#!/usr/bin/env python3
"""Headless RenderDoc capture exporter for local and remote replay."""

import argparse
import csv
import hashlib
import json
import math
import os
import re
import struct
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path


TOOL_VERSION = "1.1.0"
UINT64_MAX = (1 << 64) - 1


def enum_text(value):
    name = getattr(value, "name", None)
    return str(name) if name is not None else str(value)


def resource_text(resource):
    return str(resource)


def resource_slug(resource):
    text = resource_text(resource)
    match = re.search(r"(\d+)$", text)
    return match.group(1) if match else re.sub(r"[^A-Za-z0-9_.-]+", "_", text)


def safe_name(value, fallback="unnamed"):
    result = re.sub(r"[<>:\"/\\|?*\x00-\x1f]+", "_", str(value)).strip(" ._")
    return result[:160] or fallback


def result_dict(result):
    return {
        "code": enum_text(getattr(result, "code", result)),
        "message": str(getattr(result, "message", result)),
        "text": str(result),
    }


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path, rows, fieldnames=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    if fieldnames is None:
        fieldnames = []
        seen = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    fieldnames.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(8 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def parse_size(value):
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([KMGT]?i?B)?\s*", value, re.IGNORECASE)
    if not match:
        raise argparse.ArgumentTypeError("Expected a byte size such as 64MB, 2GiB, or 4096")
    number = float(match.group(1))
    suffix = (match.group(2) or "B").upper()
    factors = {
        "B": 1, "KB": 1000, "MB": 1000 ** 2, "GB": 1000 ** 3, "TB": 1000 ** 4,
        "KIB": 1024, "MIB": 1024 ** 2, "GIB": 1024 ** 3, "TIB": 1024 ** 4,
    }
    return int(number * factors[suffix])


def human_size(value):
    size = float(value)
    for suffix in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024.0 or suffix == "TiB":
            return f"{size:.2f} {suffix}" if suffix != "B" else f"{int(size)} B"
        size /= 1024.0


def locate_renderdoc_bin(script_path, override):
    if override:
        candidate = Path(override).resolve()
        if not candidate.is_dir():
            raise RuntimeError(f"RenderDoc binary directory does not exist: {candidate}")
        return candidate
    for parent in script_path.resolve().parents:
        candidate = parent / "x64" / "Development"
        if (candidate / "pymodules" / "renderdoc.pyd").is_file():
            return candidate
    raise RuntimeError("Could not locate x64/Development; pass --renderdoc-bin")


def find_swiftshader_icd():
    roots = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
    ]
    candidates = []
    patterns = [
        "Google/Chrome/Application/*/vk_swiftshader_icd.json",
        "Arm/*/performance_studio_hub/vk_swiftshader_icd.json",
        "Common Files/Adobe/Adobe Desktop Common/CEF/vk_swiftshader_icd.json",
        "Common Files/Adobe/Microsoft/EdgeWebView/vk_swiftshader_icd.json",
        "Microsoft/Edge/Application/*/vk_swiftshader_icd.json",
        "Netease/POPO/popo/vk_swiftshader_icd.json",
        "Side Effects Software/Houdini */bin/vk_swiftshader_icd.json",
    ]
    for root in roots:
        for pattern in patterns:
            candidates.extend(root.glob(pattern))
    candidates = [path.resolve() for path in candidates if path.is_file()]
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def load_renderdoc(bin_dir):
    modules = bin_dir / "pymodules"
    if os.name == "nt":
        os.add_dll_directory(str(bin_dir))
        os.add_dll_directory(str(modules))
    sys.path.insert(0, str(modules))
    import renderdoc as rd
    return rd


def flatten_actions(actions, parent_event=0, depth=0):
    rows = []
    for action in actions:
        rows.append((action, parent_event, depth))
        rows.extend(flatten_actions(action.children, int(action.eventId), depth + 1))
    return rows


def action_flag_names(rd, flags):
    names = []
    for flag in rd.ActionFlags:
        if flag != rd.ActionFlags(0) and flags & flag:
            names.append(enum_text(flag))
    return names


def action_kind(rd, action):
    flags = action.flags
    if flags & rd.ActionFlags.MeshDispatch: return "mesh-dispatch"
    if flags & rd.ActionFlags.DispatchRay: return "ray-dispatch"
    if flags & rd.ActionFlags.Dispatch: return "dispatch"
    if flags & rd.ActionFlags.Drawcall: return "draw"
    if flags & rd.ActionFlags.Copy: return "copy"
    if flags & rd.ActionFlags.Resolve: return "resolve"
    if flags & rd.ActionFlags.GenMips: return "genmips"
    if flags & rd.ActionFlags.Clear: return "clear"
    if flags & rd.ActionFlags.BuildAccStruct: return "build-accel"
    if flags & rd.ActionFlags.Present: return "present"
    return "other"


def execution_action(rd, action):
    mask = (
        rd.ActionFlags.Drawcall | rd.ActionFlags.Dispatch | rd.ActionFlags.MeshDispatch
        | rd.ActionFlags.DispatchRay | rd.ActionFlags.Copy | rd.ActionFlags.Resolve
        | rd.ActionFlags.GenMips | rd.ActionFlags.Clear | rd.ActionFlags.BuildAccStruct
    )
    return bool(action.flags & mask)


def action_name(action, structured):
    return str(action.customName) if action.customName else str(action.GetName(structured))


def non_null_resources(rd, resources):
    null = rd.ResourceId.Null()
    return [resource for resource in resources if resource != null]


def build_passes(rd, actions):
    passes = []
    event_to_pass = {}
    current = None
    counters = defaultdict(int)
    null = rd.ResourceId.Null()
    for action in actions:
        kind = action_kind(rd, action)
        if kind in ("draw", "mesh-dispatch"):
            outputs = tuple(resource_text(resource) for resource in non_null_resources(rd, action.outputs))
            depth = "" if action.depthOut == null else resource_text(action.depthOut)
            key = ("graphics", outputs, depth)
            category = "Colour" if outputs else ("Depth-only" if depth else "Graphics")
            suffix = f" ({len(outputs)} Targets" + (" + Depth)" if depth else ")") if outputs else ""
        elif kind in ("dispatch", "ray-dispatch"):
            key = ("compute", kind)
            category = "Compute" if kind == "dispatch" else "Ray"
            suffix = ""
        elif kind in ("copy", "resolve", "genmips"):
            source = resource_text(action.copySource) if action.copySource != null else ""
            destination = resource_text(action.copyDestination) if action.copyDestination != null else ""
            key = (kind, source, destination)
            category = kind.capitalize()
            suffix = ""
        elif kind == "clear":
            key = ("clear", tuple(resource_text(resource) for resource in non_null_resources(rd, action.outputs)))
            category = "Clear"
            suffix = ""
        else:
            key = (kind, int(action.eventId))
            category = kind.capitalize()
            suffix = ""
        if current is None or current["key"] != key:
            counters[category] += 1
            current = {
                "index": len(passes), "name": f"{category} Pass #{counters[category]}{suffix}",
                "kind": category, "key": key, "firstEvent": int(action.eventId),
                "lastEvent": int(action.eventId), "eventCount": 0, "drawCount": 0,
                "dispatchCount": 0, "outputs": list(key[1]) if key[0] == "graphics" else [],
                "depth": key[2] if key[0] == "graphics" else "",
            }
            passes.append(current)
        current["lastEvent"] = int(action.eventId)
        current["eventCount"] += 1
        current["drawCount"] += int(kind in ("draw", "mesh-dispatch"))
        current["dispatchCount"] += int(kind in ("dispatch", "ray-dispatch"))
        event_to_pass[int(action.eventId)] = current["index"]
    for item in passes:
        item.pop("key", None)
    return passes, event_to_pass


def format_dict(resource_format):
    return {
        "name": str(resource_format.Name()), "componentType": enum_text(resource_format.compType),
        "componentCount": int(resource_format.compCount),
        "componentByteWidth": int(resource_format.compByteWidth),
        "special": bool(resource_format.Special()), "bgraOrder": bool(resource_format.BGRAOrder()),
        "elementByteSize": int(resource_format.ElementSize()),
    }


def descriptor_dict(binding):
    descriptor = binding.descriptor
    access = binding.access
    return {
        "shaderBindingIndex": int(access.index), "arrayElement": int(access.arrayElement),
        "staticallyUnused": bool(access.staticallyUnused),
        "descriptorStore": resource_text(access.descriptorStore),
        "descriptorStoreByteOffset": int(access.byteOffset),
        "descriptorStoreByteSize": int(access.byteSize),
        "descriptorType": enum_text(descriptor.type), "resourceId": resource_text(descriptor.resource),
        "absoluteByteOffset": int(descriptor.byteOffset), "byteSize": int(descriptor.byteSize),
        "elementByteSize": int(descriptor.elementByteSize), "firstMip": int(descriptor.firstMip),
        "numMips": int(descriptor.numMips), "firstSlice": int(descriptor.firstSlice),
        "numSlices": int(descriptor.numSlices), "textureType": enum_text(descriptor.textureType),
        "format": format_dict(descriptor.format),
    }


def signature_dict(signature):
    return {
        "name": str(signature.varName or signature.semanticIdxName),
        "semanticName": str(signature.semanticName), "semanticIndex": int(signature.semanticIndex),
        "registerIndex": int(signature.regIndex), "stream": int(signature.stream),
        "systemValue": enum_text(signature.systemValue), "type": enum_text(signature.varType),
        "componentCount": int(signature.compCount), "perPrimitive": bool(signature.perPrimitiveRate),
    }


def shader_resource_dict(resource):
    return {
        "name": str(resource.name), "descriptorType": enum_text(getattr(resource, "descriptorType", "Sampler")),
        "fixedBindSetOrSpace": int(resource.fixedBindSetOrSpace),
        "fixedBindNumber": int(resource.fixedBindNumber), "bindArraySize": int(resource.bindArraySize),
        "isReadOnly": bool(getattr(resource, "isReadOnly", True)),
        "isTexture": bool(getattr(resource, "isTexture", False)),
        "isInputAttachment": bool(getattr(resource, "isInputAttachment", False)),
        "hasSampler": bool(getattr(resource, "hasSampler", False)),
        "textureType": enum_text(getattr(resource, "textureType", "Unknown")),
    }


def constant_type_dict(constant_type):
    return {
        "name": str(constant_type.name), "baseType": enum_text(constant_type.baseType),
        "rows": int(constant_type.rows), "columns": int(constant_type.columns),
        "elements": int(constant_type.elements), "arrayByteStride": int(constant_type.arrayByteStride),
        "matrixByteStride": int(constant_type.matrixByteStride),
        "rowMajor": bool(constant_type.rows > 1 and constant_type.columns > 1 and (int(constant_type.flags) & 1)),
        "columnMajor": bool(constant_type.rows > 1 and constant_type.columns > 1 and not (int(constant_type.flags) & 1)),
        "members": [constant_dict(member) for member in constant_type.members],
    }


def constant_dict(constant):
    return {
        "name": str(constant.name), "byteOffset": int(constant.byteOffset),
        "bitFieldOffset": int(constant.bitFieldOffset), "bitFieldSize": int(constant.bitFieldSize),
        "type": constant_type_dict(constant.type),
    }


def shader_variable_values(rd, variable):
    count = max(1, int(variable.rows) * int(variable.columns))
    mapping = {
        rd.VarType.Float: "f32v", rd.VarType.Double: "f64v", rd.VarType.Half: "f16v",
        rd.VarType.SInt: "s32v", rd.VarType.UInt: "u32v", rd.VarType.SShort: "s16v",
        rd.VarType.UShort: "u16v", rd.VarType.SLong: "s64v", rd.VarType.ULong: "u64v",
        rd.VarType.SByte: "s8v", rd.VarType.UByte: "u8v", rd.VarType.Bool: "u32v",
        rd.VarType.Enum: "u32v",
    }
    field = mapping.get(variable.type)
    if field is None:
        return []
    values = getattr(variable.value, field)
    return [values[index] for index in range(min(count, len(values)))]


def shader_variable_dict(rd, variable):
    return {
        "name": str(variable.name), "type": enum_text(variable.type),
        "rows": int(variable.rows), "columns": int(variable.columns),
        "rowMajor": bool(variable.rows > 1 and variable.columns > 1 and (variable.flags & rd.ShaderVariableFlags.RowMajorMatrix)),
        "columnMajor": bool(variable.rows > 1 and variable.columns > 1 and not (variable.flags & rd.ShaderVariableFlags.RowMajorMatrix)),
        "values": shader_variable_values(rd, variable),
        "members": [shader_variable_dict(rd, member) for member in variable.members],
    }


def blend_equation_dict(equation):
    return {
        "source": enum_text(equation.source), "destination": enum_text(equation.destination),
        "operation": enum_text(equation.operation),
    }


def stencil_face_dict(face):
    return {
        "function": enum_text(face.function), "failOperation": enum_text(face.failOperation),
        "depthFailOperation": enum_text(face.depthFailOperation),
        "passOperation": enum_text(face.passOperation), "reference": int(face.reference),
        "compareMask": int(face.compareMask), "writeMask": int(face.writeMask),
    }


def viewport_dict(viewport):
    return {
        "enabled": bool(viewport.enabled), "x": float(viewport.x), "y": float(viewport.y),
        "width": float(viewport.width), "height": float(viewport.height),
        "minDepth": float(viewport.minDepth), "maxDepth": float(viewport.maxDepth),
    }


def scissor_dict(scissor):
    return {
        "enabled": bool(scissor.enabled), "x": int(scissor.x), "y": int(scissor.y),
        "width": int(scissor.width), "height": int(scissor.height),
    }


def clamp_range(offset, size, resource_length):
    offset = max(0, int(offset))
    if offset >= resource_length:
        return offset, 0
    if size <= 0 or size == UINT64_MAX:
        size = resource_length - offset
    return offset, min(int(size), resource_length - offset)


def parse_event_range(value):
    match = re.fullmatch(r"(\d+)\s*[:\-]\s*(\d+)", value)
    if not match:
        raise argparse.ArgumentTypeError("Expected START:END")
    start, end = int(match.group(1)), int(match.group(2))
    if end < start:
        raise argparse.ArgumentTypeError("END must be >= START")
    return start, end


class ReplaySession:
    def __init__(self, rd, capture, capture_path, arguments):
        self.rd = rd
        self.capture = capture
        self.capture_path = capture_path
        self.arguments = arguments
        self.controller = None
        self.remote = None
        self.remote_path = None
        self.mode = "local"

    def open(self):
        options = self.rd.ReplayOptions()
        options.apiValidation = bool(self.arguments.api_validation)
        if not self.arguments.remote:
            result, self.controller = self.capture.OpenCapture(options, None)
            return result
        self.mode = "remote"
        connection_result, self.remote = self.rd.CreateRemoteServerConnection(self.arguments.remote)
        if connection_result != self.rd.ResultCode.Succeeded and self.arguments.start_remote:
            protocol_name = self.arguments.remote.split(":", 1)[0] if ":" in self.arguments.remote else ""
            protocol = self.rd.GetDeviceProtocolController(protocol_name) if protocol_name else None
            if protocol is not None:
                start_result = protocol.StartRemoteServer(self.arguments.remote)
                if start_result == self.rd.ResultCode.Succeeded:
                    connection_result, self.remote = self.rd.CreateRemoteServerConnection(self.arguments.remote)
        if connection_result != self.rd.ResultCode.Succeeded or self.remote is None:
            return connection_result
        self.remote_path = str(self.remote.CopyCaptureToRemote(str(self.capture_path), None))
        result, self.controller = self.remote.OpenCapture(
            self.rd.RemoteServer.NoPreference, self.remote_path, options, None
        )
        return result

    def close(self):
        if self.controller is not None:
            if self.remote is not None:
                self.remote.CloseCapture(self.controller)
            else:
                self.controller.Shutdown()
            self.controller = None
        if self.remote is not None:
            self.remote.ShutdownConnection()
            self.remote = None


class CaptureExporter:
    def __init__(self, rd, controller, capture_path, output_dir, arguments, replay_mode):
        self.rd = rd
        self.controller = controller
        self.capture_path = capture_path
        self.output_dir = output_dir
        self.arguments = arguments
        self.replay_mode = replay_mode
        self.structured = controller.GetStructuredFile()
        self.flat_actions = flatten_actions(controller.GetRootActions())
        self.actions = [entry[0] for entry in self.flat_actions]
        self.execution_actions = [action for action in self.actions if execution_action(rd, action)]
        self.passes, self.event_to_pass = build_passes(rd, self.execution_actions)
        self.resources = {resource_text(item.resourceId): item for item in controller.GetResources()}
        self.textures = {resource_text(item.resourceId): item for item in controller.GetTextures()}
        self.buffers = {resource_text(item.resourceId): item for item in controller.GetBuffers()}
        self.shader_records = {}
        self.binding_records = []
        self.cbuffer_records = []
        self.mesh_records = []
        self.event_records = []
        self.texture_references = {}
        self.buffer_references = {}
        self.buffer_ranges = {}
        self.errors = []
        self.exported_bytes = 0

    def resource_name(self, resource_id):
        description = self.resources.get(resource_text(resource_id))
        return str(description.name) if description is not None else ""

    def add_error(self, category, event_id, message, details=None):
        record = {"category": category, "eventId": int(event_id or 0), "message": str(message)}
        if details:
            record.update(details)
        self.errors.append(record)

    def add_texture_reference(self, resource_id, event_id, role):
        key = resource_text(resource_id)
        if key not in self.textures:
            return
        record = self.texture_references.setdefault(
            key, {"resourceId": key, "firstEvent": int(event_id), "lastEvent": int(event_id), "roles": set()}
        )
        record["firstEvent"] = min(record["firstEvent"], int(event_id))
        record["lastEvent"] = max(record["lastEvent"], int(event_id))
        record["roles"].add(role)

    def add_buffer_reference(self, resource_id, event_id, role, offset=0, size=0):
        key = resource_text(resource_id)
        if key not in self.buffers:
            return
        record = self.buffer_references.setdefault(
            key, {"resourceId": key, "firstEvent": int(event_id), "lastEvent": int(event_id), "roles": set()}
        )
        record["firstEvent"] = min(record["firstEvent"], int(event_id))
        record["lastEvent"] = max(record["lastEvent"], int(event_id))
        record["roles"].add(role)
        absolute_offset, byte_size = clamp_range(offset, size, int(self.buffers[key].length))
        if byte_size > 0:
            range_key = (int(event_id), key, absolute_offset, byte_size)
            range_record = self.buffer_ranges.setdefault(
                range_key,
                {"eventId": int(event_id), "resourceId": key, "absoluteByteOffset": absolute_offset,
                 "byteSize": byte_size, "roles": set()},
            )
            range_record["roles"].add(role)

    def export_resource_lists(self):
        resource_rows = [{
            "resourceId": resource_text(item.resourceId), "name": str(item.name),
            "autogeneratedName": bool(item.autogeneratedName), "type": enum_text(item.type),
            "parentResources": [resource_text(value) for value in item.parentResources],
            "derivedResources": [resource_text(value) for value in item.derivedResources],
        } for item in self.resources.values()]
        texture_rows = [{
            "resourceId": resource_text(item.resourceId), "name": self.resource_name(item.resourceId),
            "type": enum_text(item.type), "dimension": int(item.dimension), "width": int(item.width),
            "height": int(item.height), "depth": int(item.depth), "mips": int(item.mips),
            "arraySize": int(item.arraysize), "samples": int(item.msSamp), "cubemap": bool(item.cubemap),
            "format": str(item.format.Name()), "byteSize": int(item.byteSize),
            "creationFlags": str(item.creationFlags),
        } for item in self.textures.values()]
        buffer_rows = [{
            "resourceId": resource_text(item.resourceId), "name": self.resource_name(item.resourceId),
            "length": int(item.length), "gpuAddress": int(item.gpuAddress),
            "creationFlags": str(item.creationFlags),
        } for item in self.buffers.values()]
        for rows in (resource_rows, texture_rows, buffer_rows):
            rows.sort(key=lambda row: row["resourceId"])
        for name, rows in (("resources", resource_rows), ("textures", texture_rows), ("buffers", buffer_rows)):
            write_json(self.output_dir / "resources" / f"{name}.json", rows)
            write_csv(self.output_dir / "resources" / f"{name}.csv", rows)
        return resource_rows, texture_rows, buffer_rows

    def export_actions(self):
        rows = []
        for action, parent_event, depth in self.flat_actions:
            pass_index = self.event_to_pass.get(int(action.eventId))
            pass_name = self.passes[pass_index]["name"] if pass_index is not None else ""
            rows.append({
                "eventId": int(action.eventId), "actionId": int(action.actionId),
                "parentEventId": int(parent_event), "treeDepth": int(depth),
                "name": action_name(action, self.structured), "kind": action_kind(self.rd, action),
                "flags": action_flag_names(self.rd, action.flags), "passIndex": pass_index,
                "pass": pass_name, "numIndices": int(action.numIndices),
                "numInstances": int(action.numInstances), "indexOffset": int(action.indexOffset),
                "vertexOffset": int(action.vertexOffset), "baseVertex": int(action.baseVertex),
                "instanceOffset": int(action.instanceOffset),
                "dispatchDimension": [int(value) for value in action.dispatchDimension],
                "dispatchThreadsDimension": [int(value) for value in action.dispatchThreadsDimension],
                "outputs": [resource_text(item) for item in non_null_resources(self.rd, action.outputs)],
                "depthOut": "" if action.depthOut == self.rd.ResourceId.Null() else resource_text(action.depthOut),
                "copySource": "" if action.copySource == self.rd.ResourceId.Null() else resource_text(action.copySource),
                "copyDestination": "" if action.copyDestination == self.rd.ResourceId.Null() else resource_text(action.copyDestination),
            })
        write_json(self.output_dir / "actions" / "actions.json", rows)
        csv_rows = [{
            **row, "flags": "|".join(row["flags"]),
            "dispatchDimension": "x".join(str(value) for value in row["dispatchDimension"]),
            "dispatchThreadsDimension": "x".join(str(value) for value in row["dispatchThreadsDimension"]),
            "outputs": "|".join(row["outputs"]),
        } for row in rows]
        write_csv(self.output_dir / "actions" / "actions.csv", csv_rows)
        write_json(self.output_dir / "actions" / "passes.json", self.passes)
        write_csv(self.output_dir / "actions" / "passes.csv", self.passes)
        return rows

    def selected_actions(self):
        selected = list(self.execution_actions)
        if self.arguments.types:
            allowed = set(self.arguments.types.split(","))
            selected = [action for action in selected if action_kind(self.rd, action) in allowed]
        if self.arguments.event:
            event_ids = set(self.arguments.event)
            selected = [action for action in selected if int(action.eventId) in event_ids]
        if self.arguments.event_range:
            start, end = self.arguments.event_range
            selected = [action for action in selected if start <= int(action.eventId) <= end]
        if self.arguments.pass_index:
            pass_indices = set(self.arguments.pass_index)
            selected = [action for action in selected if self.event_to_pass.get(int(action.eventId)) in pass_indices]
        if self.arguments.max_events is not None:
            selected = selected[:self.arguments.max_events]
        return selected

    def pipeline_state(self, pipe):
        blends = [{
            "enabled": bool(blend.enabled), "writeMask": int(blend.writeMask),
            "color": blend_equation_dict(blend.colorBlend),
            "alpha": blend_equation_dict(blend.alphaBlend),
            "logicOperationEnabled": bool(blend.logicOperationEnabled),
            "logicOperation": enum_text(blend.logicOperation),
        } for blend in pipe.GetColorBlends()]
        state = {
            "graphicsPipeline": resource_text(pipe.GetGraphicsPipelineObject()),
            "computePipeline": resource_text(pipe.GetComputePipelineObject()),
            "topology": enum_text(pipe.GetPrimitiveTopology()),
            "viewport0": viewport_dict(pipe.GetViewport(0)),
            "scissor0": scissor_dict(pipe.GetScissor(0)),
            "colorBlends": blends,
        }
        if pipe.IsCaptureD3D11():
            api_state = self.controller.GetD3D11PipelineState()
            depth = api_state.outputMerger.depthStencilState
            raster = api_state.rasterizer.state
            state["depthStencil"] = {
                "depthTest": bool(depth.depthEnable), "depthWrite": bool(depth.depthWrites),
                "depthFunction": enum_text(depth.depthFunction), "stencilTest": bool(depth.stencilEnable),
                "front": stencil_face_dict(depth.frontFace), "back": stencil_face_dict(depth.backFace),
            }
            state["rasterizer"] = {
                "fillMode": enum_text(raster.fillMode), "cullMode": enum_text(raster.cullMode),
                "frontCCW": bool(raster.frontCCW), "depthClip": bool(raster.depthClip),
                "scissorEnable": bool(raster.scissorEnable),
            }
        elif pipe.IsCaptureD3D12():
            api_state = self.controller.GetD3D12PipelineState()
            depth = api_state.outputMerger.depthStencilState
            raster = api_state.rasterizer.state
            state["depthStencil"] = {
                "depthTest": bool(depth.depthEnable), "depthWrite": bool(depth.depthWrites),
                "depthFunction": enum_text(depth.depthFunction), "stencilTest": bool(depth.stencilEnable),
                "front": stencil_face_dict(depth.frontFace), "back": stencil_face_dict(depth.backFace),
            }
            state["rasterizer"] = {
                "fillMode": enum_text(raster.fillMode), "cullMode": enum_text(raster.cullMode),
                "frontCCW": bool(raster.frontCCW), "depthClip": bool(raster.depthClip),
            }
        elif pipe.IsCaptureVK():
            api_state = self.controller.GetVulkanPipelineState()
            depth = api_state.depthStencil
            raster = api_state.rasterizer
            state["depthStencil"] = {
                "depthTest": bool(depth.depthTestEnable), "depthWrite": bool(depth.depthWriteEnable),
                "depthFunction": enum_text(depth.depthFunction),
                "stencilTest": bool(depth.stencilTestEnable),
                "front": stencil_face_dict(depth.frontFace), "back": stencil_face_dict(depth.backFace),
            }
            state["rasterizer"] = {
                "fillMode": enum_text(raster.fillMode), "cullMode": enum_text(raster.cullMode),
                "frontCCW": bool(raster.frontCCW), "depthClamp": bool(raster.depthClampEnable),
                "depthClip": bool(raster.depthClipEnable),
                "rasterizerDiscard": bool(raster.rasterizerDiscardEnable),
            }
        elif pipe.IsCaptureGL():
            api_state = self.controller.GetGLPipelineState()
            depth = api_state.depthState
            raster = api_state.rasterizer.state
            state["depthStencil"] = {
                "depthTest": bool(depth.depthEnable), "depthWrite": bool(depth.depthWrites),
                "depthFunction": enum_text(depth.depthFunction),
                "stencilTest": bool(api_state.stencilState.stencilEnable),
                "front": stencil_face_dict(api_state.stencilState.frontFace),
                "back": stencil_face_dict(api_state.stencilState.backFace),
            }
            state["rasterizer"] = {
                "fillMode": enum_text(raster.fillMode), "cullMode": enum_text(raster.cullMode),
                "frontCCW": bool(raster.frontCCW), "depthClamp": bool(raster.depthClamp),
            }
        return state

    def save_shader(self, pipe, stage, event_id):
        shader_id = pipe.GetShader(stage)
        reflection = pipe.GetShaderReflection(stage)
        if shader_id == self.rd.ResourceId.Null() or reflection is None:
            return None
        entry_point = str(pipe.GetShaderEntryPoint(stage))
        key = (resource_text(shader_id), enum_text(stage), entry_point)
        if key in self.shader_records:
            self.shader_records[key]["events"].add(int(event_id))
            return self.shader_records[key]
        stage_name = enum_text(stage)
        shader_name = f"{stage_name.lower()}_{resource_slug(shader_id)}"
        shader_dir = self.output_dir / "shaders"
        raw_data = bytes(reflection.rawBytes)
        encoding = enum_text(reflection.encoding)
        extensions = {"SPIRV": ".spv", "OpenGLSPIRV": ".spv", "DXBC": ".dxbc", "DXIL": ".dxil"}
        raw_path = shader_dir / "raw" / (shader_name + extensions.get(encoding, ".bin"))
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(raw_data)
        pipeline = pipe.GetComputePipelineObject() if stage == self.rd.ShaderStage.Compute else pipe.GetGraphicsPipelineObject()
        disassembly = self.controller.DisassembleShader(pipeline, reflection, self.arguments.disassembly_target)
        disassembly_path = shader_dir / "disassembly" / (shader_name + ".txt")
        disassembly_path.parent.mkdir(parents=True, exist_ok=True)
        disassembly_path.write_text(str(disassembly), encoding="utf-8")
        source_files = []
        if self.arguments.shader_sources:
            for index, source in enumerate(reflection.debugInfo.files):
                source_name = safe_name(Path(str(source.filename)).name, f"source_{index}.txt")
                source_path = shader_dir / "sources" / shader_name / f"{index:03d}_{source_name}"
                source_path.parent.mkdir(parents=True, exist_ok=True)
                source_path.write_text(str(source.contents), encoding="utf-8")
                source_files.append({"filename": str(source.filename), "file": str(source_path.relative_to(self.output_dir)).replace("\\", "/")})
        record = {
            "resourceId": resource_text(shader_id), "resourceName": self.resource_name(shader_id),
            "stage": stage_name, "entryPoint": entry_point, "encoding": encoding,
            "rawFile": str(raw_path.relative_to(self.output_dir)).replace("\\", "/"),
            "rawSha256": sha256_bytes(raw_data),
            "disassemblyFile": str(disassembly_path.relative_to(self.output_dir)).replace("\\", "/"),
            "disassemblySha256": sha256_bytes(str(disassembly).encode("utf-8")),
            "inputSignature": [signature_dict(value) for value in reflection.inputSignature],
            "outputSignature": [signature_dict(value) for value in reflection.outputSignature],
            "readOnlyResources": [shader_resource_dict(value) for value in reflection.readOnlyResources],
            "readWriteResources": [shader_resource_dict(value) for value in reflection.readWriteResources],
            "samplers": [shader_resource_dict(value) for value in reflection.samplers],
            "constantBlocks": [{
                "name": str(block.name), "fixedBindSetOrSpace": int(block.fixedBindSetOrSpace),
                "fixedBindNumber": int(block.fixedBindNumber), "bindArraySize": int(block.bindArraySize),
                "byteSize": int(block.byteSize), "bufferBacked": bool(block.bufferBacked),
                "variables": [constant_dict(value) for value in block.variables],
            } for block in reflection.constantBlocks],
            "debug": {"status": str(reflection.debugInfo.debugStatus), "compiler": str(reflection.debugInfo.compiler),
                      "encoding": enum_text(reflection.debugInfo.encoding), "files": source_files},
            "events": {int(event_id)},
        }
        self.shader_records[key] = record
        return record

    def collect_bindings(self, pipe, stage, event_id):
        reflection = pipe.GetShaderReflection(stage)
        if reflection is None:
            return []
        categories = (
            ("readOnly", pipe.GetReadOnlyResources(stage), list(reflection.readOnlyResources)),
            ("readWrite", pipe.GetReadWriteResources(stage), list(reflection.readWriteResources)),
            ("sampler", pipe.GetSamplers(stage), list(reflection.samplers)),
        )
        event_bindings = []
        for category, bindings, reflected in categories:
            for binding in bindings:
                record = descriptor_dict(binding)
                index = record["shaderBindingIndex"]
                reflection_binding = reflected[index] if 0 <= index < len(reflected) else None
                record.update({
                    "eventId": int(event_id), "stage": enum_text(stage), "category": category,
                    "bindingName": str(getattr(reflection_binding, "name", "")),
                    "fixedBindSetOrSpace": int(getattr(reflection_binding, "fixedBindSetOrSpace", 0)),
                    "fixedBindNumber": int(getattr(reflection_binding, "fixedBindNumber", 0)),
                    "resourceName": self.resource_name(record["resourceId"]),
                })
                event_bindings.append(record)
                self.binding_records.append(record)
                resource_id = binding.descriptor.resource
                if record["resourceId"] in self.textures:
                    self.add_texture_reference(resource_id, event_id, f"{enum_text(stage)}:{category}:{record['bindingName']}")
                elif record["resourceId"] in self.buffers:
                    self.add_buffer_reference(
                        resource_id, event_id, f"{enum_text(stage)}:{category}:{record['bindingName']}",
                        record["absoluteByteOffset"], record["byteSize"],
                    )
        return event_bindings

    def collect_cbuffers(self, pipe, stage, event_id):
        reflection = pipe.GetShaderReflection(stage)
        if reflection is None:
            return []
        result = []
        pipeline = pipe.GetComputePipelineObject() if stage == self.rd.ShaderStage.Compute else pipe.GetGraphicsPipelineObject()
        for block_index, block in enumerate(reflection.constantBlocks):
            array_count = max(1, min(int(block.bindArraySize or 1), self.arguments.max_binding_array))
            for array_element in range(array_count):
                record = {
                    "eventId": int(event_id), "stage": enum_text(stage), "blockIndex": block_index,
                    "arrayElement": array_element, "name": str(block.name),
                    "shaderResourceId": resource_text(reflection.resourceId),
                    "fixedBindSetOrSpace": int(block.fixedBindSetOrSpace),
                    "fixedBindNumber": int(block.fixedBindNumber), "declaredByteSize": int(block.byteSize),
                    "bufferBacked": bool(block.bufferBacked),
                    "layout": [constant_dict(value) for value in block.variables],
                }
                try:
                    used = pipe.GetConstantBlock(stage, block_index, array_element)
                    descriptor = descriptor_dict(used)
                    record["descriptor"] = descriptor
                    record["resourceName"] = self.resource_name(descriptor["resourceId"])
                    if descriptor["resourceId"] in self.buffers:
                        self.add_buffer_reference(
                            used.descriptor.resource, event_id, f"{enum_text(stage)}:cbuffer:{block.name}",
                            descriptor["absoluteByteOffset"], descriptor["byteSize"],
                        )
                    if self.arguments.cbuffers in ("raw", "both") and descriptor["resourceId"] in self.buffers:
                        buffer_length = int(self.buffers[descriptor["resourceId"]].length)
                        offset, size = clamp_range(descriptor["absoluteByteOffset"], descriptor["byteSize"], buffer_length)
                        raw = bytes(self.controller.GetBufferData(used.descriptor.resource, offset, size))
                        if len(raw) != size:
                            raise RuntimeError(f"CBuffer read returned {len(raw)} bytes, expected {size}")
                        path = self.output_dir / "cbuffers" / "raw" / (
                            f"eid_{event_id:06d}_{enum_text(stage).lower()}_{block_index}_{array_element}_"
                            f"r{resource_slug(used.descriptor.resource)}_off{offset}_size{size}.bin"
                        )
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(raw)
                        record["rawFile"] = str(path.relative_to(self.output_dir)).replace("\\", "/")
                        record["rawSha256"] = sha256_bytes(raw)
                    if self.arguments.cbuffers in ("decoded", "both"):
                        values = self.controller.GetCBufferVariableContents(
                            pipeline, reflection.resourceId, stage, pipe.GetShaderEntryPoint(stage), block_index,
                            used.descriptor.resource, used.descriptor.byteOffset, used.descriptor.byteSize,
                        )
                        record["values"] = [shader_variable_dict(self.rd, value) for value in values]
                except Exception as error:
                    record["error"] = str(error)
                    self.add_error("cbuffer", event_id, error, {
                        "stage": enum_text(stage), "blockIndex": block_index,
                        "blockName": str(block.name), "declaredByteSize": int(block.byteSize),
                    })
                self.cbuffer_records.append(record)
                result.append(record)
        return result

    def process_event(self, action):
        event_id = int(action.eventId)
        self.controller.SetFrameEvent(event_id, True)
        pipe = self.controller.GetPipelineState()
        pass_index = self.event_to_pass.get(event_id)
        record = {
            "eventId": event_id, "actionId": int(action.actionId),
            "name": action_name(action, self.structured), "kind": action_kind(self.rd, action),
            "passIndex": pass_index, "pass": self.passes[pass_index]["name"] if pass_index is not None else "",
            "numIndices": int(action.numIndices), "numInstances": int(action.numInstances),
            "outputs": [resource_text(value) for value in non_null_resources(self.rd, action.outputs)],
            "depthOut": "" if action.depthOut == self.rd.ResourceId.Null() else resource_text(action.depthOut),
            "pipeline": self.pipeline_state(pipe), "shaders": [], "bindings": [], "cbuffers": [],
        }
        for output in non_null_resources(self.rd, action.outputs):
            self.add_texture_reference(output, event_id, "render-target")
        if action.depthOut != self.rd.ResourceId.Null():
            self.add_texture_reference(action.depthOut, event_id, "depth-target")
        vertex_buffers = []
        for slot, buffer in enumerate(pipe.GetVBuffers()):
            item = {
                "slot": slot, "resourceId": resource_text(buffer.resourceId),
                "absoluteByteOffset": int(buffer.byteOffset), "byteSize": int(buffer.byteSize),
                "byteStride": int(buffer.byteStride),
            }
            vertex_buffers.append(item)
            self.add_buffer_reference(buffer.resourceId, event_id, f"vertex-buffer:{slot}", buffer.byteOffset, buffer.byteSize)
        index_buffer = pipe.GetIBuffer()
        record["vertexBuffers"] = vertex_buffers
        record["indexBuffer"] = {
            "resourceId": resource_text(index_buffer.resourceId),
            "absoluteByteOffset": int(index_buffer.byteOffset), "byteSize": int(index_buffer.byteSize),
            "byteStride": int(index_buffer.byteStride),
        }
        self.add_buffer_reference(
            index_buffer.resourceId, event_id, "index-buffer", index_buffer.byteOffset, index_buffer.byteSize
        )
        record["vertexInputs"] = [{
            "name": str(value.name), "vertexBuffer": int(value.vertexBuffer),
            "byteOffset": int(value.byteOffset), "perInstance": bool(value.perInstance),
            "instanceRate": int(value.instanceRate), "used": bool(value.used),
            "format": format_dict(value.format),
        } for value in pipe.GetVertexInputs()]
        kind = action_kind(self.rd, action)
        if kind == "dispatch":
            stages = [self.rd.ShaderStage.Compute]
        elif kind == "ray-dispatch":
            stages = [self.rd.ShaderStage.RayGen, self.rd.ShaderStage.Intersection,
                      self.rd.ShaderStage.AnyHit, self.rd.ShaderStage.ClosestHit,
                      self.rd.ShaderStage.Miss, self.rd.ShaderStage.Callable]
        else:
            stages = [self.rd.ShaderStage.Vertex, self.rd.ShaderStage.Hull,
                      self.rd.ShaderStage.Domain, self.rd.ShaderStage.Geometry,
                      self.rd.ShaderStage.Pixel, self.rd.ShaderStage.Task, self.rd.ShaderStage.Mesh]
        for stage in stages:
            try:
                shader = self.save_shader(pipe, stage, event_id) if self.arguments.shaders else None
                if shader is not None:
                    record["shaders"].append({
                        "resourceId": shader["resourceId"], "stage": shader["stage"],
                        "entryPoint": shader["entryPoint"],
                    })
                if self.arguments.bindings:
                    record["bindings"].extend(self.collect_bindings(pipe, stage, event_id))
                if self.arguments.cbuffers != "none":
                    record["cbuffers"].extend(self.collect_cbuffers(pipe, stage, event_id))
            except Exception as error:
                self.add_error("stage", event_id, error, {"stage": enum_text(stage)})
                if self.arguments.strict:
                    raise
        if self.arguments.meshes != "none" and action.flags & self.rd.ActionFlags.Drawcall:
            try:
                record["meshes"] = self.export_meshes(pipe, action)
            except Exception as error:
                self.add_error("mesh", event_id, error)
                record["meshes"] = [{"error": str(error)}]
                if self.arguments.strict:
                    raise
        record["pipelineHash"] = sha256_bytes(json.dumps(record["pipeline"], sort_keys=True).encode("utf-8"))
        event_path = self.output_dir / "events" / f"eid_{event_id:06d}.json"
        write_json(event_path, record)
        record["file"] = str(event_path.relative_to(self.output_dir)).replace("\\", "/")
        self.event_records.append(record)
        return record

    def process_events(self, actions):
        for index, action in enumerate(actions, 1):
            print(f"[{index}/{len(actions)}] EID {int(action.eventId)} {action_kind(self.rd, action)}", flush=True)
            try:
                self.process_event(action)
            except Exception as error:
                self.add_error("event", int(action.eventId), traceback.format_exc())
                if self.arguments.strict:
                    raise

    def export_meshes(self, pipe, action):
        stage_map = {
            "vsout": self.rd.MeshDataStage.VSOut, "gsout": self.rd.MeshDataStage.GSOut,
            "taskout": self.rd.MeshDataStage.TaskOut, "meshout": self.rd.MeshDataStage.MeshOut,
        }
        data_stage = stage_map[self.arguments.mesh_stage]
        instance_count = min(max(1, int(action.numInstances)), self.arguments.max_instances)
        records = []
        for instance in range(instance_count):
            mesh = self.controller.GetPostVSData(instance, 0, data_stage)
            record = {
                "eventId": int(action.eventId), "instance": instance,
                "stage": enum_text(data_stage), "status": str(mesh.status),
                "topology": enum_text(mesh.topology), "numIndices": int(mesh.numIndices),
                "baseVertex": int(mesh.baseVertex), "vertexResourceId": resource_text(mesh.vertexResourceId),
                "vertexAbsoluteByteOffset": int(mesh.vertexByteOffset),
                "vertexByteSize": int(mesh.vertexByteSize), "vertexByteStride": int(mesh.vertexByteStride),
                "indexResourceId": resource_text(mesh.indexResourceId),
                "indexAbsoluteByteOffset": int(mesh.indexByteOffset),
                "indexByteSize": int(mesh.indexByteSize), "indexByteStride": int(mesh.indexByteStride),
            }
            if mesh.vertexResourceId == self.rd.ResourceId.Null() or int(mesh.numIndices) == 0:
                record["error"] = "Post-VS data is unavailable"
                records.append(record)
                self.mesh_records.append(record)
                continue
            indices, index_data = read_postvs_indices(self.rd, self.controller, mesh)
            attributes = postvs_attributes(self.rd, pipe, mesh, data_stage)
            max_index = max(indices) if indices else max(0, int(mesh.numIndices) - 1)
            vertex_size = int(mesh.vertexByteSize)
            if vertex_size <= 0 or vertex_size == UINT64_MAX:
                vertex_size = (max_index + 1) * int(mesh.vertexByteStride)
            vertex_data = bytes(self.controller.GetBufferData(mesh.vertexResourceId, mesh.vertexByteOffset, vertex_size))
            mesh_dir = self.output_dir / "meshes" / f"eid_{int(action.eventId):06d}" / f"instance_{instance:04d}"
            mesh_dir.mkdir(parents=True, exist_ok=True)
            if self.arguments.meshes in ("raw", "both"):
                vertex_path = mesh_dir / "postvs_vertices.bin"
                index_path = mesh_dir / "postvs_indices.bin"
                vertex_path.write_bytes(vertex_data)
                index_path.write_bytes(index_data)
                record["vertexFile"] = str(vertex_path.relative_to(self.output_dir)).replace("\\", "/")
                record["vertexSha256"] = sha256_bytes(vertex_data)
                record["indexFile"] = str(index_path.relative_to(self.output_dir)).replace("\\", "/")
                record["indexSha256"] = sha256_bytes(index_data)
            record["attributes"] = [{
                "name": item["name"], "absoluteByteOffset": int(item["offset"]),
                "relativeByteOffset": int(item["offset"] - int(mesh.vertexByteOffset)),
                "format": format_dict(item["format"]),
            } for item in attributes]
            if self.arguments.meshes in ("csv", "both"):
                rows = []
                for draw_index, vertex_index in enumerate(indices[:self.arguments.max_mesh_rows]):
                    row = {"drawIndex": draw_index, "vertexIndex": vertex_index}
                    for attribute in attributes:
                        relative = attribute["offset"] - int(mesh.vertexByteOffset)
                        data_offset = vertex_index * int(mesh.vertexByteStride) + relative
                        value = unpack_format(self.rd, attribute["format"], vertex_data, data_offset)
                        if value is not None:
                            for component, component_value in enumerate(value):
                                row[f"{attribute['name']}.{component}"] = component_value
                    rows.append(row)
                csv_path = mesh_dir / "postvs.csv"
                write_csv(csv_path, rows)
                record["csvFile"] = str(csv_path.relative_to(self.output_dir)).replace("\\", "/")
                record["csvRows"] = len(rows)
                record["csvTruncated"] = len(indices) > len(rows)
            metadata_path = mesh_dir / "mesh.json"
            write_json(metadata_path, record)
            record["metadataFile"] = str(metadata_path.relative_to(self.output_dir)).replace("\\", "/")
            records.append(record)
            self.mesh_records.append(record)
        return records

    def export_textures(self, fallback_event):
        if self.arguments.textures == "none":
            return []
        if self.arguments.textures == "all":
            candidates = [{
                "resourceId": key, "firstEvent": fallback_event, "lastEvent": fallback_event,
                "roles": {"all-textures"},
            } for key in self.textures]
        else:
            candidates = list(self.texture_references.values())
        if self.arguments.max_textures is not None:
            candidates = candidates[:self.arguments.max_textures]
        file_types = {
            "dds": self.rd.FileType.DDS, "png": self.rd.FileType.PNG, "jpg": self.rd.FileType.JPG,
            "bmp": self.rd.FileType.BMP, "tga": self.rd.FileType.TGA, "hdr": self.rd.FileType.HDR,
            "exr": self.rd.FileType.EXR,
        }
        records = []
        for index, reference in enumerate(candidates, 1):
            key = reference["resourceId"]
            texture = self.textures[key]
            event_id = int(reference.get("lastEvent") or fallback_event)
            record = {
                "resourceId": key, "resourceName": self.resource_name(key), "eventId": event_id,
                "roles": sorted(reference["roles"]), "width": int(texture.width),
                "height": int(texture.height), "depth": int(texture.depth), "mips": int(texture.mips),
                "arraySize": int(texture.arraysize), "samples": int(texture.msSamp),
                "format": str(texture.format.Name()), "byteSize": int(texture.byteSize),
            }
            if int(texture.byteSize) > self.arguments.max_resource_bytes:
                record["skipped"] = f"Resource exceeds --max-resource-bytes ({human_size(self.arguments.max_resource_bytes)})"
                records.append(record)
                continue
            try:
                print(f"[texture {index}/{len(candidates)}] {key} at EID {event_id}", flush=True)
                self.controller.SetFrameEvent(event_id, True)
                save = self.rd.TextureSave()
                save.resourceId = texture.resourceId
                save.destType = file_types[self.arguments.texture_format]
                save.mip = -1 if self.arguments.texture_format == "dds" else 0
                if self.arguments.texture_format != "dds":
                    save.slice.sliceIndex = 0
                    save.sample.sampleIndex = self.rd.TextureSampleMapping.ResolveSamples
                path = self.output_dir / "textures" / (
                    f"resource_{resource_slug(texture.resourceId)}_eid_{event_id:06d}.{self.arguments.texture_format}"
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                result = self.controller.SaveTexture(save, str(path))
                record["result"] = result_dict(result)
                if path.is_file():
                    record["file"] = str(path.relative_to(self.output_dir)).replace("\\", "/")
                    record["fileSize"] = path.stat().st_size
                    record["sha256"] = sha256_file(path)
                    self.exported_bytes += path.stat().st_size
                else:
                    record["error"] = "SaveTexture did not create an output file"
            except Exception as error:
                record["error"] = str(error)
                self.add_error("texture", event_id, error, {"resourceId": key})
                if self.arguments.strict:
                    raise
            records.append(record)
        write_json(self.output_dir / "textures" / "texture_exports.json", records)
        write_csv(self.output_dir / "textures" / "texture_exports.csv", [{
            **row, "roles": "|".join(row.get("roles", [])), "result": row.get("result", {}).get("text", "")
        } for row in records])
        return records

    def export_buffers(self, fallback_event):
        if self.arguments.buffers == "none":
            return []
        if self.arguments.buffers == "ranges":
            candidates = list(self.buffer_ranges.values())
        else:
            references = self.buffer_references.values() if self.arguments.buffers == "referenced" else [
                {"resourceId": key, "lastEvent": fallback_event, "roles": {"all-buffers"}}
                for key in self.buffers
            ]
            candidates = []
            for reference in references:
                buffer = self.buffers[reference["resourceId"]]
                candidates.append({
                    "eventId": int(reference.get("lastEvent") or fallback_event),
                    "resourceId": reference["resourceId"], "absoluteByteOffset": 0,
                    "byteSize": int(buffer.length), "roles": set(reference["roles"]),
                })
        if self.arguments.max_buffers is not None:
            candidates = candidates[:self.arguments.max_buffers]
        records = []
        for index, candidate in enumerate(candidates, 1):
            record = {**candidate, "roles": sorted(candidate["roles"])}
            event_id = int(candidate["eventId"])
            key = candidate["resourceId"]
            size = int(candidate["byteSize"])
            offset = int(candidate["absoluteByteOffset"])
            record["resourceName"] = self.resource_name(key)
            if size > self.arguments.max_resource_bytes:
                record["skipped"] = f"Range exceeds --max-resource-bytes ({human_size(self.arguments.max_resource_bytes)})"
                records.append(record)
                continue
            if self.exported_bytes + size > self.arguments.max_total_bytes:
                record["skipped"] = f"Export would exceed --max-total-bytes ({human_size(self.arguments.max_total_bytes)})"
                records.append(record)
                continue
            try:
                print(f"[buffer {index}/{len(candidates)}] {key} off={offset} size={size} EID {event_id}", flush=True)
                self.controller.SetFrameEvent(event_id, True)
                resource_id = self.buffers[key].resourceId
                data = bytes(self.controller.GetBufferData(resource_id, offset, size))
                if len(data) != size:
                    raise RuntimeError(f"GetBufferData returned {len(data)} bytes, expected {size}")
                path = self.output_dir / "buffers" / (
                    f"resource_{resource_slug(resource_id)}_eid_{event_id:06d}_off_{offset}_size_{size}.bin"
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                record["file"] = str(path.relative_to(self.output_dir)).replace("\\", "/")
                record["sha256"] = sha256_bytes(data)
                self.exported_bytes += len(data)
            except Exception as error:
                record["error"] = str(error)
                self.add_error("buffer", event_id, error, {
                    "resourceId": key, "absoluteByteOffset": offset, "byteSize": size,
                })
                if self.arguments.strict:
                    raise
            records.append(record)
        write_json(self.output_dir / "buffers" / "buffer_exports.json", records)
        write_csv(self.output_dir / "buffers" / "buffer_exports.csv", [{
            **row, "roles": "|".join(row.get("roles", []))
        } for row in records])
        return records

    def write_analysis_files(self):
        shaders = []
        for record in self.shader_records.values():
            value = {**record, "events": sorted(record["events"]), "drawCount": len(record["events"])}
            shaders.append(value)
            write_json(
                self.output_dir / "shaders" / "metadata" /
                f"{value['stage'].lower()}_{resource_slug(value['resourceId'])}.json", value,
            )
        shaders.sort(key=lambda row: (row["stage"], row["resourceId"]))
        write_json(self.output_dir / "shaders" / "shaders.json", shaders)
        write_csv(self.output_dir / "shaders" / "shaders.csv", [{
            "resourceId": row["resourceId"], "resourceName": row["resourceName"],
            "stage": row["stage"], "entryPoint": row["entryPoint"], "encoding": row["encoding"],
            "drawCount": row["drawCount"], "rawFile": row["rawFile"],
            "disassemblyFile": row["disassemblyFile"],
        } for row in shaders])
        write_json(self.output_dir / "bindings" / "bindings.json", self.binding_records)
        write_csv(self.output_dir / "bindings" / "bindings.csv", [{
            **row, "format": row.get("format", {}).get("name", "")
        } for row in self.binding_records])
        write_json(self.output_dir / "cbuffers" / "cbuffers.json", self.cbuffer_records)
        write_csv(self.output_dir / "cbuffers" / "cbuffers.csv", [{
            "eventId": row["eventId"], "stage": row["stage"], "blockIndex": row["blockIndex"],
            "arrayElement": row["arrayElement"], "name": row["name"],
            "resourceId": row.get("descriptor", {}).get("resourceId", ""),
            "absoluteByteOffset": row.get("descriptor", {}).get("absoluteByteOffset", 0),
            "byteSize": row.get("descriptor", {}).get("byteSize", 0),
            "rawFile": row.get("rawFile", ""), "error": row.get("error", ""),
        } for row in self.cbuffer_records])
        write_json(self.output_dir / "meshes" / "meshes.json", self.mesh_records)
        write_jsonl(self.output_dir / "events" / "events.jsonl", self.event_records)
        write_csv(self.output_dir / "events" / "events.csv", [{
            "eventId": row["eventId"], "actionId": row["actionId"], "name": row["name"],
            "kind": row["kind"], "passIndex": row["passIndex"], "pass": row["pass"],
            "numIndices": row["numIndices"], "numInstances": row["numInstances"],
            "topology": row["pipeline"].get("topology", ""),
            "graphicsPipeline": row["pipeline"].get("graphicsPipeline", ""),
            "computePipeline": row["pipeline"].get("computePipeline", ""),
            "shaderCount": len(row["shaders"]), "bindingCount": len(row["bindings"]),
            "pipelineHash": row["pipelineHash"], "file": row["file"],
        } for row in self.event_records])
        return shaders

    def run(self):
        resource_rows, texture_rows, buffer_rows = self.export_resource_lists()
        action_rows = self.export_actions()
        selected = self.selected_actions()
        if self.arguments.pipeline:
            self.process_events(selected)
        fallback_event = int(selected[-1].eventId) if selected else (
            int(self.execution_actions[-1].eventId) if self.execution_actions else 0
        )
        texture_exports = self.export_textures(fallback_event)
        buffer_exports = self.export_buffers(fallback_event)
        shaders = self.write_analysis_files()
        debug_messages = [{
            "eventId": int(value.eventId), "source": enum_text(value.source),
            "category": enum_text(value.category), "severity": enum_text(value.severity),
            "messageId": int(value.messageID), "description": str(value.description),
        } for value in self.controller.GetDebugMessages()]
        write_json(self.output_dir / "debug_messages.json", debug_messages)
        write_json(self.output_dir / "errors.json", self.errors)
        totals = {
            "actions": len(action_rows), "executionActions": len(self.execution_actions),
            "selectedEvents": len(selected), "processedEvents": len(self.event_records),
            "passes": len(self.passes), "resources": len(resource_rows),
            "textures": len(texture_rows), "buffers": len(buffer_rows), "shaders": len(shaders),
            "bindings": len(self.binding_records), "cbuffers": len(self.cbuffer_records),
            "meshes": len(self.mesh_records), "textureExports": len(texture_exports),
            "bufferExports": len(buffer_exports), "errors": len(self.errors),
            "exportedBytes": self.exported_bytes,
        }
        manifest = {
            "schemaVersion": 1, "toolVersion": TOOL_VERSION, "status": "complete",
            "capture": str(self.capture_path), "replayMode": self.replay_mode,
            "api": str(self.controller.GetAPIProperties().pipelineType),
            "preset": self.arguments.preset, "totals": totals, "errorsFile": "errors.json",
        }
        write_json(self.output_dir / "manifest.json", manifest)
        summary = [
            "RenderDoc RDC Export", "=" * 72, f"Capture: {self.capture_path}",
            f"Replay mode: {self.replay_mode}", f"Actions: {totals['actions']}",
            f"Selected events: {totals['selectedEvents']}", f"Textures: {totals['textures']}",
            f"Buffers: {totals['buffers']}", f"Shaders: {totals['shaders']}",
            f"Bindings: {totals['bindings']}", f"CBuffer snapshots: {totals['cbuffers']}",
            f"Post-VS meshes: {totals['meshes']}", f"Exported bytes: {human_size(totals['exportedBytes'])}",
            f"Errors: {totals['errors']}",
        ]
        (self.output_dir / "summary.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
        return manifest


def read_postvs_indices(rd, controller, mesh):
    count = int(mesh.numIndices)
    if mesh.indexResourceId == rd.ResourceId.Null():
        return list(range(count)), b""
    stride = int(mesh.indexByteStride)
    formats = {1: "B", 2: "H", 4: "I"}
    if stride not in formats:
        raise RuntimeError(f"Unsupported post-VS index stride {stride}")
    data = bytes(controller.GetBufferData(mesh.indexResourceId, mesh.indexByteOffset, count * stride))
    if len(data) != count * stride:
        raise RuntimeError(f"Post-VS index read returned {len(data)} bytes, expected {count * stride}")
    values = list(struct.unpack("<" + formats[stride] * count, data))
    if int(mesh.baseVertex):
        values = [value + int(mesh.baseVertex) for value in values]
    return values, data


def postvs_attributes(rd, pipe, mesh, data_stage):
    if data_stage == rd.MeshDataStage.VSOut:
        reflection = pipe.GetShaderReflection(rd.ShaderStage.Vertex)
    elif data_stage == rd.MeshDataStage.MeshOut:
        reflection = pipe.GetShaderReflection(rd.ShaderStage.Mesh)
    elif data_stage == rd.MeshDataStage.TaskOut:
        raise RuntimeError("Task shader payload decoding is not supported")
    else:
        reflection = pipe.GetShaderReflection(rd.ShaderStage.Geometry)
        if reflection is None:
            reflection = pipe.GetShaderReflection(rd.ShaderStage.Domain)
    if reflection is None:
        raise RuntimeError("No shader reflection is available for the requested post-VS stage")
    attributes = []
    position_index = 0
    for signature in reflection.outputSignature:
        if pipe.GetRasterizedStream() >= 0 and signature.stream != pipe.GetRasterizedStream():
            continue
        if pipe.GetRasterizedStream() < 0 and signature.stream != 0:
            continue
        if signature.systemValue == rd.ShaderBuiltin.OutputIndices:
            continue
        resource_format = rd.ResourceFormat()
        resource_format.compByteWidth = rd.VarTypeByteSize(signature.varType)
        resource_format.compCount = signature.compCount
        resource_format.compType = rd.VarTypeCompType(signature.varType)
        resource_format.type = rd.ResourceFormatType.Regular
        if signature.systemValue == rd.ShaderBuiltin.Position:
            position_index = len(attributes)
        attributes.append({
            "name": str(signature.varName or signature.semanticIdxName),
            "format": resource_format, "offset": int(mesh.vertexByteOffset),
        })
    if position_index > 0:
        attributes.insert(0, attributes.pop(position_index))
    accumulated = 0
    for attribute in attributes:
        resource_format = attribute["format"]
        element_size = 8 if int(resource_format.compByteWidth) > 4 else 4
        alignment = element_size * (2 if resource_format.compCount == 2 else (4 if resource_format.compCount > 2 else 1))
        if pipe.HasAlignedPostVSData(data_stage) and accumulated % alignment:
            accumulated += alignment - (accumulated % alignment)
        attribute["offset"] += accumulated
        accumulated += element_size * int(resource_format.compCount)
    return attributes


def unpack_format(rd, resource_format, data, offset):
    if resource_format.Special() or offset < 0 or offset >= len(data):
        return None
    formats = {
        rd.CompType.UInt: "xBHxIxxxQ", rd.CompType.SInt: "xbhxixxxq",
        rd.CompType.Float: "xxexfxxxd",
    }
    formats[rd.CompType.UNorm] = formats[rd.CompType.UInt]
    formats[rd.CompType.UScaled] = formats[rd.CompType.UInt]
    formats[rd.CompType.SNorm] = formats[rd.CompType.SInt]
    formats[rd.CompType.SScaled] = formats[rd.CompType.SInt]
    table = formats.get(resource_format.compType)
    width = int(resource_format.compByteWidth)
    if table is None or width >= len(table) or table[width] == "x":
        return None
    try:
        value = struct.unpack_from("=" + str(resource_format.compCount) + table[width], data, offset)
    except struct.error:
        return None
    if resource_format.compType == rd.CompType.UNorm:
        divisor = float((1 << (width * 8)) - 1)
        value = tuple(float(item) / divisor for item in value)
    elif resource_format.compType == rd.CompType.SNorm:
        minimum = -(1 << (width * 8 - 1))
        divisor = float(-minimum - 1)
        value = tuple(-1.0 if item == minimum else float(item) / divisor for item in value)
    elif resource_format.compType in (rd.CompType.UScaled, rd.CompType.SScaled):
        value = tuple(float(item) for item in value)
    if resource_format.BGRAOrder() and len(value) == 4:
        value = (value[2], value[1], value[0], value[3])
    return value


def export_container_metadata(rd, capture, capture_path, output_dir, capture_hash):
    sections = []
    for index in range(int(capture.GetSectionCount())):
        properties = capture.GetSectionProperties(index)
        sections.append({
            "index": index, "name": str(properties.name), "type": enum_text(properties.type),
            "version": int(properties.version), "flags": str(properties.flags),
            "compressedSize": int(properties.compressedSize),
            "uncompressedSize": int(properties.uncompressedSize),
        })
    write_json(output_dir / "capture" / "sections.json", sections)
    write_csv(output_dir / "capture" / "sections.csv", sections)
    thumbnail_record = None
    try:
        thumbnail = capture.GetThumbnail(rd.FileType.JPG, 2048)
        data = bytes(thumbnail.data)
        if data:
            path = output_dir / "capture" / "thumbnail.jpg"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            thumbnail_record = {
                "file": str(path.relative_to(output_dir)).replace("\\", "/"),
                "width": int(thumbnail.width), "height": int(thumbnail.height),
                "sha256": sha256_bytes(data),
            }
    except Exception as error:
        thumbnail_record = {"error": str(error)}
    metadata = {
        "path": str(capture_path), "fileSize": capture_path.stat().st_size,
        "sha256": sha256_file(capture_path) if capture_hash else None,
        "driver": str(capture.DriverName()), "recordedMachineIdent": str(capture.RecordedMachineIdent()),
        "localReplaySupport": enum_text(capture.LocalReplaySupport()),
        "timestampBase": int(capture.TimestampBase()), "timestampFrequency": float(capture.TimestampFrequency()),
        "sectionCount": len(sections), "thumbnail": thumbnail_record,
    }
    write_json(output_dir / "capture" / "capture.json", metadata)
    return metadata


def resolve_preset(arguments):
    presets = {
        "metadata": {"pipeline": False, "shaders": False, "bindings": False,
                     "textures": "none", "buffers": "none", "cbuffers": "none", "meshes": "none"},
        "analysis": {"pipeline": True, "shaders": True, "bindings": True,
                     "textures": "none", "buffers": "none", "cbuffers": "none", "meshes": "none"},
        "full": {"pipeline": True, "shaders": True, "bindings": True,
                 "textures": "referenced", "buffers": "ranges", "cbuffers": "both", "meshes": "both"},
    }
    defaults = presets[arguments.preset]
    for name, value in defaults.items():
        if getattr(arguments, name) is None:
            setattr(arguments, name, value)
    return arguments


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Export RenderDoc RDC actions, resources, shaders, descriptors, CBuffers, textures and post-VS data"
    )
    parser.add_argument("capture", help="Path to the .rdc capture")
    parser.add_argument("-o", "--output", required=True, help="Output directory")
    parser.add_argument("--renderdoc-bin", help="Directory containing renderdoc.dll and pymodules/renderdoc.pyd")
    parser.add_argument("--preset", choices=("metadata", "analysis", "full"), default="analysis")
    parser.add_argument("--remote", help="Remote replay URL, for example adb://SERIAL or hostname")
    parser.add_argument("--start-remote", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--api-validation", action="store_true")
    parser.add_argument("--vulkan-software-replay", action="store_true")
    parser.add_argument("--vulkan-icd", help="Path to a Vulkan ICD JSON, typically vk_swiftshader_icd.json")
    parser.add_argument("--vulkan-emulate-fragment-density-map", action="store_true")
    parser.add_argument("--vulkan-allow-unsupported-features", action="store_true")
    parser.add_argument("--pipeline", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--shaders", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--bindings", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--shader-sources", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--disassembly-target", default="")
    parser.add_argument("--textures", choices=("none", "referenced", "all"), default=None)
    parser.add_argument("--texture-format", choices=("dds", "png", "jpg", "bmp", "tga", "hdr", "exr"), default="dds")
    parser.add_argument("--buffers", choices=("none", "ranges", "referenced", "all"), default=None)
    parser.add_argument("--cbuffers", choices=("none", "raw", "decoded", "both"), default=None)
    parser.add_argument("--meshes", choices=("none", "raw", "csv", "both"), default=None)
    parser.add_argument("--mesh-stage", choices=("vsout", "gsout", "taskout", "meshout"), default="vsout")
    parser.add_argument("--event", type=int, action="append")
    parser.add_argument("--event-range", type=parse_event_range)
    parser.add_argument("--pass-index", type=int, action="append")
    parser.add_argument("--types", default="draw,mesh-dispatch,dispatch,ray-dispatch,copy,resolve,genmips,clear,build-accel")
    parser.add_argument("--max-events", type=int)
    parser.add_argument("--max-textures", type=int)
    parser.add_argument("--max-buffers", type=int)
    parser.add_argument("--max-instances", type=int, default=1)
    parser.add_argument("--max-binding-array", type=int, default=16)
    parser.add_argument("--max-mesh-rows", type=int, default=1_000_000)
    parser.add_argument("--max-resource-bytes", type=parse_size, default=parse_size("512MiB"))
    parser.add_argument("--max-total-bytes", type=parse_size, default=parse_size("8GiB"))
    parser.add_argument("--capture-hash", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return resolve_preset(parser.parse_args())


def main():
    arguments = parse_arguments()
    capture_path = Path(arguments.capture).resolve()
    output_dir = Path(arguments.output).resolve()
    if not capture_path.is_file():
        raise SystemExit(f"Capture does not exist: {capture_path}")
    if (output_dir / "manifest.json").exists() and not arguments.overwrite:
        raise SystemExit(f"Output already contains manifest.json; pass --overwrite: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    script_path = Path(__file__).resolve()
    bin_dir = locate_renderdoc_bin(script_path, arguments.renderdoc_bin)
    if arguments.vulkan_software_replay:
        if not arguments.vulkan_icd:
            detected_icd = find_swiftshader_icd()
            if detected_icd is None:
                raise SystemExit("SwiftShader ICD was not found; pass --vulkan-icd with vk_swiftshader_icd.json")
            arguments.vulkan_icd = str(detected_icd)
        arguments.vulkan_emulate_fragment_density_map = True
        arguments.vulkan_allow_unsupported_features = True
    if arguments.vulkan_icd:
        icd_path = Path(arguments.vulkan_icd).resolve()
        if not icd_path.is_file():
            raise SystemExit(f"Vulkan ICD JSON does not exist: {icd_path}")
        os.environ["VK_ICD_FILENAMES"] = str(icd_path)
    rd = load_renderdoc(bin_dir)
    capture = None
    session = None
    start_time = time.time()
    try:
        rd.InitialiseReplay(rd.GlobalEnvironment(), [])
        if arguments.vulkan_emulate_fragment_density_map:
            setting = rd.SetConfigSetting("Vulkan.Replay.EmulateFragmentDensityMap")
            if setting is None:
                raise RuntimeError("Vulkan.Replay.EmulateFragmentDensityMap is unavailable in this build")
            setting.data.basic.b = True
        if arguments.vulkan_allow_unsupported_features:
            setting = rd.SetConfigSetting("Vulkan.Replay.AllowUnsupportedFeatures")
            if setting is None:
                raise RuntimeError("Vulkan.Replay.AllowUnsupportedFeatures is unavailable in this build")
            setting.data.basic.b = True
        capture = rd.OpenCaptureFile()
        open_result = capture.OpenFile(str(capture_path), "", None)
        if open_result != rd.ResultCode.Succeeded:
            failure = {"status": "open-failed", "capture": str(capture_path), "result": result_dict(open_result)}
            write_json(output_dir / "manifest.json", failure)
            print(json.dumps(failure, indent=2, ensure_ascii=False))
            return 1
        container = export_container_metadata(rd, capture, capture_path, output_dir, arguments.capture_hash)
        session = ReplaySession(rd, capture, capture_path, arguments)
        replay_result = session.open()
        if replay_result != rd.ResultCode.Succeeded or session.controller is None:
            failure = {
                "schemaVersion": 1, "toolVersion": TOOL_VERSION, "status": "replay-unavailable",
                "capture": str(capture_path), "container": container, "result": result_dict(replay_result),
                "remoteRequested": arguments.remote,
                "hint": "For Android captures, connect a compatible device and pass --remote adb://SERIAL",
                "elapsedSeconds": round(time.time() - start_time, 3),
            }
            write_json(output_dir / "manifest.json", failure)
            (output_dir / "replay_error.txt").write_text(failure["result"]["text"] + "\n", encoding="utf-8")
            print(json.dumps(failure, indent=2, ensure_ascii=False))
            return 0 if arguments.allow_partial else 3
        exporter = CaptureExporter(
            rd, session.controller, capture_path, output_dir, arguments, session.mode
        )
        manifest = exporter.run()
        manifest["api"] = container["driver"]
        manifest["vulkanSoftwareReplay"] = bool(arguments.vulkan_software_replay)
        manifest["vulkanIcd"] = arguments.vulkan_icd
        manifest["container"] = container
        manifest["elapsedSeconds"] = round(time.time() - start_time, 3)
        write_json(output_dir / "manifest.json", manifest)
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        return 2 if arguments.strict and manifest["totals"]["errors"] else 0
    except Exception:
        failure = {
            "schemaVersion": 1, "toolVersion": TOOL_VERSION, "status": "failed",
            "capture": str(capture_path), "error": traceback.format_exc(),
            "elapsedSeconds": round(time.time() - start_time, 3),
        }
        write_json(output_dir / "manifest.json", failure)
        print(failure["error"], file=sys.stderr)
        return 1
    finally:
        if session is not None:
            session.close()
        if capture is not None:
            capture.Shutdown()
        try:
            rd.ShutdownReplay()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
