"""Validated design model and deterministic, editable SVG generation."""

import copy
import re
import xml.etree.ElementTree as ET

SVG = "http://www.w3.org/2000/svg"
INK = "http://www.inkscape.org/namespaces/inkscape"
XLINK = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG)
ET.register_namespace("inkscape", INK)
STATES = {"unselected": "未选中", "selected": "选中"}
TYPES = {"button", "icon", "text", "panel", "image", "chart", "table", "input", "status", "group"}
TAGS = set("g defs rect circle ellipse line polyline polygon path text tspan image use linearGradient radialGradient stop clipPath mask filter feGaussianBlur feOffset feFlood feComposite feMerge feMergeNode feColorMatrix feBlend title desc".split())
ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
URL = re.compile(r"url\(\s*['\"]?([^)'\"\s]+)['\"]?\s*\)", re.I)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def label(value, location):
    require(isinstance(value, str) and value.strip(), f"{location}: 必须是非空文本")


def number(value, location, low=0, high=10000):
    require(type(value) is int and low <= value <= high, f"{location}: 必须是 {low}–{high} 的整数")


def fields(node, allowed, location):
    require(isinstance(node, dict), f"{location}: 必须为对象")
    require(not (set(node) - set(allowed)), f"{location}: 不支持的字段 {sorted(set(node) - set(allowed))}")


def safe_name(name):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    require(bool(value) and value not in {".", ".."}, "资源名称不能为空")
    require(len(value) <= 64, f"资源名称过长，请用更简洁的内容名称：{name}")
    if value.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        value += "_资源"
    return value


def fragment(markup, prefix=""):
    label(markup, "SVG 片段")
    require(len(markup) <= 2_000_000, "SVG 片段超过 2MB")
    require(not re.search(r"<!|<\?", markup), "SVG 不允许实体、DTD、处理指令或注释")
    try:
        root = ET.fromstring(f'<g xmlns="{SVG}" xmlns:xlink="{XLINK}">{markup}</g>')
    except ET.ParseError as exc:
        raise ValueError(f"SVG 语法错误：{exc}") from exc
    ids, refs = set(), []
    for node in root.iter():
        tag = node.tag.removeprefix(f"{{{SVG}}}")
        require(tag in TAGS, f"SVG 不支持或不允许标签：{tag}")
        if node.get("id"):
            require(node.get("id") not in ids, "SVG 片段内 ID 重复")
            ids.add(node.get("id"))
        for attr, value in node.attrib.items():
            name = attr.removeprefix(f"{{{XLINK}}}").lower()
            require(not name.startswith("on") and name not in {"style", "class"}, f"SVG 不允许属性：{name}")
            if name == "href":
                if value.startswith("#"):
                    refs.append(value[1:])
                else:
                    require(tag == "image" and re.fullmatch(r"data:image/(?:png|jpeg);base64,[A-Za-z0-9+/=\s]+", value) is not None,
                            "SVG 图片必须内嵌 PNG/JPEG，其他引用只能用 #id")
            for ref in URL.findall(value):
                require(ref.startswith("#"), "SVG 禁止外部 URL")
                refs.append(ref[1:])
            require("javascript:" not in value.lower() and "@import" not in value.lower(), "SVG 包含不允许的引用")
    require(all(ref in ids for ref in refs), "SVG 引用了片段内不存在的 ID")
    if prefix:
        for node in root.iter():
            for attr, value in list(node.attrib.items()):
                if attr == "id":
                    node.set(attr, prefix + value)
                elif attr in {"href", f"{{{XLINK}}}href"} and value.startswith("#"):
                    node.set(attr, "#" + prefix + value[1:])
                else:
                    node.set(attr, URL.sub(lambda m: f"url(#{prefix}{m.group(1)[1:]})", value))
    return root


def each_element(design):
    for page in design["pages"]:
        for region in page["regions"]:
            for element in region["elements"]:
                yield page, region, element


def validate(design):
    fields(design, {"schema_version", "name", "revision", "canvas", "font_family", "requirements", "pages", "change_log"}, "设计源")
    require(design.get("schema_version") == 1, "schema_version 必须为 1")
    label(design.get("name"), "name")
    number(design.get("revision"), "revision", 1)
    canvas = design.get("canvas", {})
    fields(canvas, {"width", "height", "background"}, "canvas")
    require(canvas.get("width") == 1920 and canvas.get("height") == 1080, "页面画布必须为 1920×1080")
    require(re.fullmatch(r"#[0-9a-fA-F]{6}", canvas.get("background", "")) is not None, "背景必须为 #RRGGBB")
    label(design.get("font_family"), "font_family")
    requirements = design.get("requirements")
    require(isinstance(requirements, list) and requirements, "必须提供 UI 需求与出处")
    req_ids = set()
    for req in requirements:
        fields(req, {"id", "text", "source", "kind"}, "requirement")
        for key in ("id", "text", "source"):
            label(req.get(key), f"requirement.{key}")
        require(req["id"] not in req_ids, "需求 ID 重复")
        require(req.get("kind") in {"explicit", "assumption"}, "需求 kind 必须为 explicit 或 assumption")
        req_ids.add(req["id"])

    ids, mapped = set(), set()

    def identity(node, scope):
        require(isinstance(node, dict), f"{scope} 必须为对象")
        require(isinstance(node.get("id"), str) and ID.fullmatch(node["id"]), f"{scope}: ID 格式错误")
        require(node["id"] not in ids, f"重复 ID：{node['id']}")
        ids.add(node["id"])
        label(node.get("name"), f"{scope}.name")
        safe_name(node["name"])
        refs = node.get("requirement_ids", [])
        require(isinstance(refs, list) and all(isinstance(r, str) and r in req_ids for r in refs), f"{scope}: 需求引用不存在")

    def bounds(node, parent_width, parent_height):
        for key in ("x", "y"):
            number(node.get(key), key)
        for key in ("width", "height"):
            number(node.get(key), key, 1)
        require(node["x"] + node["width"] <= parent_width and node["y"] + node["height"] <= parent_height,
                f"{node['name']}: 元素边界超出父区域")

    require(isinstance(design.get("pages"), list) and design["pages"], "必须至少有一页")
    for page in design["pages"]:
        fields(page, {"id", "name", "requirement_ids", "regions"}, "page")
        identity(page, "page")
        require(bool(page.get("requirement_ids")), f"{page['name']}: 页面必须映射需求")
        mapped.update(page["requirement_ids"])
        require(isinstance(page.get("regions"), list) and page["regions"], "页面至少包含一个区域")
        for region in page["regions"]:
            fields(region, {"id", "name", "requirement_ids", "x", "y", "width", "height", "elements"}, "region")
            identity(region, "region")
            bounds(region, 1920, 1080)
            require(isinstance(region.get("elements"), list) and region["elements"], "区域至少包含一个元素")
            for element in region["elements"]:
                fields(element, {"id", "name", "requirement_ids", "type", "x", "y", "width", "height", "svg", "states", "display_state", "padding", "export"}, "element")
                identity(element, "element")
                bounds(element, region["width"], region["height"])
                require(element.get("type") in TYPES, f"不支持的元素类型：{element.get('type')}")
                require(type(element.get("export", True)) is bool, "export 必须为布尔值")
                number(element.get("padding", 4), "padding", 0, 128)
                if element["type"] == "button":
                    states = element.get("states", {})
                    require(isinstance(states, dict) and set(states) == set(STATES), f"{element['name']}: 按钮必须同时包含 selected 与 unselected")
                    require("svg" not in element and element.get("export", True), "按钮使用 states 且必须导出")
                    require(element.get("display_state", "unselected") in STATES, "按钮默认状态不合法")
                    variants = [ET.tostring(fragment(states[s])) for s in STATES]
                    require(variants[0] != variants[1], f"{element['name']}: 两种状态内容相同")
                else:
                    require("states" not in element, "非按钮使用 svg 字段")
                    fragment(element.get("svg"))
    require(req_ids <= mapped, f"存在没有页面承接的需求：{sorted(req_ids - mapped)}")
    outputs = plan(design, 3)
    for output in outputs:
        generated_ids = [n.get("id") for n in ET.fromstring(output["svg"]).iter() if n.get("id")]
        require(len(generated_ids) == len(set(generated_ids)), f"{output['path']}: ID 与生成的分组标识冲突，请调整输入 ID")
    paths = [item["path"].casefold() for item in outputs]
    require(len(paths) == len(set(paths)), "资源名称重复（含文件名清理或大小写导致的重复），请增加内容限定")
    return design


def group(parent, stable_id, name, **attributes):
    node = ET.SubElement(parent, f"{{{SVG}}}g", {
        "id": stable_id, "data-name": name, f"{{{INK}}}label": name,
        **{key: str(value) for key, value in attributes.items()},
    })
    ET.SubElement(node, f"{{{SVG}}}title").text = name
    return node


def svg_root(width, height, font_family):
    return ET.Element(f"{{{SVG}}}svg", {"width": str(width), "height": str(height),
        "viewBox": f"0 0 {width} {height}", "version": "1.1", "font-family": font_family})


def append_content(parent, markup, stable_id):
    content = group(parent, stable_id + "-content", "内部内容")
    parsed = fragment(markup, stable_id + "-ref-")
    for index, child in enumerate(parsed):
        if "id" not in child.attrib:
            child.set("id", f"{stable_id}-shape-{index}")
        if child.tag.rsplit("}", 1)[-1] not in {"defs", "title", "desc"}:
            tag = child.tag.rsplit("}", 1)[-1]
            name = "".join(child.itertext())[:64] if tag == "text" else {"rect": "矩形", "path": "矢量路径", "circle": "圆形", "line": "分隔线", "g": "元素分组"}.get(tag, tag)
            child.set(f"{{{INK}}}label", child.get("data-name", name))
        content.append(child)


def element_group(parent, element, translated=True, state=None):
    attrs = {"transform": f"translate({element['x']} {element['y']})"} if translated else {}
    outer = group(parent, element["id"], element["name"], **attrs)
    outer.set("data-type", element["type"])
    outer.set("data-requirements", ",".join(element.get("requirement_ids", [])))
    if element["type"] == "button":
        states = [state] if state else STATES
        for key in states:
            attrs = {} if state or key == element.get("display_state", "unselected") else {"display": "none"}
            variant = group(outer, element["id"] + "-" + key, STATES[key], **attrs)
            append_content(variant, element["states"][key], element["id"] + "-" + key)
    else:
        append_content(outer, element["svg"], element["id"])


def serialize(root):
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


def plan(design, scale):
    number(scale, "scale", 2, 4)
    outputs = []
    for page in design["pages"]:
        root = svg_root(1920, 1080, design["font_family"])
        outer = group(root, page["id"], page["name"])
        ET.SubElement(outer, f"{{{SVG}}}rect", {"width": "1920", "height": "1080", "fill": design["canvas"]["background"], f"{{{INK}}}label": "页面背景"})
        for region in page["regions"]:
            region_node = group(outer, region["id"], region["name"], transform=f"translate({region['x']} {region['y']})")
            for element in region["elements"]:
                element_group(region_node, element)
        outputs.append({"kind": "page", "page_id": page["id"], "name": page["name"],
                        "path": f"pages/{safe_name(page['name'])}.svg", "width": 1920, "height": 1080,
                        "pixel_width": 1920 * scale, "pixel_height": 1080 * scale,
                        "requirement_ids": page["requirement_ids"], "svg": serialize(root)})
        for region in page["regions"]:
            for element in region["elements"]:
                if not element.get("export", True):
                    continue
                padding = element.get("padding", 4)
                width, height = element["width"] + padding * 2, element["height"] + padding * 2
                for state in (STATES if element["type"] == "button" else [None]):
                    root = svg_root(width, height, design["font_family"])
                    container = group(root, "asset-origin", "导出边界", transform=f"translate({padding} {padding})")
                    element_group(container, element, translated=False, state=state)
                    name = element["name"] + ("_" + STATES[state] if state else "")
                    outputs.append({"kind": "asset", "page_id": page["id"], "region_id": region["id"],
                        "element_id": element["id"], "name": name, "type": element["type"], "state": state,
                        "path": f"assets/{safe_name(page['name'])}/{safe_name(region['name'])}/{safe_name(name)}.svg",
                        "width": width, "height": height, "logical_width": element["width"],
                        "logical_height": element["height"], "padding": padding,
                        "pixel_width": width * scale, "pixel_height": height * scale,
                        "requirement_ids": element.get("requirement_ids", []), "svg": serialize(root)})
    return outputs


def apply_changes(design, patch):
    validate(design)
    fields(patch, {"expected_revision", "reason", "changes"}, "补丁")
    number(patch.get("expected_revision"), "expected_revision", 1)
    require(patch.get("expected_revision") == design["revision"], "补丁 revision 与源文件不匹配")
    label(patch.get("reason"), "修改原因")
    require(isinstance(patch.get("changes"), list) and patch["changes"], "补丁 changes 不能为空")
    result = copy.deepcopy(design)
    elements = {e["id"]: e for _, _, e in each_element(result)}
    allowed = {"name", "x", "y", "width", "height", "svg", "states", "display_state", "padding", "export", "requirement_ids"}
    changed = []
    for change in patch["changes"]:
        fields(change, {"element_id", "set"}, "补丁修改项")
        target = change.get("element_id")
        require(target in elements and target not in changed, f"补丁目标不存在或重复：{target}")
        changes = change.get("set")
        require(isinstance(changes, dict) and bool(changes) and set(changes) <= allowed, "补丁包含不支持的字段")
        elements[target].update(copy.deepcopy(changes))
        changed.append(target)
    result["revision"] += 1
    result.setdefault("change_log", []).append({"revision": result["revision"], "reason": patch["reason"], "element_ids": changed})
    return validate(result)
