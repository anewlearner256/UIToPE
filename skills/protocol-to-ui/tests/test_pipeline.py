import copy
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import model
import ui
from extract_protocol import extract
from zipfile import ZipFile


def scene():
    return {
        "schema_version": 1, "name": "设备控制", "revision": 1,
        "canvas": {"width": 1920, "height": 1080, "background": "#101820"},
        "font_family": "Microsoft YaHei",
        "requirements": [{"id": "R1", "text": "启停设备", "source": "第1节", "kind": "explicit"}],
        "pages": [{"id": "control", "name": "设备控制", "requirement_ids": ["R1"],
                   "regions": [{"id": "actions", "name": "操作区域", "x": 20, "y": 20,
                                "width": 1880, "height": 1040,
                                "elements": [{"id": "start", "name": "启动设备按钮", "type": "button",
                                              "x": 10, "y": 10, "width": 160, "height": 48,
                                              "states": {"unselected": "<rect width='160' height='48' fill='#334455'/>",
                                                         "selected": "<rect width='160' height='48' fill='#008877'/>"}}]}]}]}


class ContractTests(unittest.TestCase):
    def test_page_and_assets_keep_grouping_dimensions_and_two_states(self):
        design = scene()
        model.validate(design)
        outputs = model.plan(design, 3)
        page = next(o for o in outputs if o["kind"] == "page")
        root = ET.fromstring(page["svg"])
        self.assertEqual((root.get("width"), root.get("height"), root.get("viewBox")),
                         ("1920", "1080", "0 0 1920 1080"))
        names = [g.get("data-name") for g in root.iter("{http://www.w3.org/2000/svg}g")]
        for name in ["设备控制", "操作区域", "启动设备按钮", "选中", "未选中"]:
            self.assertIn(name, names)
        assets = [o for o in outputs if o["kind"] == "asset"]
        self.assertEqual({o["state"] for o in assets}, {"selected", "unselected"})
        self.assertEqual({(o["pixel_width"], o["pixel_height"]) for o in assets}, {(504, 168)})
        self.assertTrue(any("启动设备按钮_选中" in o["path"] for o in assets))

    def test_rejects_wrong_canvas_missing_state_duplicate_ids_and_missing_coverage(self):
        for mutate in [lambda d: d["canvas"].update(width=1280),
                       lambda d: d["pages"][0]["regions"][0]["elements"][0]["states"].pop("selected"),
                       lambda d: d["pages"][0]["regions"][0].update(id="control"),
                       lambda d: d["requirements"].append({"id":"R2","text":"告警","source":"第2节","kind":"explicit"})]:
            with self.subTest(mutate=mutate):
                design = scene()
                mutate(design)
                with self.assertRaises(ValueError):
                    model.validate(design)

    def test_rejects_malformed_nodes_and_unknown_fields(self):
        mutations = [lambda d: d.update(canvas=[]),
                     lambda d: d['requirements'].append('invalid'),
                     lambda d: d['pages'][0]['regions'][0]['elements'][0].update(paddding=100)]
        for mutate in mutations:
            design = scene()
            mutate(design)
            with self.assertRaises(ValueError):
                model.validate(design)

    def test_rejects_unsafe_svg_and_broken_local_reference(self):
        for svg in ["<script>alert(1)</script>", "<rect onload='x()'/>",
                    "<image href='https://example.com/a.png'/>",
                    "<rect fill='url(https://example.com/x)'/>",
                    "<use href='#missing'/>", "<foreignObject/>",
                    "<!DOCTYPE g [<!ENTITY x SYSTEM 'file:///etc/passwd'>]><g/>"]:
            with self.subTest(svg=svg):
                design = scene()
                design["pages"][0]["regions"][0]["elements"][0]["states"]["selected"] = svg
                with self.assertRaises(ValueError):
                    model.validate(design)

    def test_resource_name_collisions_are_rejected_after_sanitizing(self):
        design = scene()
        elements = design["pages"][0]["regions"][0]["elements"]
        elements[0]["name"] = "启动/设备"
        other = copy.deepcopy(elements[0])
        other.update(id="start2", name="启动:设备")
        elements.append(other)
        with self.assertRaises(ValueError):
            model.validate(design)

    def test_definitions_get_unique_ids_in_each_state(self):
        design = scene()
        element = design["pages"][0]["regions"][0]["elements"][0]
        for state, color in [("unselected", "red"), ("selected", "blue")]:
            element["states"][state] = f"<defs><linearGradient id='paint'><stop stop-color='{color}'/></linearGradient></defs><rect width='160' height='48' fill='url(#paint)'/>"
        model.validate(design)
        root = ET.fromstring(model.plan(design, 3)[0]["svg"])
        ids = [n.get("id") for n in root.iter() if n.get("id")]
        self.assertEqual(len(ids), len(set(ids)))
        for node in root.iter():
            if node.get("fill", "").startswith("url(#"):
                self.assertIn(node.get("fill")[5:-1], ids)

    def test_rejects_ids_that_collide_with_generated_group_ids(self):
        design = scene()
        design['pages'][0]['regions'][0]['id'] = 'start-selected-content'
        with self.assertRaises(ValueError):
            model.validate(design)

    def test_patch_updates_only_target_and_checks_revision(self):
        design = scene()
        patch = {"expected_revision": 1, "reason": "客户修改文案", "changes": [
            {"element_id": "start", "set": {"name": "运行设备按钮"}}]}
        result = model.apply_changes(design, patch)
        self.assertEqual(design["revision"], 1)
        self.assertEqual(result["revision"], 2)
        self.assertEqual(result["pages"][0]["regions"][0]["elements"][0]["name"], "运行设备按钮")
        self.assertEqual(design["pages"][0]["regions"][0]["elements"][0]["name"], "启动设备按钮")
        patch["expected_revision"] = 0
        with self.assertRaises(ValueError):
            model.apply_changes(design, patch)


class DeliveryTests(unittest.TestCase):
    def test_build_exports_real_3x_pngs_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "交付"
            ui.build(scene(), output, 3)
            report = ui.check(scene(), output)
            self.assertTrue(report["passed"])
            assets = list((output / "assets").rglob("*.png"))
            self.assertEqual(len(assets), 2)
            self.assertTrue(all(ui.png_size(p) == (504, 168) for p in assets))
            self.assertNotEqual(assets[0].read_bytes(), assets[1].read_bytes())
            assets[0].write_bytes(assets[1].read_bytes())
            with self.assertRaises(ValueError):
                ui.check(scene(), output)

    def test_build_does_not_overwrite_an_existing_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "人工设计"
            output.mkdir()
            original = output / "客户修改.txt"
            original.write_text("需要保留", encoding="utf-8")
            with self.assertRaises(ValueError):
                ui.build(scene(), output, 3)
            self.assertEqual(original.read_text(encoding="utf-8"), "需要保留")

    def test_render_rejects_identical_looking_button_states(self):
        design = scene()
        button = design["pages"][0]["regions"][0]["elements"][0]
        button["states"]["selected"] = "<g>" + button["states"]["unselected"] + "</g>"
        model.validate(design)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                ui.build(design, Path(tmp) / "交付", 3)
            self.assertFalse((Path(tmp) / "交付").exists())

    def test_render_reports_overflow_at_asset_boundary(self):
        design = scene()
        button = design["pages"][0]["regions"][0]["elements"][0]
        button["states"]["selected"] = "<rect x='-50' y='-50' width='260' height='148' fill='red'/>"
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                ui.build(design, Path(tmp) / "交付", 3)

    def test_check_detects_missing_or_unexpected_files_and_changed_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "交付"
            ui.build(scene(), output, 2)
            unexpected = output / "遗留资源.svg"
            unexpected.write_text("stale", encoding="utf-8")
            with self.assertRaises(ValueError):
                ui.check(scene(), output)
            unexpected.unlink()
            design = scene()
            design["name"] = "另一个项目"
            with self.assertRaises(ValueError):
                ui.check(design, output)


class ExtractionTests(unittest.TestCase):
    def test_extracts_markdown_with_source_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "技术协议.md"
            source.write_text("# 设备系统\n\n支持设备监控\n", encoding="utf-8")
            result = extract(source)
            self.assertEqual(result["blocks"][1], {"locator": "行 3", "text": "支持设备监控"})
            self.assertEqual(result["needs_ocr_pages"], [])

    def test_extracts_docx_paragraph_and_table_in_document_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "协议.docx"
            xml = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>功能要求</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>设备编号</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>必填</w:t></w:r></w:p></w:tc></w:tr></w:tbl><w:p><w:r><w:t>支持告警查询</w:t></w:r></w:p></w:body></w:document>'
            with ZipFile(source, "w") as archive:
                archive.writestr("word/document.xml", xml)
            blocks = extract(source)["blocks"]
            self.assertEqual([b["text"] for b in blocks], ["功能要求", "设备编号 | 必填", "支持告警查询"])
            self.assertEqual(blocks[1]["locator"], "表格 1 / 行 1")

    def test_pdf_marks_blank_pages_for_ocr_instead_of_silently_omitting(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "协议.pdf"
            with pymupdf.open() as document:
                page = document.new_page()
                page.insert_text((40, 40), "Device monitoring")
                document.new_page()
                document.save(source)
            result = extract(source)
            self.assertEqual(result["blocks"][0]["locator"], "第 1 页")
            self.assertEqual(result["needs_ocr_pages"], [2])


if __name__ == "__main__":
    unittest.main()
