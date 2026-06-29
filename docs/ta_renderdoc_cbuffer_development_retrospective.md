# TA 向 RenderDoc CBuffer 调试开发复盘

本文记录本次扩展 RenderDoc CBuffer 调试能力时遇到的问题、排查过程、最终方案，以及后续开发中需要遵守的验证原则。

## 背景目标

- 在 CBuffer 查看器中支持对变量进行临时修改，用于 TA/渲染调试。
- 修改不写回 `.rdc` 文件，只影响 replay 阶段的预览和分析。
- 修改后 CBuffer 面板应立即显示新值，渲染结果应只受被修改变量影响。
- 支持还原，回到捕获文件原始数据。

## 主要问题与难点

### 1. 只验证构建通过是不够的

早期实现只跑了完整工程构建，确认 API/UI 能编译，但没有验证运行时闭环：

1. 修改前读取 CBuffer 原值。
2. 写入新值。
3. 立即从 replay 层读回同一 buffer/offset/type。
4. 确认读回 bytes 与写入 bytes 完全一致。
5. 刷新 UI 后确认变量显示更新。
6. 检查渲染结果是否只发生预期变化。

结果导致多轮问题只能靠人工截图发现。后续类似功能必须加入运行时读写验证，不能只用 MSBuild 成功作为完成标准。

### 2. 替换整个 buffer 会污染无关数据

最初方案是为整个 buffer 创建 proxy，然后用整块数据替换原资源。问题是实际项目中 CBuffer 可能是动态/ring buffer，不同事件可能复用同一个 buffer 或同一个 offset 表示不同语义的数据。

表现：

- 修改一个 float 后，早于当前事件的 Mesh/投影也被拉伸。
- 矩阵、世界变换等本不该改变的数据被污染。

原因：

- 整块 buffer 快照来自某个事件。
- 这个快照被应用到其他 replay 事件时，会把该事件自己的 CBuffer 内容覆盖掉。

解决方向：

- 不保存整块 buffer 快照作为最终修改语义。
- 只保存用户真正修改的字节范围：`eventId + resourceId + byteOffset + patch bytes`。
- replay 到事件后，以该事件自己的 live buffer 数据为基底，再应用 patch range。

### 3. D3D11 resource replacement 会改变 CBuffer 绑定窗口

曾尝试使用 `ReplaceResource(originalBuffer, proxyBuffer)`。这会让 replay 中所有对原 buffer 的绑定/更新都转向 proxy buffer。用户测试发现修改后 CBuffer 数据整体“串行错位”：

- `u_texture_trans1` 变成原来的 `u_rt_size`。
- 后续字段整体向后错 16 字节。

这说明不是变量 offset 错，而是 D3D11 CBuffer 的绑定窗口（`FirstConstant` / `NumConstants` / descriptor byte offset）受到 replacement 方案影响。

解决方案：

- 对 CBuffer 调试修改，不再替换 resource object。
- replay 结束后直接 patch 当前 live buffer 数据。
- 这样不会改变 D3D11 pipeline state 中的 buffer 对象绑定、constant window offset、descriptor offset/size。

### 4. D3D11 GetBufferData 需要走正确的 live resource

早期 `D3D11Replay::GetBufferData()` 直接从 `WrappedID3D11Buffer::m_BufferList` 拿原始对象，绕过了 `ResourceManager` 的 replacement 映射。虽然最终 CBuffer 修改不再使用 resource replacement，但这次排查暴露了一个原则：

- 读回验证必须与渲染实际使用的数据路径一致。
- 如果存在 replacement 或 live patch，读取路径必须读到当前 replay live 数据，而不是 capture 原始对象或陈旧缓存。

### 5. Dynamic buffer 不能只依赖 UpdateSubresource

最终出现：写入后立即读回仍然不匹配。

报错示例：

```text
Replacement was written but readback did not match (buffer ResourceId:276006, offset 120, size 4, type float, components 1)
```

原因：目标 CBuffer 很可能是 `D3D11_USAGE_DYNAMIC + D3D11_CPU_ACCESS_WRITE`。对这种 buffer，用 `UpdateSubresource()` 写回可能无效或不可靠。

最终修复：

- 在 `D3D11Replay::SetProxyBufferData()` 中识别 dynamic writable buffer。
- 对 dynamic buffer 使用：

```text
Map(D3D11_MAP_WRITE_DISCARD) -> memcpy -> Unmap
```

- 非 dynamic buffer 继续使用 `UpdateSubresource()`。

### 6. offset 语义必须明确

CBuffer UI 中显示的 offset 通常是相对当前 CBuffer range 的变量 offset；实际写入 live buffer 时需要转换为：

```text
absoluteOffset = descriptor.byteOffset + variableRelativeOffset
```

开发中必须明确每个 offset 是：

- 相对 CBuffer 结构。
- 相对 buffer 资源。
- 相对 descriptor/view range。
- 相对当前 paging/viewer range。

任何一处混淆都会表现为字段错位、矩阵损坏或读回不匹配。

## 最终方案概述

当前方案遵循以下策略：

1. UI 只允许编辑基础标量/向量类型：`float`、`double`、`int`、`uint`、`bool`。
2. 暂不允许直接编辑矩阵整行，避免 row-major/column-major、stride 和 padding 复杂性导致错写。
3. 编辑时只生成变量对应的 patch bytes，不保存整块 CBuffer 快照。
4. patch 记录从当前事件开始生效，避免污染更早事件。
5. replay 后对当前 live buffer 应用 patch。
6. 写入后立即从 replay 层读回同一 offset/type/components，并做 byte-level 比较。
7. 校验失败时向 UI 报告 buffer、offset、size、type、components。

## 后续开发验证建议

### 必须验证的最小闭环

每次修改 CBuffer 编辑逻辑后，都必须验证：

- 修改前目标变量值正确。
- 修改后目标变量值变为输入值。
- 目标变量前后的相邻字段不变。
- 矩阵字段不发生整体错位。
- 切换到更早事件，确认早期事件不被污染。
- 切回编辑事件，确认 patch 仍生效。
- 点击还原后，变量恢复捕获原值。

### 推荐自动化方向

后续应补一个 replay 层测试工具或测试命令，至少覆盖：

1. 打开一个固定 `.rdc`。
2. 定位一个已知 D3D11 CBuffer 和变量 offset。
3. 读取原始 bytes。
4. 写入 patch bytes。
5. 立即读回验证。
6. replay 到早期 event，验证 patch 不生效。
7. replay 回目标 event，验证 patch 生效。
8. restore 后验证恢复原始 bytes。

如果 Python replay API 加载不稳定，可以在 `renderdoccmd test` 或专门的内部测试入口中添加 C++ replay 测试。

## 经验教训

- 对 replay 功能，构建通过只是语法验证，不是功能验证。
- CBuffer 看起来像普通 buffer，但 D3D11 的 constant window、dynamic usage、ring buffer 复用都会让简单替换方案失效。
- 资源级 replacement 适合 texture/shader 替换，不一定适合 CBuffer 局部变量调试。
- 对 TA 工具功能，最重要的是“不破坏未修改的数据”。因此 patch 粒度应尽可能小，作用域应尽可能明确。
- 每次修复都应让错误信息更可诊断，避免只显示泛化失败。
