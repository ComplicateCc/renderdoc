# TA Performance Viewer 使用说明

`TA Performance Viewer` 是面向 TA/渲染分析的层级化性能预览窗口，用来比 `Statistics Viewer` 文本报告更清晰地观察 `.rdc` 中的 action/marker 结构、draw 分布和 GPU counter 数据。

## 打开方式

在 qrenderdoc 中打开捕获后：

```text
Window -> TA Performance Viewer
```

## 基础列

窗口默认展示一棵与 Event Browser action/marker 对应的树：

- `EID`：事件 ID。
- `Action`：action 或 marker 名称。
- `Type`：Draw、Dispatch、Marker、Copy、Resolve、Clear 等动作类型。
- `Draws`：该节点及子节点下的 draw-like action 数量。
- `Dispatches`：该节点及子节点下的 compute dispatch 数量。
- `Vertices/Indices`：基于 action 记录的顶点/索引数量汇总。
- `Triangles (est.)`：估算三角面数，当前按 `vertices_or_indices * instances / 3` 估算。
- `Children`：直接子节点数量。

## Performance Counter 数据

点击工具栏中的 `Capture counters` 可以打开与 `Performance Counter Viewer` 相同的 counter 选择窗口。

选择并采集后：

- 所有选择的 counter 会作为额外列追加到树形表格后面。
- counter 名称和单位显示逻辑与 `Performance Counter Viewer` 保持一致。
- 时间类 counter 会根据 RenderDoc 当前时间单位配置显示为 s/ms/us/ns。
- 对 marker/父节点，会聚合子节点 counter 值，用于模拟一段 marker 区间下的 draw 耗时或成本。

## 交互功能

- `Refresh`：重新生成 action 树。
- `Capture counters`：选择并采集 GPU counters。
- `Sync with Event Browser`：按 Event Browser 可见性过滤，并同步当前事件选中。
- `Hide no-draw nodes`：隐藏不包含 draw 的节点，只保留 draw 链路相关内容。
- `Expand All` / `Collapse All`：展开或折叠完整 action 树。
- 双击任意行：跳转到对应 EID。
- 点击列头：按该列排序，包括动态追加的 counter 列。
- 导出按钮：导出 CSV，`Action` 列会保留缩进以表示树层级。

## 注意事项

- `Triangles (est.)` 是估算值，不等同于精确 primitive 数。更精确的统计需要结合每个 draw 的 topology 或 replay 后的 mesh 数据。
- counter 父节点聚合默认采用数值求和，适合 duration、cycles、bytes 等成本类指标；对百分比、比率类 counter 仅作为粗略参考。
- `Hide no-draw nodes` 会保留包含 draw 子节点的 marker 父节点，便于观察 draw 链状结构。
