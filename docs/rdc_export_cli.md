# RDC 渲染资源导出 CLI

`util/rdc_export/rdc_export.py` 是一个不依赖 qrenderdoc GUI 的离线导出工具。它直接加载仓库构建出的 RenderDoc Python binding，可以处理 PC 捕获，也可以通过 RenderDoc remote replay 在 Android 设备上处理移动端捕获。

## 环境要求

- Windows x64。
- 与 `x64/Development/pymodules/renderdoc.pyd` ABI 匹配的 Python。本机当前使用 Python 3.14。
- 已构建 `x64/Development/renderdoc.dll` 和 `x64/Development/pymodules/renderdoc.pyd`。
- Android 远程重放需要 `adb devices` 能看到兼容设备，并允许安装/启动 RenderDoc remote server APK。
- Android 本地软件重放需要 SwiftShader。工具可自动查找 Chrome、Arm Performance Studio、Edge 等软件附带的 `vk_swiftshader_icd.json`，也可通过 `--vulkan-icd` 显式指定。

## 快速开始

PowerShell 启动器：

```powershell
.\util\rdc_export\rdc-export.ps1 `
  -Capture "D:\Captures\frame.rdc" `
  -Output ".\exports\frame" `
  -Preset analysis
```

直接调用 Python：

```powershell
& "C:\Users\caishuo01\AppData\Local\Programs\Python\Python314\python.exe" `
  .\util\rdc_export\rdc_export.py `
  "D:\Captures\frame.rdc" `
  --output ".\exports\frame" `
  --preset analysis
```

## Preset

| Preset | 内容 | 适用场景 |
| --- | --- | --- |
| `metadata` | 捕获信息、缩略图、section、action、pass、资源清单 | 快速盘点大捕获 |
| `analysis` | `metadata` + 每事件 Pipeline、Shader、descriptor binding | 默认分析 |
| `full` | `analysis` + 引用纹理、Buffer 范围、CBuffer、Post-VS | 选定事件的完整取证 |

PC 捕获可能有数千纹理和 Buffer。建议先跑 `metadata`，再用 `--event`、`--event-range` 或 `--pass-index` 缩小范围后跑 `full`。

## 典型命令

只导出一个 draw 的完整数据：

```powershell
.\util\rdc_export\rdc-export.ps1 `
  -Capture "D:\Captures\frame.rdc" `
  -Output ".\exports\frame_eid_153" `
  -Preset full `
  -ExtraArgs @("--event", "153", "--max-textures", "32", "--max-buffers", "128")
```

导出事件区间：

```powershell
.\util\rdc_export\rdc-export.ps1 `
  -Capture "D:\Captures\frame.rdc" `
  -Output ".\exports\frame_1000_1200" `
  -Preset full `
  -ExtraArgs @("--event-range", "1000:1200")
```

只导出引用纹理为 PNG：

```powershell
.\util\rdc_export\rdc-export.ps1 `
  -Capture "D:\Captures\frame.rdc" `
  -Output ".\exports\textures" `
  -Preset analysis `
  -ExtraArgs @("--textures", "referenced", "--texture-format", "png")
```

DDS 是默认格式，会尽量保留 mip、数组层和压缩格式；PNG 只导出 mip 0、slice 0，并对 MSAA 做 resolve。

## Android 捕获

移动端 Vulkan 捕获经常依赖桌面 GPU 不支持的扩展或 ETC2/ASTC 压缩格式。工具提供两条路径：

1. `--vulkan-software-replay`：自动选择 SwiftShader，在本机做 best-effort 软件重放。适合导出 action、Shader、descriptor、CBuffer、Buffer、纹理和 Post-VS 数据。
2. `--remote adb://SERIAL`：在兼容 Android GPU 上远程重放。适合需要更高画面准确性的分析。

本地软件重放命令：

```powershell
.\util\rdc_export\rdc-export.ps1 `
  -Capture "E:\Projects\AI\renderdoc\tmp_rdc_analysis\1. 野外 - 流畅.rdc" `
  -Output ".\exports\android_smooth" `
  -Preset full `
  -ExtraArgs @("--vulkan-software-replay", "--event", "113")
```

如自动查找不到 SwiftShader：

```powershell
... -ExtraArgs @(
  "--vulkan-software-replay",
  "--vulkan-icd", "C:\path\to\vk_swiftshader_icd.json"
)
```

软件重放会显式禁用 replay 设备不支持但捕获中启用的 feature、忽略 fragment-density attachment，并扩大 replay memory allocation 以容纳 SwiftShader 解压后的 ASTC/ETC2 资源。所有这些行为默认关闭，只在 `--vulkan-software-replay` 下启用。

该路径用于数据提取，不保证像素精确。SwiftShader 可能对部分移动端 depth format 输出 warning，因此最终颜色、深度和性能结果不能当成原 Android GPU 的准确结果；原始资源字节、Shader、descriptor offset 和结构化元数据仍可用于离线分析。

若不使用软件重放，工具会先尝试普通本地重放；失败时仍会导出捕获容器元数据、section 和缩略图，并在 `manifest.json` 中写入完整 RenderDoc 错误。

连接设备后查看序列号：

```powershell
adb devices -l
```

使用 Android 设备远程重放：

```powershell
.\util\rdc_export\rdc-export.ps1 `
  -Capture "E:\Projects\AI\renderdoc\tmp_rdc_analysis\1. 野外 - 流畅.rdc" `
  -Output ".\exports\android_smooth" `
  -Preset analysis `
  -Remote "adb://DEVICE_SERIAL"
```

启动器会通过 RenderDoc 的 `DeviceProtocolController` 尝试启动 remote server，然后把 RDC 上传到设备并在设备 GPU 上重放。若设备已经手动启动 remote server，可加 `--no-start-remote`。

参考 Android 捕获在 RTX 4080 硬件 replay 上会因为缺少 `VK_EXT_fragment_density_map` 被拒绝；使用 `--vulkan-software-replay` 已在本机完成 EID 113 的完整资源导出。若要求画面准确，仍建议使用兼容 Android 设备 remote replay。

## 输出目录

```text
manifest.json                 总状态、API、统计和错误数量
summary.txt                   人类可读摘要
capture/                      捕获元数据、section、缩略图
actions/                      action 树和推导出的连续 pass
resources/                    全部 texture/buffer/resource 清单
events/                       选定事件的 Pipeline JSON/CSV
shaders/                      原始 DXBC/DXIL/SPIR-V、反汇编、源码、反射
bindings/                     descriptor、资源 ID、absolute byte offset/size
cbuffers/                     CBuffer 布局、解码值和原始字节
textures/                     可选 DDS/PNG 等实际纹理文件
buffers/                      可选 Buffer 原始范围
meshes/                       可选 Post-VS 原始顶点/索引和 CSV
debug_messages.json           RenderDoc replay debug messages
errors.json                   单资源/单事件错误，不隐藏部分失败
```

所有 CBuffer 和 Buffer 记录都明确保存 `resourceId`、`absoluteByteOffset` 和 `byteSize`。descriptor offset 是 buffer 绝对偏移，不是变量相对 offset；变量相对布局在 CBuffer `layout[].byteOffset` 中单独记录。

## 常用限制参数

- `--max-events N`：最多处理 N 个执行事件。
- `--max-resource-bytes 512MiB`：单资源/范围上限。
- `--max-total-bytes 8GiB`：实际导出总量上限。
- `--max-instances N`：每个 draw 最多导出 N 个 Post-VS instance。
- `--max-mesh-rows N`：每个 Post-VS CSV 最大行数。
- `--strict`：任何单项错误都使命令失败。
- `--allow-partial`：重放不可用时，保留容器元数据并返回成功状态。
- `--overwrite`：允许覆盖已有 `manifest.json` 的目录；建议仍使用新目录避免旧文件残留。

## 已验证捕获

- PC/D3D11：`tmp_rdc_analysis/pc_13th Gen Intel(R) Core(TM) i9-13900KF_NVIDIA GeForce RTX 4080_07.08_17.51.15_frame22127.rdc`。
- Android/Vulkan：`tmp_rdc_analysis/1. 野外 - 流畅.rdc`。已使用 `--vulkan-software-replay --event 113 --preset full` 验证 SPIR-V、descriptor、CBuffer、ASTC DDS、Buffer 和 Post-VS 导出，错误数为 0。
