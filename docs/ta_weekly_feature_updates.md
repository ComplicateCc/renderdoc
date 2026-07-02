# TA RenderDoc Weekly Feature Updates

本文记录最近一周 TA RenderDoc 分支内新增能力，便于交付、回归验证和后续排查。

## 2026-06-26 至 2026-07-02 提交概览

| 日期 | Commit | 作者 | 内容 |
| --- | --- | --- | --- |
| 2026-07-01 | `76391bbdf` | 蔡硕 | Add flat normal replacement texture |
| 2026-07-01 | `c3ffd95aa` | 蔡硕 | Use RGBA proxy textures for replacements |
| 2026-06-30 | `19f9ebafc` | 蔡硕 | Add TA performance tree viewer |
| 2026-06-29 | `4c51ca83a` | 蔡硕 | Document TA CBuffer development lessons |
| 2026-06-29 | `3b881956a` | 蔡硕 | Add TA CBuffer editing and performance preview |
| 2026-06-29 | `2362af614` | 蔡硕 | Document texture replacement implementation notes |
| 2026-06-29 | `7a6a30bba` | 蔡硕 | Avoid opening texture tabs during replacement |
| 2026-06-29 | `c364a8618` | 蔡硕 | Use replacements for D3D11 texture previews |
| 2026-06-29 | `226a4bbdd` | 蔡硕 | Refresh texture thumbnails after replacement |
| 2026-06-29 | `1843266dc` | 蔡硕 | Keep D3D11 descriptors canonical after replacement |
| 2026-06-29 | `19e20e95f` | 蔡硕 | Add texture replacement toolbar action |
| 2026-06-29 | `74616d2a4` | 蔡硕 | Refresh D3D11 views for texture replacements |
| 2026-06-29 | `d750d6f29` | 蔡硕 | Support compressed texture replacement formats |
| 2026-06-29 | `90e5a409e` | 蔡硕 | Add replay texture replacement preview |
| 2026-06-29 | `182e7e883` | 蔡硕 | Merge remote-tracking branch `origin/v1.x` into `v1.x` |
| 2026-06-26 | `abd06a8d1` | baldurk | Ignore pipeline caches that are too large for 32-bit chunk size |

## 本次新增：Shader 静态分支精简

### 功能入口

- 在 `Editing XXX Shader` 窗口工具栏新增 `Strip Branches` 按钮。
- 新增 `Keep macros` 复选框，默认不勾选。
- 功能作用于当前正在编辑的 shader 源文件 tab，不会修改只读调试视图。

### 处理规则

- 收集当前文件内的静态 `#define NAME VALUE` 和无值宏定义。
- 支持求值 `#if`、`#ifdef`、`#ifndef`、`#elif`、`#else`、`#endif` 条件块。
- 对可静态确定的分支，移除不会执行的代码路径和对应预处理指令。
- 对包含未知标识符或无法静态求值的动态条件块，保留原始预处理结构。
- 默认移除只用于静态分支判断的原宏定义。
- `Keep macros` 勾选后保留原始 `#define` 行，便于保留宏上下文。
- 若宏仍在普通代码行中被引用，会保留对应 `#define`，避免破坏编译。

### 支持的条件表达式

- 整数和简单浮点字面量。
- `defined(NAME)` 与 `defined NAME`。
- `true`、`false`。
- 逻辑运算：`!`、`&&`、`||`。
- 比较运算：`==`、`!=`、`>`、`<`、`>=`、`<=`。
- 算术运算：`+`、`-`、`*`、`/`、`%`。
- 位运算：`&`、`|`、`^`、`~`、`<<`、`>>`。
- 括号嵌套和宏值递归展开。

### 使用建议

- 先打开 pipeline 里对应 shader 的编辑窗口。
- 点击 `Strip Branches` 对当前源文件执行精简。
- 在 Errors 面板查看输入行数、输出行数、移除宏行数、消除静态分支数等统计信息。
- 如果需要保留原宏定义用于人工对照，先勾选 `Keep macros` 再执行。
- 精简后仍需点击 `Apply changes` 走原有 shader 编译与替换流程。

## 本周功能线汇总

### Texture Replacement

- 增加纹理替换工具栏入口。
- 支持 replay 侧纹理替换预览。
- 支持压缩纹理替换格式。
- D3D11 预览路径改用 replacement 资源。
- 替换后刷新缩略图和相关视图。
- 规范 D3D11 descriptor，降低替换后状态不一致风险。
- 使用 RGBA proxy texture 和 flat normal replacement texture 补充特殊替换场景。

### CBuffer Editing / TA Preview

- 增加 TA CBuffer 编辑能力和 performance preview。
- 补充 CBuffer 编辑开发复盘文档，明确读写闭环验证、局部字节 patch、offset 语义和错误信息要求。

### TA Performance Viewer

- 增加 TA performance tree viewer。
- 补充使用说明文档，方便定位 pass/draw 级性能信息。

## 验证记录

- 已通过 `qrenderdoc_local.vcxproj` Development x64 构建。
- 已通过 `renderdoc.sln` Development x64 完整构建。
- 已生成便携 zip 包：`package/RenderDoc_shader_strip_20260702-130423.zip`。
