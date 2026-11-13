"""Build, check and revise grouped SVG / high-resolution asset deliveries."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from model import STATES, apply_changes, plan, require, validate

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def scene_hash(design):
    return digest(json.dumps(design, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def png_size(path):
    with Path(path).open("rb") as stream:
        header = stream.read(24)
    require(len(header) == 24 and header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR", f"PNG 格式错误：{path}")
    return struct.unpack(">II", header[16:24])


def requirements_markdown(design):
    lines = [f"# {design['name']} · UI 需求映射", "", f"设计版本：{design['revision']}", "",
             f"字体：{design['font_family']}；页面：1920 × 1080。", ""]
    for req in design["requirements"]:
        pages = [p["name"] for p in design["pages"] if req["id"] in p["requirement_ids"]]
        lines += [f"- {req['id']}｜{'协议要求' if req['kind'] == 'explicit' else '设计假设'}：{req['text']}",
                  f"  - 依据：{req['source']}", f"  - 页面：{'、'.join(pages)}"]
    if design.get("change_log"):
        lines += ["", "## 修改记录", ""]
        for entry in design["change_log"]:
            lines.append(f"- v{entry['revision']}：{entry['reason']}（{', '.join(entry['element_ids'])}）")
    return "\n".join(lines) + "\n"


def check(design, output):
    validate(design)
    output = Path(output).resolve()
    manifest = read_json(output / "manifest.json")
    require(manifest.get("schema_version") == 1, "交付清单版本不支持")
    require(manifest.get("source_sha256") == scene_hash(design), "交付与当前设计源不一致")
    items = plan(design, manifest.get("scale"))
    expected_metadata = [{key: value for key, value in item.items() if key != "svg"} for item in items]
    require(manifest.get("items") == expected_metadata, "交付清单与设计元素不一致")
    paths = {"design.json", "requirements.md"}
    for item in items:
        paths.add(item["path"])
        paths.add(str(Path(item["path"]).with_suffix(".png")).replace("\\", "/"))
    require(set(manifest.get("files", {})) == paths, "交付清单文件集合不完整")
    actual_paths = {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
    require(actual_paths == paths | {"manifest.json", "validation.json"}, "交付存在缺失文件或未登记的遗留文件")
    for path in paths:
        target = output / path
        require(target.resolve().is_relative_to(output) and not target.is_symlink(), "交付文件不能指向目录外部")
        require(digest(target.read_bytes()) == manifest["files"][path], f"交付文件已变化：{path}")
    require(scene_hash(read_json(output / "design.json")) == scene_hash(design), "交付中的设计源不一致")
    require((output / "requirements.md").read_text(encoding="utf-8") == requirements_markdown(design), "需求映射已变化")
    states = {}
    for item in items:
        target = output / item["path"]
        require(target.read_text(encoding="utf-8") == item["svg"], f"SVG 分组或内容与设计源不一致：{item['path']}")
        svg = ET.fromstring(item["svg"])
        require(svg.get("viewBox") == f"0 0 {item['width']} {item['height']}", "SVG viewBox 错误")
        png = target.with_suffix(".png")
        require(png_size(png) == (item["pixel_width"], item["pixel_height"]), f"PNG 分辨率错误：{png}")
        if item.get("type") == "button":
            states.setdefault(item["element_id"], {})[item["state"]] = digest(png.read_bytes())
    for element_id, variants in states.items():
        require(set(variants) == set(STATES) and len(set(variants.values())) == 2, f"按钮两种状态必须视觉不同：{element_id}")
    return {"passed": True, "revision": design["revision"], "scale": manifest["scale"],
            "pages": sum(i["kind"] == "page" for i in items),
            "assets": sum(i["kind"] == "asset" for i in items), "buttons": len(states),
            "checks": ["需求映射", "源文件一致性", "文件完整性与摘要", "SVG分组与尺寸", "PNG实际像素尺寸", "按钮双状态视觉差异"],
            "visual_review_required": ["客户需求与布局", "文字溢出与重叠", "字体一致性", "透明素材及效果留白"]}


def build(design, output, scale=3):
    validate(design)
    items = plan(design, scale)
    output = Path(output).absolute()
    require(not output.exists(), "交付目录已存在；请使用新的版本目录以保留人工修改")
    require(shutil.which("node") is not None, "PNG 导出需要 Node.js")
    require((ROOT / "node_modules/@resvg/resvg-js").exists(), f"请先在 {ROOT} 执行 npm ci --ignore-scripts")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ui-build-", dir=output.parent) as temp:
        stage = Path(temp) / "delivery"
        stage.mkdir()
        write_json(stage / "design.json", design)
        (stage / "requirements.md").write_text(requirements_markdown(design), encoding="utf-8")
        jobs = []
        for item in items:
            target = stage / item["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(item["svg"], encoding="utf-8")
            jobs.append({key: value for key, value in item.items() if key in {"kind", "padding", "pixel_width", "pixel_height"}} |
                        {"svg": str(target), "png": str(target.with_suffix(".png"))})
        result = subprocess.run([shutil.which("node"), str(ROOT / "scripts/render.cjs")],
                                input=json.dumps({"jobs": jobs, "scale": scale, "font_family": design["font_family"]}),
                                text=True, encoding="utf-8", capture_output=True, timeout=300, cwd=ROOT)
        require(result.returncode == 0, "PNG 导出失败：" + result.stderr.strip())
        files = {p.relative_to(stage).as_posix(): digest(p.read_bytes()) for p in stage.rglob("*") if p.is_file()}
        write_json(stage / "manifest.json", {"schema_version": 1, "name": design["name"], "revision": design["revision"],
            "source_sha256": scene_hash(design), "font_family": design["font_family"], "scale": scale,
            "renderer": "@resvg/resvg-js 2.6.2", "files": files,
            "items": [{key: value for key, value in item.items() if key != "svg"} for item in items]})
        write_json(stage / "validation.json", {"passed": False})
        report = check(design, stage)
        write_json(stage / "validation.json", report)
        stage.rename(output)
    return report


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="生成和检查按元素分组的 1920×1080 SVG 与高分辨率素材")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "build", "check"):
        command = commands.add_parser(name)
        command.add_argument("design", type=Path)
        if name in {"build", "check"}:
            command.add_argument("--out", type=Path, required=True)
        if name == "build":
            command.add_argument("--scale", type=int, choices=(2, 3, 4), default=3)
    command = commands.add_parser("patch")
    command.add_argument("design", type=Path)
    command.add_argument("patch", type=Path)
    command.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        design = read_json(args.design)
        if args.command == "validate":
            validate(design)
            result = {"passed": True, "pages": len(design["pages"]), "revision": design["revision"]}
        elif args.command == "build":
            result = build(design, args.out, args.scale)
        elif args.command == "check":
            result = check(design, args.out)
        else:
            result = apply_changes(design, read_json(args.patch))
            require(not args.out.exists(), "补丁输出文件已存在，请使用新的版本文件名")
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open("x", encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            result = {"passed": True, "revision": result["revision"], "output": str(args.out)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
