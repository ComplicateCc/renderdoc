"""RenderDoc Python-API backend — wraps the renderdoc module for replay & analysis.

This module provides high-level wrappers around the renderdoc Python module
(SWIG bindings). It requires that renderdoc is installed and the Python module
is importable.  All functions return plain dicts suitable for JSON serialisation.
"""

from __future__ import annotations

import os
import struct
import sys
from typing import Any, Dict, List, Optional, Tuple


def _import_rd():
    """Import and return the renderdoc module, raising a clear error if missing."""
    try:
        import renderdoc as rd
        return rd
    except ImportError:
        raise RuntimeError(
            "The 'renderdoc' Python module is not importable.\n"
            "Ensure RenderDoc is installed and its Python bindings are on PYTHONPATH.\n"
            "  Windows: add <RenderDoc install dir> to PYTHONPATH\n"
            "  Linux:   export PYTHONPATH=/usr/share/renderdoc/pymodules:$PYTHONPATH"
        )


# ---------------------------------------------------------------------------
# Capture file operations
# ---------------------------------------------------------------------------

def open_capture(rdc_path: str) -> Tuple:
    """Open an .rdc capture and return (cap, controller, rd).

    Caller is responsible for calling controller.Shutdown() and cap.Shutdown().
    """
    rd = _import_rd()
    rd.InitialiseReplay(rd.GlobalEnvironment(), [])

    cap = rd.OpenCaptureFile()
    result = cap.OpenFile(rdc_path, "", None)
    if result != rd.ResultCode.Succeeded:
        cap.Shutdown()
        rd.ShutdownReplay()
        raise RuntimeError(f"Couldn't open '{rdc_path}': {result}")

    if not cap.LocalReplaySupport():
        cap.Shutdown()
        rd.ShutdownReplay()
        raise RuntimeError(f"Capture '{rdc_path}' cannot be replayed locally")

    result, controller = cap.OpenCapture(rd.ReplayOptions(), None)
    if result != rd.ResultCode.Succeeded:
        cap.Shutdown()
        rd.ShutdownReplay()
        raise RuntimeError(f"Couldn't initialise replay for '{rdc_path}': {result}")

    return cap, controller, rd


def close_capture(cap, controller, rd):
    """Cleanly shut down a replay session."""
    if controller:
        controller.Shutdown()
    if cap:
        cap.Shutdown()
    rd.ShutdownReplay()


# ---------------------------------------------------------------------------
# Capture info
# ---------------------------------------------------------------------------

def get_capture_info(rdc_path: str) -> Dict[str, Any]:
    """Return metadata about a capture file without full replay."""
    rd = _import_rd()
    rd.InitialiseReplay(rd.GlobalEnvironment(), [])

    cap = rd.OpenCaptureFile()
    result = cap.OpenFile(rdc_path, "", None)
    if result != rd.ResultCode.Succeeded:
        cap.Shutdown()
        rd.ShutdownReplay()
        raise RuntimeError(f"Couldn't open '{rdc_path}': {result}")

    info = {
        "path": rdc_path,
        "file_size": os.path.getsize(rdc_path),
        "local_replay_support": cap.LocalReplaySupport(),
        "driver_name": str(cap.DriverName()) if hasattr(cap, "DriverName") else "unknown",
        "section_count": cap.GetSectionCount() if hasattr(cap, "GetSectionCount") else -1,
    }

    # Attempt to list sections
    if hasattr(cap, "GetSectionCount") and hasattr(cap, "GetSectionProperties"):
        sections = []
        for i in range(cap.GetSectionCount()):
            props = cap.GetSectionProperties(i)
            sections.append({
                "index": i,
                "name": str(props.name),
                "type": str(props.type),
            })
        info["sections"] = sections

    cap.Shutdown()
    rd.ShutdownReplay()
    return info


# ---------------------------------------------------------------------------
# Actions / draw calls
# ---------------------------------------------------------------------------

def _action_to_dict(action, structured_file=None) -> Dict[str, Any]:
    """Convert an ActionDescription to a JSON-friendly dict."""
    d = {
        "eventId": action.eventId,
        "flags": int(action.flags),
        "numIndices": action.numIndices,
        "numInstances": action.numInstances,
    }
    if structured_file:
        try:
            d["name"] = action.GetName(structured_file)
        except Exception:
            d["name"] = f"Event {action.eventId}"
    else:
        d["name"] = f"Event {action.eventId}"

    d["childCount"] = len(action.children)
    return d


def list_actions(rdc_path: str, flat: bool = False) -> Dict[str, Any]:
    """List all root-level actions (draw calls) in a capture.

    Args:
        rdc_path: Path to the .rdc file.
        flat: If True, flatten the action tree recursively.

    Returns:
        Dict with action list.
    """
    cap, controller, rd = open_capture(rdc_path)
    try:
        sf = controller.GetStructuredFile()
        root_actions = controller.GetRootActions()

        if flat:
            all_actions = []

            def _flatten(actions):
                for a in actions:
                    all_actions.append(_action_to_dict(a, sf))
                    if len(a.children) > 0:
                        _flatten(a.children)

            _flatten(root_actions)
            return {"path": rdc_path, "count": len(all_actions), "actions": all_actions}
        else:
            actions = [_action_to_dict(a, sf) for a in root_actions]
            return {"path": rdc_path, "count": len(actions), "actions": actions}
    finally:
        close_capture(cap, controller, rd)


# ---------------------------------------------------------------------------
# Textures
# ---------------------------------------------------------------------------

def list_textures(rdc_path: str) -> Dict[str, Any]:
    """List all textures in a capture."""
    cap, controller, rd = open_capture(rdc_path)
    try:
        textures = controller.GetTextures()
        tex_list = []
        for t in textures:
            tex_list.append({
                "resourceId": str(int(t.resourceId)),
                "width": t.width,
                "height": t.height,
                "depth": t.depth,
                "mips": t.mips,
                "arraysize": t.arraysize,
                "format": str(t.format),
                "dimension": t.dimension,
                "creationFlags": int(t.creationFlags),
            })
        return {"path": rdc_path, "count": len(tex_list), "textures": tex_list}
    finally:
        close_capture(cap, controller, rd)


def save_texture(
    rdc_path: str,
    resource_id: int,
    output_path: str,
    file_type: str = "png",
    event_id: Optional[int] = None,
    mip: int = 0,
    slice_index: int = 0,
) -> Dict[str, Any]:
    """Save a texture from a capture to disk.

    Args:
        rdc_path: Path to the .rdc file.
        resource_id: The ResourceId of the texture (as int).
        output_path: Destination file path.
        file_type: Output type: png, jpg, bmp, tga, hdr, dds.
        event_id: Event to move to before saving (optional).
        mip: Mip level to save (0-based), or -1 for all (DDS only).
        slice_index: Array slice to save (0-based), or -1 for all (DDS only).

    Returns:
        Dict with result status.
    """
    cap, controller, rd = open_capture(rdc_path)
    try:
        # Navigate to event if specified
        if event_id is not None:
            controller.SetFrameEvent(event_id, True)

        type_map = {
            "png": rd.FileType.PNG,
            "jpg": rd.FileType.JPG,
            "bmp": rd.FileType.BMP,
            "tga": rd.FileType.TGA,
            "hdr": rd.FileType.HDR,
            "dds": rd.FileType.DDS,
        }
        ft = type_map.get(file_type.lower(), rd.FileType.PNG)

        texsave = rd.TextureSave()
        texsave.resourceId = rd.ResourceId.MakeFromInt(resource_id) if hasattr(rd.ResourceId, "MakeFromInt") else rd.ResourceId()
        # Fallback: directly set if MakeFromInt not available
        if not hasattr(rd.ResourceId, "MakeFromInt"):
            texsave.resourceId = resource_id

        texsave.destType = ft
        texsave.mip = mip
        texsave.slice.sliceIndex = slice_index
        texsave.alpha = rd.AlphaMapping.Preserve

        controller.SaveTexture(texsave, output_path)

        success = os.path.isfile(output_path) and os.path.getsize(output_path) > 0
        return {
            "success": success,
            "output": output_path,
            "file_size": os.path.getsize(output_path) if success else 0,
            "file_type": file_type,
        }
    finally:
        close_capture(cap, controller, rd)


# ---------------------------------------------------------------------------
# Pipeline state
# ---------------------------------------------------------------------------

def get_pipeline_state(rdc_path: str, event_id: int) -> Dict[str, Any]:
    """Get the pipeline state at a specific event.

    Args:
        rdc_path: Path to the .rdc file.
        event_id: The event ID to inspect.

    Returns:
        Dict describing the pipeline state.
    """
    cap, controller, rd = open_capture(rdc_path)
    try:
        controller.SetFrameEvent(event_id, True)
        state = controller.GetPipelineState()

        result = {
            "path": rdc_path,
            "eventId": event_id,
            "graphics_pipeline": str(state.GetGraphicsPipelineObject()) if hasattr(state, "GetGraphicsPipelineObject") else "N/A",
        }

        # Shader stages
        stages = [
            ("vertex", rd.ShaderStage.Vertex),
            ("fragment", rd.ShaderStage.Fragment if hasattr(rd.ShaderStage, "Fragment") else rd.ShaderStage.Pixel),
        ]
        for name, stage in stages:
            try:
                refl = state.GetShaderReflection(stage)
                if refl is not None:
                    result[f"{name}_shader"] = {
                        "entry_point": str(state.GetShaderEntryPoint(stage)),
                        "resourceId": str(int(refl.resourceId)),
                    }
                else:
                    result[f"{name}_shader"] = None
            except Exception:
                result[f"{name}_shader"] = None

        # Render targets
        try:
            outputs = controller.GetRootActions()
            # Find the action matching event_id
            def find_action(actions, eid):
                for a in actions:
                    if a.eventId == eid:
                        return a
                    found = find_action(a.children, eid)
                    if found:
                        return found
                return None

            action = find_action(outputs, event_id)
            if action:
                result["outputs"] = [str(int(o)) for o in action.outputs if int(o) != 0]
                result["depthOutput"] = str(int(action.depthOut)) if int(action.depthOut) != 0 else None
        except Exception:
            pass

        return result
    finally:
        close_capture(cap, controller, rd)


# ---------------------------------------------------------------------------
# Shaders
# ---------------------------------------------------------------------------

def disassemble_shader(
    rdc_path: str,
    event_id: int,
    stage: str = "pixel",
    target_index: int = 0,
) -> Dict[str, Any]:
    """Disassemble a shader at a specific event.

    Args:
        rdc_path: Path to the .rdc file.
        event_id: The event ID.
        stage: Shader stage: vertex, pixel/fragment, compute, geometry, hull, domain.
        target_index: Index of the disassembly target format.

    Returns:
        Dict with disassembly text.
    """
    cap, controller, rd = open_capture(rdc_path)
    try:
        controller.SetFrameEvent(event_id, True)
        state = controller.GetPipelineState()

        stage_map = {
            "vertex": rd.ShaderStage.Vertex,
            "pixel": rd.ShaderStage.Pixel,
            "fragment": rd.ShaderStage.Pixel,
            "compute": rd.ShaderStage.Compute,
            "geometry": rd.ShaderStage.Geometry,
            "hull": rd.ShaderStage.Hull,
            "domain": rd.ShaderStage.Domain,
        }
        shader_stage = stage_map.get(stage.lower(), rd.ShaderStage.Pixel)

        refl = state.GetShaderReflection(shader_stage)
        if refl is None:
            return {"error": f"No {stage} shader bound at event {event_id}"}

        pipe = state.GetGraphicsPipelineObject()
        targets = controller.GetDisassemblyTargets(True)

        if target_index >= len(targets):
            target_index = 0

        target = targets[target_index]
        disasm = controller.DisassembleShader(pipe, refl, target)

        return {
            "eventId": event_id,
            "stage": stage,
            "target": str(target),
            "available_targets": [str(t) for t in targets],
            "disassembly": str(disasm),
        }
    finally:
        close_capture(cap, controller, rd)


# ---------------------------------------------------------------------------
# GPU Counters
# ---------------------------------------------------------------------------

def list_counters(rdc_path: str) -> Dict[str, Any]:
    """Enumerate available GPU performance counters."""
    cap, controller, rd = open_capture(rdc_path)
    try:
        counters = controller.EnumerateCounters()
        counter_list = []
        for c in counters:
            desc = controller.DescribeCounter(c)
            counter_list.append({
                "id": int(c),
                "name": str(desc.name),
                "description": str(desc.description),
                "resultByteWidth": desc.resultByteWidth,
                "resultType": str(desc.resultType),
                "unit": str(desc.unit),
            })
        return {"path": rdc_path, "count": len(counter_list), "counters": counter_list}
    finally:
        close_capture(cap, controller, rd)
