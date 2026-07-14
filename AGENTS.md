# RenderDoc TA Extension Development Guide

本文件适用于整个仓库。后续修改 RenderDoc TA 向功能时，除了通用代码规范，还必须遵守以下验证要求。

## CBuffer 编辑功能

修改 CBuffer 编辑、buffer replacement、D3D11/D3D12/GL/Vulkan replay buffer 读写路径时，不能只依赖编译通过。必须验证运行时读写闭环。

### 必须验证的闭环

每次修改后至少确认：

1. 修改前能读取目标 CBuffer 变量原始值。
2. 写入新值后，立即从 replay 层读回同一 `resourceId + byteOffset + type + components`。
3. 读回 bytes 与写入 bytes 完全一致。
4. CBuffer 面板刷新后目标变量显示为新值。
5. 目标变量前后相邻字段不变。
6. 矩阵字段不整体错位、不串行偏移。
7. 更早 event 不被当前 patch 污染。
8. 还原后恢复捕获原始值。

### 实现原则

- 优先使用“局部字节范围 patch”，不要保存/替换整块 CBuffer 快照。
- 不要为了修改一个变量替换整个 D3D11 buffer resource object，除非已验证不会改变 `FirstConstant` / `NumConstants` / descriptor offset。
- D3D11 dynamic buffer 写回必须考虑 `D3D11_USAGE_DYNAMIC + D3D11_CPU_ACCESS_WRITE`，这类 buffer 应使用 `Map(D3D11_MAP_WRITE_DISCARD)` 路径。
- offset 语义必须写清楚：区分 CBuffer 相对 offset、buffer 绝对 offset、descriptor range offset、viewer paging offset。
- 对矩阵、数组、结构体等复杂布局，除非已验证 stride/padding/row-major/column-major，否则不要开放直接编辑。

### 错误信息要求

CBuffer 写入/读回失败时，错误信息至少包含：

- `resourceId`
- absolute `byteOffset`
- 写入 size
- `VarType`
- component count

如果后续继续排查，优先扩展错误信息，而不是只返回通用失败。

## 构建验证

Windows 上优先使用：

```powershell
& "C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\amd64\MSBuild.exe" .\renderdoc.sln /m /p:Configuration=Development /p:Platform=x64 /p:PlatformToolset=v143 /v:minimal
```

如只验证 qrenderdoc 相关改动，可先跑：

```powershell
& "C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\amd64\MSBuild.exe" .\qrenderdoc\qrenderdoc_local.vcxproj /m /p:Configuration=Development /p:Platform=x64 /p:PlatformToolset=v143 /p:SolutionDir="E:\Projects\AI\renderdoc\" /v:minimal
```

最终交付前仍应跑完整 solution。

## 文档

CBuffer 调试功能相关复盘见：

```text
docs/ta_renderdoc_cbuffer_development_retrospective.md
```

TA Performance Viewer 使用说明见：

```text
docs/ta_performance_viewer.md
```

## RenderDoc Capture Analysis

分析 `.rdc` 截帧、drawcall、shader、pipeline、CBuffer、post-VS 网格、地形世界坐标、距离或边界时，先阅读：

```text
.codex/skills/renderdoc-capture-analysis/SKILL.md
```

需要给出可复核结论时，必须保存 action、descriptor resource/absolute byte offset、raw CBuffer bytes、post-VS resource/index data、矩阵回代误差和最终统计。除非捕获或游戏资料明确单位比例，不要将 capture world coordinate units 直接声称为米。