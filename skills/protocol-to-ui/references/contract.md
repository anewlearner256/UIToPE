# 设计与交付契约

设计源为 UTF-8 JSON（`schema_version: 1`），由执行 Skill 的模型理解协议后编写。脚本负责确定性生成与检查，不会把关键词扫描冒充需求分析。

```json
{
  "schema_version": 1,
  "name": "项目名称",
  "revision": 1,
  "canvas": {"width": 1920, "height": 1080, "background": "#101820"},
  "font_family": "Microsoft YaHei",
  "requirements": [
    {"id": "R1", "text": "显示设备状态", "source": "协议第2节", "kind": "explicit"}
  ],
  "pages": [{
    "id": "monitor", "name": "设备监控", "requirement_ids": ["R1"],
    "regions": [{
      "id": "toolbar", "name": "操作区域", "x": 40, "y": 40,
      "width": 1840, "height": 96,
      "elements": [{
        "id": "start", "name": "启动设备按钮", "type": "button",
        "x": 0, "y": 0, "width": 160, "height": 48,
        "padding": 4, "requirement_ids": ["R1"],
        "display_state": "unselected",
        "states": {
          "unselected": "<rect x='1' y='1' width='158' height='46' fill='#243444'/><text x='80' y='31' text-anchor='middle' font-size='18' fill='white'>启动设备</text>",
          "selected": "<rect x='1' y='1' width='158' height='46' fill='#087f73'/><text x='80' y='31' text-anchor='middle' font-size='18' fill='white'>启动设备</text>"
        }
      }]
    }]
  }]
}
```

## 字段

- `id` 为稳定标识，采用小写字母起始的 ASCII 字母、数字、连字符或下划线；页面、区域、元素标识全项目唯一。客户修改时保留。
- 名称描述内容；支持中文。文件名取 `页面/区域/元素名称[_状态].svg|png`，自动替换 Windows 非法字符；替换后重复会报错，需补充语义限定。
- `requirements` 必须有出处；`kind` 为 `explicit` 或 `assumption`。假设出处写清推导依据。这里只记录需要 UI 承接的要求，非 UI 条款在分析文档另列。
- 每页必须映射需求；所有 UI 需求必须至少由一页承接。元素可用 `requirement_ids` 进一步细化。
- `type` 为 `button`、`icon`、`text`、`panel`、`image`、`chart`、`table`、`input`、`status`、`group` 之一。除按钮外，用 `svg` 字段描述元素内部；按钮必须有且仅有上述两种 `states`。
- 元素位置相对于区域；内部 SVG 坐标相对于元素。内部复杂结构继续用带 `data-name` 的 `<g>` 分组；也可以给图元加 `data-name`。文字使用 `<text>`，保持可编辑。
- `export` 默认为 true。背景等无需独立交付的元素可设置 false，但按钮始终必须导出。
- `padding` 默认 4，范围 0–128，表示四周额外透明留白，避免描边/阴影裁切。若阴影超出，显式增加。两种状态共享尺寸和留白。
- SVG 片段支持常用形状、文字、路径、嵌入 PNG/JPEG、渐变、裁剪、滤镜。禁用脚本、事件、外链、foreignObject、CSS style 标签与实体声明。引用仅允许片段内 `#id`，生成时自动加唯一前缀。
- 色彩用显式属性。不要依赖外部 CSS、字体链接或外部图片。字体由机器提供；交付清单记录字体名，跨机器需安装相同字体。
- 画布固定 1920×1080；资源 SVG 的尺寸按元素尺寸加留白确定。PNG 默认 3x，如 160×48 按钮加四边4px留白，PNG 为 504×168。

## 修改契约

补丁含 `expected_revision`、`reason`、`changes`；每项包含 `element_id` 和 `set`，可修改元素的名称、位置、尺寸、SVG、状态、默认状态、留白、导出开关与需求引用。禁止通过补丁改 ID 或类型。补丁输出新源文件、递增 revision、写入 change_log；旧源文件与交付目录保持可追溯。跨页面结构调整直接编辑 JSON 并递增 revision，再验证。

```json
{"expected_revision":1,"reason":"客户要求启动设备按钮使用橙色","changes":[{"element_id":"start","set":{"states":{"unselected":"<rect width='160' height='48' fill='#5a3d20'/>","selected":"<rect width='160' height='48' fill='#e78323'/>"}}}]}
```

## 验收

交付目录包含 `design.json`、`requirements.md`、`pages/`、`assets/`、`manifest.json`、`validation.json`。页面 SVG 含页面/区域/元素/状态/内部内容分组；备用按钮状态在页面中隐藏，独立资源分别导出。页面预览为 3x PNG。所有资源 SVG/PNG 配对，manifest 记录像素尺寸、逻辑尺寸、状态、字体、需求映射与 SHA-256。

`check` 校验源文件一致性、完整文件集合、摘要、SVG 画布/分组/状态、PNG 实际像素尺寸和状态视觉差异。仍需查看预览与透明素材，检查内容质量、文字溢出、重叠和效果裁切；机器检查不能替代视觉检查。
