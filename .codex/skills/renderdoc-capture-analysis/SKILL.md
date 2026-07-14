---
name: renderdoc-capture-analysis
description: Analyze RenderDoc `.rdc` captures headlessly with the local RenderDoc Python binding. Use for draw-call, terrain, mesh, shader, pipeline, constant-buffer, post-VS, world-space bounds, camera-distance, resource-binding, or replay-evidence investigations in this repository.
---

# RenderDoc Capture Analysis

Use this skill for evidence-based capture analysis. Prefer direct `renderdoc` Python API calls over GUI inspection when a conclusion must be reproducible.

## Environment

1. Use `x64/Development/pymodules/renderdoc.pyd` with the matching Python ABI.
2. On this machine, run Python 3.14 and add both `x64/Development` and `x64/Development/pymodules` through `os.add_dll_directory` before importing `renderdoc`.
3. Verify the binding dependency before opening a capture. It must be `python314.dll`, not `python36.dll`.
4. Rebuild `qrenderdoc\Code\pyrenderdoc\pyrenderdoc_module.vcxproj` with `VSPythonOverridePath=build_tools\python314_override` if the binding is stale.

## Draw-Call Workflow

1. Open the capture, assert local replay support, and save action metadata.
2. Set the event and save pipeline state, shader reflection, descriptor resource IDs, descriptor byte offsets, and byte sizes.
3. For CBuffers, read raw bytes with `GetBufferData(descriptor.resource, descriptor.byteOffset, descriptor.byteSize)`. Do not pass offset zero unless the descriptor offset is zero.
4. For world-space geometry, use post-VS output. Record its vertex resource, byte offset, stride, index resource, and index stride.
5. State every coordinate-space assumption and verify it numerically. Project the claimed world position with the captured matrix and compare it to post-VS `gl_Position`.
6. Report exact capture-coordinate bounds and both 3D and horizontal ranges. Do not call values metres unless the capture or game establishes the unit scale.

## Terrain Analysis

Run the bundled script for instanced terrain draws whose post-VS layout is `gl_Position` followed by a world-position `float4`:

```powershell
$env:PYTHONPATH = "E:\Projects\AI\renderdoc\x64\Development\pymodules"
$env:PATH = "E:\Projects\AI\renderdoc\x64\Development;$env:PATH"
& "C:\Users\caishuo01\AppData\Local\Programs\Python\Python314\python.exe" `
  .\.codex\skills\renderdoc-capture-analysis\scripts\analyze_terrain_draw.py `
  --capture "D:\Renderdoc\frame.rdc" --event 1026 --output .\analysis\frame_eid1026
```

The script writes `terrain_evidence.json`, including raw-resource hashes, CBuffer offsets, matrices, camera reconstruction, post-VS projection error, world bounds, triangle counts, and distance metrics. Treat `verification.verified` as mandatory before presenting the world-space conclusion as exact.

## Compatibility Notes

- Current bindings expose a `Descriptor` resource as `descriptor.resource`, not `descriptor.resourceId`.
- Old CLI-Anything helpers may return all-zero CBuffer variables because they omit descriptor byte offsets. Use the raw-byte path above for proof-sensitive work.
- If a Python module rebuild is required under Codex, remove duplicate `Path`/`PATH` environment entries and disable MSBuild file tracking before rebuilding. Preserve the rebuild log.
## FBX Export

Use `scripts/export_terrain_fbx.py` after terrain evidence has passed validation. It exports every non-degenerate post-VS terrain triangle in capture world coordinates and adds a separately named camera-position sphere.

```powershell
& "C:\Users\caishuo01\AppData\Local\Programs\Python\Python314\python.exe" `
  .\.codex\skills\renderdoc-capture-analysis\scripts\export_terrain_fbx.py `
  --evidence .\analysis\frame_eid1026\terrain_evidence.json `
  --vertices .\analysis\frame_eid1026\postvs_vertices_raw.bin `
  --indices .\analysis\frame_eid1026\postvs_indices_raw.bin `
  --output .\analysis\frame_eid1026\terrain_postvs_with_camera.fbx
```

The exporter verifies the post-VS SHA-256 and non-degenerate triangle count before writing FBX. Keep the default sphere radius of 32 capture units unless a different scene-scale marker is required.
## Blender-Compatible FBX

Blender 5.1 does not import ASCII FBX. Use Blender's own binary FBX writer instead of `export_terrain_fbx.py` when the target is Blender:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --factory-startup `
  --python .\.codex\skills\renderdoc-capture-analysis\scripts\export_terrain_fbx_blender.py -- `
  --evidence .\analysis\frame_eid1026\terrain_evidence.json `
  --vertices .\analysis\frame_eid1026\postvs_vertices_raw.bin `
  --indices .\analysis\frame_eid1026\postvs_indices_raw.bin `
  --output .\analysis\frame_eid1026\terrain_postvs_with_camera.fbx
```

The Blender-compatible exporter maps capture `(X,Y,Z)` with Y-up to Blender `(X,-Z,Y)` with Z-up, exports binary FBX, and stores the original capture camera position as a custom property on the marker sphere.
## Blender Visible Export

For a file that opens visibly in Blender's default viewport, use `scripts/export_terrain_fbx_blender_visual.py`. It recentres coordinates on the capture camera, applies a visual scale of `0.1`, assigns default terrain and camera-marker materials, and writes a `.blend` plus a rendered PNG for visual verification. This version preserves all terrain-to-camera relative distances but does not preserve absolute capture coordinates in the FBX scene.