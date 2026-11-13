"""Extract source text and locators; requirement interpretation belongs to the agent."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from zipfile import ZipFile

W = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def paragraph_text(node):
    text = []
    for part in node.iter():
        local = part.tag.rsplit("}", 1)[-1]
        if local == "t":
            text.append(part.text or "")
        elif local == "tab":
            text.append("\t")
        elif local == "br":
            text.append("\n")
    return "".join(text).strip()


def extract(path):
    path = Path(path)
    suffix = path.suffix.lower()
    blocks, ocr_pages = [], []
    warnings = []
    if suffix in {".txt", ".md"}:
        try:
            content = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            content = path.read_text(encoding="gb18030")
            warnings.append("源文件使用 GB18030 解码，请核对文字。")
        blocks = [{"locator": f"行 {index}", "text": line} for index, line in enumerate(content.splitlines(), 1) if line.strip()]
    elif suffix == ".docx":
        with ZipFile(path) as archive:
            entry = archive.getinfo("word/document.xml")
            if entry.file_size > 30_000_000:
                raise ValueError("DOCX 正文 XML 超过 30MB")
            xml = archive.read(entry)
        if b"<!" in xml:
            raise ValueError("DOCX XML 包含不允许的实体声明")
        body = ET.fromstring(xml).find("w:body", W)
        if body is None:
            raise ValueError("DOCX 缺少正文")
        paragraphs = tables = 0
        for node in body:
            tag = node.tag.rsplit("}", 1)[-1]
            if tag == "p":
                paragraphs += 1
                text = paragraph_text(node)
                if text:
                    blocks.append({"locator": f"段落 {paragraphs}", "text": text})
            elif tag == "tbl":
                tables += 1
                for index, row in enumerate(node.findall("w:tr", W), 1):
                    cells = [paragraph_text(cell) for cell in row.findall("w:tc", W)]
                    blocks.append({"locator": f"表格 {tables} / 行 {index}", "text": " | ".join(cells)})
        warnings.append("DOCX 提取正文与表格文字；需另行检查截图、图纸、页眉页脚、批注及修订内容。")
    elif suffix == ".pdf":
        try:
            import pymupdf
        except ImportError as exc:
            raise ValueError("PDF 提取需要 PyMuPDF：python -m pip install -r requirements.txt") from exc
        with pymupdf.open(path) as document:
            if document.needs_pass:
                raise ValueError("PDF 已加密，需要先提供可读取的版本")
            for index, page in enumerate(document, 1):
                text = page.get_text(sort=True).strip()
                if text:
                    blocks.append({"locator": f"第 {index} 页", "text": text})
                else:
                    ocr_pages.append(index)
        warnings.append("PDF 文字按阅读顺序提取；需视觉检查多栏、表格和图中内容。无文字页单独标记，不能当作已完整解析。")
    else:
        raise ValueError("支持 .txt、.md、.docx、.pdf；旧版 .doc 请先转为 .docx")
    if not blocks and not ocr_pages:
        raise ValueError("未提取到协议内容")
    return {"schema_version": 1, "source_file": path.name,
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "blocks": blocks, "needs_ocr_pages": ocr_pages, "warnings": warnings}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="提取技术协议文字并保留出处位置")
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = extract(args.source)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(json.dumps({"output": str(args.out), "blocks": len(result["blocks"]),
                          "needs_ocr_pages": result["needs_ocr_pages"]}, ensure_ascii=False))
        return 2 if result["needs_ocr_pages"] else 0
    except (OSError, ValueError, KeyError, ET.ParseError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
