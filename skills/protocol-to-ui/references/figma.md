# Figma 交付路径

SVG 路线可独立完成完整交付；仅当用户选择 Figma 或确实需要 Figma 协作时读取本说明。

## 能力选择

优先发现并使用已连接的官方 Figma 集成。实际工具列表决定当前能力；存在 Figma 连接不等于存在全部写入能力。若有官方 Figma skill，先按该集成的要求加载对应 skill。

官方文档核对日期：2026-11-13。

- [工具能力](https://developers.figma.com/docs/figma-mcp-server/tools-and-prompts/)：`use_figma` 可创建/修改页面、框架、组件、变体、变量和文字；`download_assets` 可导出指定节点的 SVG/PNG。
- [HTML 转图层](https://developers.figma.com/docs/figma-mcp-server/tools-and-prompts/#html_to_figma)：结果为普通图层，不自动使用组件库与变量。
- [SVG 导入](https://developers.figma.com/docs/plugins/api/properties/figma-createnodefromsvg/)：导入 SVG 与创建原生组件不是同一操作。
- [节点导出](https://developers.figma.com/docs/plugins/api/properties/nodes-exportasync/)：插件环境支持按倍率导出；官方 MCP 实际导出选项以当前文档为准。

## 从统一设计源创建

沿用 design JSON 的稳定 ID、名称、区域、元素尺寸与需求引用。每页创建 1920×1080 Frame，按区域和元素命名。优先复用客户已有组件和变量。

按钮创建一个组件集与两种变体，命名属性 `状态=未选中/选中`；页面放置对应默认状态的实例。文字用原生 Text，容器用原生 Frame/形状；保留可编辑内容，适合的容器设置 Auto Layout。图标路径可以导入 SVG，但不要把整页或整颗含文字的按钮当成一个扁平矢量对象。

design JSON 中元素 SVG 的形状、文字、颜色用于转译；并非把 SVG 字符串传给工具就自动拥有原生组件语义。复杂图表可作为命名图层组，但仍保留关键文字和图形的分组。

写入后回读文件结构，验证页面尺寸、区域层级、组件实例引用、按钮变体和文字编辑能力；再查看页面截图。保存 `figma-map.json`，记录文件链接、每个稳定元素 ID 的节点 ID、组件集 ID、两个变体 ID 和设计 revision。该映射是实际写入后生成的数据，不能预先编造。

## 导出和修改

按内容名称导出每个素材节点；按钮分别从两个变体导出，且 bounds/padding 一致。PNG 默认 3x，资源 SVG 保留矢量。留白不足时应调整外层导出框。检查实际 PNG 像素尺寸、透明边缘与两状态视觉差异。

修改前回读相关节点并与上次源和映射比较，保留客户的人工编辑。修改组件后检查所有实例；新增版本记录客户意见与影响范围。交付 Figma 文件链接及独立素材。`.fig` 本地副本仅在实际使用支持的保存/导出功能后提供，不能给 JSON 改后缀。

当前包未自带 Figma 登录、写入工具或私有格式编码器，Figma 路径需要实际集成后执行和验证。若未连接且用户接受 SVG，则完成 SVG 交付；用户明确只接受 Figma 时，应说明缺少连接，不把 SVG 交付报告为 Figma 成功。
