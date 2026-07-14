# RenderDoc 帧资源恢复与 Blender 导出

`util/renderdoc_scene_export` 提供独立 CLI，用 replay API 将一个 Colour Pass 中的 post-VS 网格、纹理、基础材质和 shader 资源关系导出到 Blender 5.1。

## 快速使用

```powershell
& .\util\renderdoc_scene_export\export_colour_pass.ps1
```

默认示例为：

- 捕获：`C:\Renderdoc\yy_极致_高帧率.rdc`
- Pass：`Colour Pass #3 (6 Targets + Depth)`
- Blender：`C:\Program Files\Blender Foundation\Blender 5.1\blender.exe`
- 输出：`C:\Renderdoc\yy_极致_高帧率_blender_export`

直接运行 Python：

```powershell
& "C:\Users\caishuo01\AppData\Local\Programs\Python\Python314\python.exe" `
  .\util\renderdoc_scene_export\rdoc_scene_export.py `
  --capture "C:\Renderdoc\yy_极致_高帧率.rdc" `
  --output "C:\Renderdoc\yy_极致_高帧率_blender_export" `
  --colour-pass 3 `
  --blender "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
```

## 输出结构

- `scene.blend`：Blender 原生场景，摄像机位于原点。
- `scene.fbx`：包含全部 draw 的合并 FBX。
- `fbx/eid_XXXXXX.fbx`：每个 draw 的独立 FBX。
- `textures/resource_*.png`：mip 0 纹理；默认导出首个 array slice。
- `shaders/*.txt`：唯一 VS/PS 的 RenderDoc 反汇编。
- `meshes/eid_XXXXXX/`：相机相对坐标、三角形、UV、法线和原始 post-VS 数据。
- `scene_manifest.json`：action、shader、descriptor、纹理和材质引用关系。
- `camera_calibration.json`：共享 `clipFromWorld`、相机位置、交叉验证误差和原始 CBuffer 证据。
- `blender_validation.json`：在全新 Blender 进程中重新导入 `scene.fbx` 的计数验证。

## 坐标恢复

工具会在目标 Pass 的高权重 draw 中搜索可作为世界坐标的 VS 输出，拟合共享 `clipFromWorld`，并要求至少另一个 draw 的输出通过交叉验证。随后所有 draw 都通过 post-VS clip position 和逆矩阵恢复到同一世界空间，再减去捕获摄像机位置。

如果自动标定失败，可以指定已知输出：

```powershell
--calibration-event 2509 --world-output 0
```

`world-output` 是排除 `Position` 后的 post-VS 输出索引。也可以在配置文件的 `camera.clipFromWorld` 中直接提供 4x4 矩阵。

坐标单位保持为 capture world-coordinate units，不声明与米的换算。默认将 capture Y-up 的 `(X,Y,Z)` 转为 Blender Z-up 的 `(X,-Z,Y)`。

## 材质与透明裁剪

- 默认按 Pixel Shader 只读纹理的 binding 顺序，将第一个可导出的纹理作为 diffuse。
- 检测 shader 反汇编中的 `Kill`、`discard`、`OpKill` 或 `Demote`，在 Blender 中使用 alpha clip 材质。
- 未识别 UV 或法线时，FBX 仍会导出几何体；Blender 会使用默认 UV 或重算法线。
- shader 只整理反汇编和资源引用，不在 Blender 中恢复 shader 逻辑。

## 自定义扩展

复制 `util/renderdoc_scene_export/example_config.json` 后使用 `--config`：

- `pass.colourTargetCount` / `pass.requireDepth`：验证目标 Pass 附件。
- `attributes.shaderOverrides.<VS resource id>.uvOutput`：指定 UV 输出。
- `attributes.shaderOverrides.<VS resource id>.normalOutput`：指定法线输出。
- `materials.shaderOverrides.<PS resource id>.diffuseTextureSlot`：覆盖 diffuse 槽位。
- `textures.stages`：选择导出哪些 shader stage 的纹理。
- `textures.allSlices`：导出 texture array 的全部 slice，仍只导出 mip 0。
- `blender.flipV` / `blender.scale` / `blender.perDrawFbx`：控制 Blender 组装。

resource id 可写为 `ResourceId::61885` 或 `61885`。

完整构建 `renderdoc.sln` 后，默认项目可能把 `renderdoc.pyd` 重建为依赖 `python36.dll`。运行本 CLI 前应按 `.codex/skills/renderdoc-capture-analysis/SKILL.md` 使用 `build_tools/python314_override` 重建 `pyrenderdoc_module.vcxproj`；可用 `dumpbin /dependents` 确认依赖为 `python314.dll`。

## 当前边界

- 支持 Triangle List、Triangle Strip 和 Triangle Fan。
- 自动世界空间恢复需要捕获中至少有可交叉验证的 world-position VS 输出；否则必须提供标定事件或矩阵。
- 第一纹理槽只是默认材质启发式，复杂材质、虚拟纹理、bindless 动态索引需要配置覆盖或后续插件扩展。
- 纹理导出按首次遇到该 resource id 时的内容保存；manifest 保留首次 event 和 descriptor 关系。
