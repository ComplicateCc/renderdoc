# Texture Replacement Development Notes

This note records implementation details and pitfalls from adding live texture replacement preview in
qrenderdoc. It is intended as a maintenance reference for future work on similar replay-time resource
editing features.

## Feature Summary

The implementation adds replay-time texture replacement without modifying the RDC file:

- `IReplayController::ReplaceTexture(const TextureReplacement &replacement)` creates a proxy texture,
  uploads replacement pixels, and registers a resource replacement.
- `TextureReplacement` supports image files handled by `stb_image` (including PNG/TGA) and built-in
  debug textures: black, white, grey, and checkerboard.
- Uncompressed regular formats and common compressed formats are supported for preview:
  - BC1, BC3, BC7 use Compressonator block encoders.
  - ASTC uses ASTC 4x4 constant-color blocks for fast preview/debug replacement.
- qrenderdoc exposes this through the Texture Viewer toolbar `Replace...` button.

## Important Commits

- `90e5a409e` - Add replay texture replacement preview.
- `d750d6f29` - Support compressed texture replacement formats.
- `74616d2a4` - Refresh D3D11 views for texture replacements.
- `19e20e95f` - Add texture replacement toolbar action.
- `1843266dc` - Keep D3D11 descriptors canonical after replacement.
- `226a4bbdd` - Refresh texture thumbnails after replacement.
- `c364a8618` - Use replacements for D3D11 texture previews.
- `7a6a30bba` - Avoid opening texture tabs during replacement.

## Pitfalls and Fixes

### Replacing only the texture resource is not enough

In D3D11, draw calls bind SRV/UAV/RTV view objects, not just the underlying texture resource. Replacing
only the texture makes some direct resource paths work, but the real draw can continue to use the old
view.

Fix:

- `D3D11Replay::ReplaceResource()` now creates matching replacement SRV/RTV/UAV objects for derived
  views of the original texture.
- The derived views are also registered with the resource manager so replayed draws use the replacement.
- `D3D11Replay::RemoveReplacement()` removes replacement mappings for derived views.

### Pipeline/UI descriptors must stay canonical

After view replacement, D3D11 pipeline state queries can return replay-only replacement IDs. These IDs
are not in the original capture texture list, so qrenderdoc Inputs could disappear or show empty.

Fix:

- D3D11 descriptor reporting maps replacement IDs back through `GetUnreplacedID()` before returning
  `Descriptor.resource` and `Descriptor.view` to UI code.
- This keeps Inputs/Outputs showing the original captured resources while replay uses replacements.

### Texture Viewer thumbnails use a separate preview path

The right-side Inputs thumbnails are rendered through `ReplayOutput::DrawThumbnail()` and D3D11 texture
preview shaders. This path uses `D3D11DebugManager::GetShaderDetails()`, which originally looked up the
exact original texture ID and ignored replacement mappings.

Fix:

- `D3D11DebugManager::GetShaderDetails()` resolves the live replacement resource before looking up
  texture details and cached SRVs.
- D3D11 texture preview typeless handling now checks proxy original info using the live replacement ID.
- `ReplayOutput::ClearThumbnails()` now also clears thumbnail generator handles after destroying them.
- `ReplayController::ReplaceTexture()` and `RemoveReplacement()` clear thumbnail outputs/generators.

### UI replacement must not open a locked texture tab

Calling `ViewTexture()` from a replacement action can create or switch to a locked texture tab if the
current Texture Viewer tab is locked. That made later double-clicks appear unable to switch the main
preview until the extra tab/window was closed.

Fix:

- Toolbar and context menu replacement actions now call resource-specific helper functions directly:
  - `replaceTextureFile(ResourceId id)`
  - `replaceTextureBuiltin(ResourceId id, TextureReplacementType type)`
  - `removeTextureReplacement(ResourceId id)`
- Replacement no longer calls `ViewTexture()` and only refreshes the current event, current preview,
  and active thumbnails.

### Compressed formats need block-sized data

Compressed formats require block-compressed upload data, not RGBA pixels. Non-multiple-of-four mips must
be edge-clamped when building 4x4 blocks.

Fix:

- BC1/BC3/BC7 replacement mips are block encoded from RGBA8 with edge clamping.
- ASTC preview uses valid ASTC constant-color blocks with averaged per-block color.
- Unsupported compressed formats still return `ImageUnsupported` instead of attempting unsafe uploads.

## Validation Commands

Use Visual Studio 2022 MSBuild from the repository root:

```powershell
& "C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\amd64\MSBuild.exe" .\renderdoc.sln /m /p:Configuration=Development /p:Platform=x64 /p:PlatformToolset=v143 /v:minimal
```

A useful CLI smoke test is to compile a temporary replay program that:

1. Opens the target RDC.
2. Finds a texture used as `PS_Resource` at a draw.
3. Calls `IReplayOutput::DrawThumbnail()` for the original texture.
4. Calls `ReplaceTexture()` with a white/debug texture.
5. Calls `DrawThumbnail()` again for the same original texture ID.
6. Verifies the thumbnail hashes differ.

The verified local result for the supplied RDC was:

```text
event=498 before=<hash> after=<hash> changed=1 size=49152/49152
```

Also validate final render impact by saving an output texture before/after replacement and comparing
hashes. The expected result is that output hashes differ while the original input resource remains
listed as a `PS_Resource`.

## Current Limitations

- The D3D11 path has been fully exercised for the supplied capture.
- D3D12 and Vulkan have different descriptor/resource replacement models and need separate validation.
- Vulkan currently has `VulkanReplay::CreateProxyTexture()` unimplemented, so `ReplaceTexture()` will
  return unsupported there until proxy texture creation is implemented.
- ASTC support is intended for fast preview/debug replacement, not high-quality ASTC recompression.

## Guidance for Future Resource Editing Features

- Always consider derived/bound objects, not just the underlying resource.
- Keep UI-facing descriptors canonical so qrenderdoc can still find original captured resources.
- Check all preview paths separately: main render output, Texture Viewer preview, Inputs/Outputs
  thumbnails, SaveTexture/GetTextureData, pixel picking, and buffer-as-texture views can take different
  code paths.
- Add CLI validation for both visible output changes and UI/resource-list invariants when possible.
- Avoid calling UI navigation helpers like `ViewTexture()` from mutation actions unless changing tabs is
  explicitly intended.
