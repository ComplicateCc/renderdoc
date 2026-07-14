#!/usr/bin/env python3
"""Export a RenderDoc colour pass into Blender-ready scene resources."""

import argparse
import array
import hashlib
import json
import math
import os
import re
import struct
import subprocess
import sys
from pathlib import Path


DEFAULT_CONFIG = {
    "pass": {"colourTargetCount": None, "requireDepth": None},
    "camera": {
        "clipFromWorld": None,
        "calibrationEvent": None,
        "worldOutput": None,
        "candidateDraws": 24,
        "sampleVertices": 64,
        "fitTolerance": 0.0002,
        "minimumCrossValidationDraws": 2,
    },
    "attributes": {"shaderOverrides": {}},
    "materials": {
        "diffuseTextureSlot": 0,
        "shaderOverrides": {},
        "alphaTestPattern": r"\b(?:Kill|discard|OpKill|Demote)\s*\(?",
    },
    "textures": {"stages": ["Vertex", "Pixel"], "allSlices": False},
    "blender": {"flipV": True, "scale": 1.0, "perDrawFbx": True},
}


def deep_merge(base, override):
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def relative(path, root):
    return str(Path(path).resolve().relative_to(Path(root).resolve())).replace("\\", "/")


def resource_name(resource):
    return str(resource)


def resource_slug(resource):
    return resource_name(resource).replace("ResourceId::", "")


def json_write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def write_float_file(path, values):
    data = array.array("f", values)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("wb") as handle:
        data.tofile(handle)
    return sha256(Path(path).read_bytes())


def write_uint_file(path, values):
    data = array.array("I", values)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("wb") as handle:
        data.tofile(handle)
    return sha256(Path(path).read_bytes())


def flatten_actions(actions):
    result = []
    for action in actions:
        result.append(action)
        result.extend(flatten_actions(action.children))
    return result


def solve_linear(matrix, vector):
    count = len(vector)
    rows = [list(matrix[row]) + [vector[row]] for row in range(count)]
    for column in range(count):
        pivot = max(range(column, count), key=lambda row: abs(rows[row][column]))
        if abs(rows[pivot][column]) < 1.0e-12:
            raise ValueError("Singular linear system")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        rows[column] = [value / divisor for value in rows[column]]
        for row in range(count):
            if row == column:
                continue
            factor = rows[row][column]
            rows[row] = [rows[row][entry] - factor * rows[column][entry] for entry in range(count + 1)]
    return [rows[row][-1] for row in range(count)]


def fit_clip_from_points(points, clips):
    means = [sum(point[index] for point in points) / len(points) for index in range(3)]
    scales = [
        max(1.0, math.sqrt(sum((point[index] - means[index]) ** 2 for point in points) / len(points)))
        for index in range(3)
    ]
    rows = [[(point[index] - means[index]) / scales[index] for index in range(3)] + [1.0] for point in points]
    normal = [[sum(row[left] * row[right] for row in rows) for right in range(4)] for left in range(4)]
    result = []
    for component in range(4):
        target = [sum(rows[row][index] * clips[row][component] for row in range(len(rows))) for index in range(4)]
        coefficients = solve_linear(normal, target)
        output = [coefficients[index] / scales[index] for index in range(3)]
        output.append(coefficients[3] - sum(coefficients[index] * means[index] / scales[index] for index in range(3)))
        result.append(output)
    return result


def matrix_vector(matrix, vector):
    return [sum(matrix[row][column] * vector[column] for column in range(4)) for row in range(4)]


def invert_matrix(matrix):
    rows = [list(matrix[row]) + [1.0 if row == column else 0.0 for column in range(4)] for row in range(4)]
    for column in range(4):
        pivot = max(range(column, 4), key=lambda row: abs(rows[row][column]))
        if abs(rows[pivot][column]) < 1.0e-12:
            raise ValueError("Matrix is singular")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        rows[column] = [value / divisor for value in rows[column]]
        for row in range(4):
            if row == column:
                continue
            factor = rows[row][column]
            rows[row] = [rows[row][entry] - factor * rows[column][entry] for entry in range(8)]
    return [row[4:] for row in rows]


def matrix_error(matrix, points, clips):
    errors = []
    for point, clip in zip(points, clips):
        projected = matrix_vector(matrix, point + [1.0])
        scale = max(1.0, abs(clip[3]))
        errors.extend(abs(projected[index] - clip[index]) / scale for index in range(4))
    return {"maxRelative": max(errors), "meanRelative": sum(errors) / len(errors)}


def vector_dot(left, right):
    return sum(left[index] * right[index] for index in range(3))


def vector_length(vector):
    return math.sqrt(vector_dot(vector, vector))


def vector_scale(vector, scalar):
    return [value * scalar for value in vector]


def vector_add(left, right):
    return [left[index] + right[index] for index in range(3)]


def vector_sub(left, right):
    return [left[index] - right[index] for index in range(3)]


def derive_camera(clip_from_world):
    row0, row1, row3 = clip_from_world[0], clip_from_world[1], clip_from_world[3]
    forward_scale = vector_length(row3[:3])
    forward = vector_scale(row3[:3], 1.0 / forward_scale)
    row0_forward = vector_dot(row0[:3], forward)
    row1_forward = vector_dot(row1[:3], forward)
    right_raw = vector_sub(row0[:3], vector_scale(forward, row0_forward))
    up_raw = vector_sub(row1[:3], vector_scale(forward, row1_forward))
    right_scale = vector_length(right_raw)
    up_scale = vector_length(up_raw)
    right = vector_scale(right_raw, 1.0 / right_scale)
    up = vector_scale(up_raw, 1.0 / up_scale)
    forward_coordinate = -row3[3] / forward_scale
    right_coordinate = -(row0[3] - row0_forward * row3[3] / forward_scale) / right_scale
    up_coordinate = -(row1[3] - row1_forward * row3[3] / forward_scale) / up_scale
    position = vector_add(
        vector_add(vector_scale(right, right_coordinate), vector_scale(up, up_coordinate)),
        vector_scale(forward, forward_coordinate),
    )
    return {"position": position, "right": right, "up": up, "forward": forward}


def locate_renderdoc_bin(script_path, override):
    if override:
        return Path(override).resolve()
    for parent in script_path.resolve().parents:
        candidate = parent / "x64" / "Development"
        if candidate.is_dir():
            return candidate
    raise RuntimeError("Could not locate x64/Development; pass --renderdoc-bin")


def load_renderdoc(bin_dir):
    if os.name == "nt":
        os.add_dll_directory(str(bin_dir))
        modules = bin_dir / "pymodules"
        os.add_dll_directory(str(modules))
        sys.path.insert(0, str(modules))
    import renderdoc as rd
    return rd


def action_name(action, structured):
    return str(action.customName) if action.customName else str(action.GetName(structured))


def build_passes(rd, controller, actions, structured):
    passes = []
    current = None
    for action in actions:
        name = action_name(action, structured)
        if "BeginRenderPass" in name or "BeginRendering" in name:
            if current is not None:
                passes.append(current)
            current = {"beginEvent": int(action.eventId), "beginName": name, "drawActions": []}
        if current is not None and action.flags & rd.ActionFlags.Drawcall:
            current["drawActions"].append(action)
        if current is not None and ("EndRenderPass" in name or "EndRendering" in name):
            current["endEvent"] = int(action.eventId)
            current["endName"] = name
            passes.append(current)
            current = None
    if current is not None:
        passes.append(current)
    colour_index = 0
    for item in passes:
        if not item["drawActions"]:
            item["colourTargetCount"] = 0
            item["hasDepth"] = False
            continue
        controller.SetFrameEvent(item["drawActions"][0].eventId, True)
        pipeline = controller.GetPipelineState()
        outputs = [output for output in pipeline.GetOutputTargets() if output.resource != rd.ResourceId.Null()]
        depth = pipeline.GetDepthTarget()
        item["colourTargets"] = [resource_name(output.resource) for output in outputs]
        item["colourTargetCount"] = len(outputs)
        item["hasDepth"] = depth.resource != rd.ResourceId.Null()
        item["depthTarget"] = resource_name(depth.resource)
        item["drawCount"] = len(item["drawActions"])
        item["firstDraw"] = int(item["drawActions"][0].eventId)
        item["lastDraw"] = int(item["drawActions"][-1].eventId)
        if outputs:
            colour_index += 1
            item["colourPassIndex"] = colour_index
    return passes


def select_pass(rd, controller, actions, structured, arguments, config):
    if arguments.begin_event is not None or arguments.end_event is not None:
        if arguments.begin_event is None or arguments.end_event is None:
            raise RuntimeError("--begin-event and --end-event must be specified together")
        draws = [action for action in actions if arguments.begin_event < action.eventId < arguments.end_event and action.flags & rd.ActionFlags.Drawcall]
        if not draws:
            raise RuntimeError("No draw calls found in the requested event range")
        return {
            "beginEvent": arguments.begin_event,
            "endEvent": arguments.end_event,
            "drawActions": draws,
            "drawCount": len(draws),
            "selection": "eventRange",
        }, []
    passes = build_passes(rd, controller, actions, structured)
    selected = next((item for item in passes if item.get("colourPassIndex") == arguments.colour_pass), None)
    if selected is None:
        raise RuntimeError("Colour pass #%d was not found" % arguments.colour_pass)
    expected_targets = config["pass"]["colourTargetCount"]
    if expected_targets is not None and selected["colourTargetCount"] != expected_targets:
        raise RuntimeError("Colour pass target count is %d, expected %d" % (selected["colourTargetCount"], expected_targets))
    require_depth = config["pass"]["requireDepth"]
    if require_depth is not None and selected["hasDepth"] != require_depth:
        raise RuntimeError("Colour pass depth attachment mismatch")
    selected["selection"] = "colourPass"
    return selected, passes


def parse_indices(rd, controller, mesh):
    count = int(mesh.numIndices)
    if mesh.indexResourceId == rd.ResourceId.Null():
        return list(range(count)), b""
    stride = int(mesh.indexByteStride)
    formats = {1: "B", 2: "H", 4: "I"}
    if stride not in formats:
        raise RuntimeError("Unsupported post-VS index stride %d" % stride)
    data = bytes(controller.GetBufferData(mesh.indexResourceId, mesh.indexByteOffset, count * stride))
    if len(data) != count * stride:
        raise RuntimeError("Post-VS index read was truncated")
    values = list(struct.unpack("<" + formats[stride] * count, data))
    base_vertex = int(mesh.baseVertex)
    if base_vertex:
        values = [value + base_vertex for value in values]
    return values, data


def signature_layout(rd, reflection):
    if reflection is None:
        return None, []
    signatures = list(reflection.outputSignature)
    positions = [item for item in signatures if item.systemValue == rd.ShaderBuiltin.Position]
    outputs = [item for item in signatures if item.systemValue != rd.ShaderBuiltin.Position]
    ordered = positions + outputs
    offset = 0
    layout = []
    for signature in ordered:
        byte_width = int(rd.VarTypeByteSize(signature.varType))
        item = {
            "name": str(signature.varName or signature.semanticIdxName),
            "semanticName": str(signature.semanticName),
            "semanticIndex": int(signature.semanticIndex),
            "systemValue": str(signature.systemValue),
            "varType": str(signature.varType),
            "compCount": int(signature.compCount),
            "byteWidth": byte_width,
            "byteOffset": offset,
            "isFloat": signature.varType == rd.VarType.Float,
        }
        layout.append(item)
        offset += (8 if byte_width > 4 else 4) * int(signature.compCount)
    position = layout[0] if positions else None
    return position, layout[1:] if positions else layout


def sample_draw(rd, controller, action, sample_vertices):
    controller.SetFrameEvent(action.eventId, True)
    pipeline = controller.GetPipelineState()
    reflection = pipeline.GetShaderReflection(rd.ShaderStage.Vertex)
    position, outputs = signature_layout(rd, reflection)
    if position is None or not position["isFloat"] or position["compCount"] < 4:
        raise RuntimeError("Post-VS position is not float4")
    mesh = controller.GetPostVSData(0, 0, rd.MeshDataStage.VSOut)
    indices, _ = parse_indices(rd, controller, mesh)
    unique = list(dict.fromkeys(indices))
    if len(unique) > sample_vertices:
        unique = [unique[round(index * (len(unique) - 1) / (sample_vertices - 1))] for index in range(sample_vertices)]
    if not unique:
        raise RuntimeError("Post-VS output has no vertices")
    vertex_count = max(unique) + 1
    stride = int(mesh.vertexByteStride)
    data = bytes(controller.GetBufferData(mesh.vertexResourceId, mesh.vertexByteOffset, vertex_count * stride))
    clips = [list(struct.unpack_from("<4f", data, index * stride + position["byteOffset"])) for index in unique]
    attributes = []
    for output_index, output in enumerate(outputs):
        if not output["isFloat"] or output["compCount"] < 3:
            continue
        values = [
            list(struct.unpack_from("<" + "f" * output["compCount"], data, index * stride + output["byteOffset"]))
            for index in unique
        ]
        attributes.append({"outputIndex": output_index, "layout": output, "values": values})
    return {"eventId": int(action.eventId), "shader": resource_name(pipeline.GetShader(rd.ShaderStage.Vertex)), "clips": clips, "attributes": attributes}


def candidate_matrix(sample, attribute, tolerance):
    values = [value[:3] for value in attribute["values"]]
    spans = [max(value[index] for value in values) - min(value[index] for value in values) for index in range(3)]
    if math.sqrt(sum(span * span for span in spans)) < 1.0 or sum(span > 1.0e-3 for span in spans) < 2:
        return None
    training = list(range(0, len(values), 2))
    testing = list(range(1, len(values), 2))
    if len(training) < 4 or len(testing) < 2:
        return None
    try:
        matrix = fit_clip_from_points([values[index] for index in training], [sample["clips"][index] for index in training])
        invert_matrix(matrix)
    except ValueError:
        return None
    fit = matrix_error(matrix, [values[index] for index in training], [sample["clips"][index] for index in training])
    validation = matrix_error(matrix, [values[index] for index in testing], [sample["clips"][index] for index in testing])
    if validation["maxRelative"] > tolerance:
        return None
    return {
        "matrix": matrix,
        "sourceEvent": sample["eventId"],
        "sourceShader": sample["shader"],
        "sourceOutput": attribute["outputIndex"],
        "sourceOutputName": attribute["layout"]["name"],
        "fit": fit,
        "holdout": validation,
    }


def calibration_from_override(rd, controller, actions_by_event, config):
    event_id = config["camera"]["calibrationEvent"]
    output_index = config["camera"]["worldOutput"]
    if event_id is None and output_index is None:
        return None
    if event_id is None or output_index is None:
        raise RuntimeError("camera.calibrationEvent and camera.worldOutput must be specified together")
    action = actions_by_event.get(int(event_id))
    if action is None:
        raise RuntimeError("Calibration event %d was not found" % event_id)
    sample = sample_draw(rd, controller, action, int(config["camera"]["sampleVertices"]))
    attribute = next((item for item in sample["attributes"] if item["outputIndex"] == int(output_index)), None)
    if attribute is None:
        raise RuntimeError("Calibration output %d is unavailable" % output_index)
    candidate = candidate_matrix(sample, attribute, float(config["camera"]["fitTolerance"]))
    if candidate is None:
        raise RuntimeError("Configured calibration output did not fit a stable clip-from-world matrix")
    candidate["crossValidation"] = []
    candidate["selection"] = "configuredOutput"
    return candidate


def auto_calibrate(rd, controller, draw_actions, config):
    count = int(config["camera"]["candidateDraws"])
    tolerance = float(config["camera"]["fitTolerance"])
    sample_vertices = int(config["camera"]["sampleVertices"])
    ranked = sorted(draw_actions, key=lambda action: int(action.numIndices) * max(1, int(action.numInstances)), reverse=True)
    samples = []
    failures = []
    for action in ranked[:count]:
        try:
            samples.append(sample_draw(rd, controller, action, sample_vertices))
        except Exception as error:
            failures.append({"eventId": int(action.eventId), "error": str(error)})
    candidates = []
    for sample in samples:
        for attribute in sample["attributes"]:
            candidate = candidate_matrix(sample, attribute, tolerance)
            if candidate is not None:
                candidates.append(candidate)
    if not candidates:
        raise RuntimeError("Could not fit a clip-from-world matrix; configure camera.calibrationEvent/worldOutput or camera.clipFromWorld")
    for candidate in candidates:
        validations = []
        for sample in samples:
            if sample["eventId"] == candidate["sourceEvent"]:
                continue
            best = None
            for attribute in sample["attributes"]:
                values = [value[:3] for value in attribute["values"]]
                error = matrix_error(candidate["matrix"], values, sample["clips"])
                if best is None or error["maxRelative"] < best["error"]["maxRelative"]:
                    best = {"eventId": sample["eventId"], "output": attribute["outputIndex"], "error": error}
            if best is not None and best["error"]["maxRelative"] <= tolerance:
                validations.append(best)
        candidate["crossValidation"] = validations
        candidate["score"] = 1 + len(validations)
    candidates.sort(key=lambda item: (-item["score"], item["holdout"]["maxRelative"], item["sourceEvent"], item["sourceOutput"]))
    selected = candidates[0]
    minimum = int(config["camera"]["minimumCrossValidationDraws"])
    if selected["score"] < minimum:
        raise RuntimeError("Automatic camera calibration had only %d matching draw(s), required %d" % (selected["score"], minimum))
    selected["selection"] = "automaticWorldOutputSearch"
    selected["sampleFailures"] = failures
    selected["candidateCount"] = len(candidates)
    return selected


def save_calibration_cbuffers(rd, controller, event_id, output_dir):
    controller.SetFrameEvent(event_id, True)
    pipeline = controller.GetPipelineState()
    reflection = pipeline.GetShaderReflection(rd.ShaderStage.Vertex)
    result = []
    if reflection is None:
        return result
    for index, block in enumerate(reflection.constantBlocks):
        bound = pipeline.GetConstantBlock(rd.ShaderStage.Vertex, index, 0).descriptor
        data = b""
        if bound.resource != rd.ResourceId.Null() and bound.byteSize > 0:
            data = bytes(controller.GetBufferData(bound.resource, bound.byteOffset, bound.byteSize))
        path = output_dir / "evidence" / ("calibration_eid_%d_vs_cbuffer_%d.bin" % (event_id, index))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        result.append({
            "index": index,
            "name": str(block.name),
            "resourceId": resource_name(bound.resource),
            "absoluteByteOffset": int(bound.byteOffset),
            "byteSize": int(bound.byteSize),
            "file": relative(path, output_dir),
            "sha256": sha256(data),
        })
    return result


def shader_override(config, section, shader):
    overrides = config[section].get("shaderOverrides", {})
    return overrides.get(shader, overrides.get(resource_slug(shader), {}))


def choose_attributes(outputs, data, stride, vertex_indices, shader, config):
    override = shader_override(config, "attributes", shader)

    def values(output):
        return [
            list(struct.unpack_from("<" + "f" * output["compCount"], data, index * stride + output["byteOffset"]))
            for index in vertex_indices
        ]

    decoded = [values(output) if output["isFloat"] else [] for output in outputs]
    uv_index = override.get("uvOutput")
    normal_index = override.get("normalOutput")
    if uv_index is None:
        best = None
        for index, output in enumerate(outputs):
            if not output["isFloat"] or output["compCount"] < 2:
                continue
            samples = decoded[index]
            xs = [sample[0] for sample in samples]
            ys = [sample[1] for sample in samples]
            if max(xs) - min(xs) < 1.0e-6 or max(ys) - min(ys) < 1.0e-6:
                continue
            max_abs = max(abs(value) for value in xs + ys)
            if max_abs > 64.0:
                continue
            normal_penalty = 0.0
            if output["compCount"] >= 3:
                lengths = [vector_length(sample[:3]) for sample in samples]
                median = sorted(lengths)[len(lengths) // 2]
                if 0.75 <= median <= 1.25:
                    normal_penalty = 20.0
            score = normal_penalty + math.log2(max(1.0, max_abs)) + index * 0.01
            if best is None or score < best[0]:
                best = (score, index)
        uv_index = None if best is None else best[1]
    if normal_index is None:
        for index, output in enumerate(outputs):
            if index == uv_index or not output["isFloat"] or output["compCount"] < 3:
                continue
            lengths = [vector_length(sample[:3]) for sample in decoded[index]]
            if lengths and sum(0.65 <= value <= 1.35 for value in lengths) / len(lengths) >= 0.8:
                normal_index = index
                break
    for name, index in (("uvOutput", uv_index), ("normalOutput", normal_index)):
        if index is not None and (index < 0 or index >= len(outputs)):
            raise RuntimeError("%s %s is outside the post-VS output list" % (shader, name))
    return uv_index, normal_index


def triangles_for_topology(rd, topology, indices):
    triangles = []
    if topology == rd.Topology.TriangleList:
        triangles = [tuple(indices[index:index + 3]) for index in range(0, len(indices) - 2, 3)]
    elif topology == rd.Topology.TriangleStrip:
        for index in range(len(indices) - 2):
            triangle = (indices[index], indices[index + 1], indices[index + 2])
            if index & 1:
                triangle = (triangle[1], triangle[0], triangle[2])
            triangles.append(triangle)
    elif topology == rd.Topology.TriangleFan:
        triangles = [(indices[0], indices[index], indices[index + 1]) for index in range(1, len(indices) - 1)]
    else:
        raise RuntimeError("Unsupported topology %s" % topology)
    return [triangle for triangle in triangles if len(set(triangle)) == 3]


def descriptor_metadata(binding, reflection_binding=None):
    descriptor = binding.descriptor
    access = binding.access
    result = {
        "shaderBindingIndex": int(access.index),
        "arrayElement": int(access.arrayElement),
        "descriptorStore": resource_name(access.descriptorStore),
        "descriptorStoreByteOffset": int(access.byteOffset),
        "descriptorStoreByteSize": int(access.byteSize),
        "resourceId": resource_name(descriptor.resource),
        "resourceByteOffset": int(descriptor.byteOffset),
        "resourceByteSize": int(descriptor.byteSize),
        "firstMip": int(descriptor.firstMip),
        "numMips": int(descriptor.numMips),
        "firstSlice": int(descriptor.firstSlice),
        "numSlices": int(descriptor.numSlices),
        "descriptorType": str(descriptor.type),
        "format": str(descriptor.format.Name()),
    }
    if reflection_binding is not None:
        result["bindingName"] = str(reflection_binding.name)
        result["fixedBindSetOrSpace"] = int(reflection_binding.fixedBindSetOrSpace)
        result["fixedBindNumber"] = int(reflection_binding.fixedBindNumber)
    return result


def save_shader(rd, controller, pipeline, stage, output_dir, shader_records, config):
    shader = pipeline.GetShader(stage)
    if shader == rd.ResourceId.Null():
        return None
    key = "%s:%s" % (stage, resource_name(shader))
    if key in shader_records:
        return shader_records[key]
    reflection = pipeline.GetShaderReflection(stage)
    stage_names = {
        rd.ShaderStage.Vertex: "Vertex",
        rd.ShaderStage.Hull: "Hull",
        rd.ShaderStage.Domain: "Domain",
        rd.ShaderStage.Geometry: "Geometry",
        rd.ShaderStage.Pixel: "Pixel",
    }
    stage_name = stage_names.get(stage, str(stage))
    path = output_dir / "shaders" / ("%s_%s.txt" % (stage_name.lower(), resource_slug(shader)))
    path.parent.mkdir(parents=True, exist_ok=True)
    disassembly = controller.DisassembleShader(pipeline.GetGraphicsPipelineObject(), reflection, "") if reflection else ""
    path.write_text(disassembly, encoding="utf-8")
    record = {
        "stage": stage_name,
        "resourceId": resource_name(shader),
        "entryPoint": str(pipeline.GetShaderEntryPoint(stage)),
        "disassembly": relative(path, output_dir),
        "sha256": sha256(disassembly.encode("utf-8")),
        "alphaTest": bool(re.search(config["materials"]["alphaTestPattern"], disassembly, re.IGNORECASE)),
    }
    shader_records[key] = record
    return record


def stage_from_name(rd, name):
    mapping = {
        "Vertex": rd.ShaderStage.Vertex,
        "Hull": rd.ShaderStage.Hull,
        "Domain": rd.ShaderStage.Domain,
        "Geometry": rd.ShaderStage.Geometry,
        "Pixel": rd.ShaderStage.Pixel,
    }
    if name not in mapping:
        raise RuntimeError("Unknown texture stage %s" % name)
    return mapping[name]


def texture_description_map(controller):
    return {resource_name(texture.resourceId): texture for texture in controller.GetTextures()}


def export_texture(rd, controller, resource, texture, event_id, output_dir, texture_records, all_slices):
    key = resource_name(resource)
    if key in texture_records:
        return texture_records[key]
    slices = max(1, int(texture.arraysize)) if all_slices else 1
    files = []
    errors = []
    for slice_index in range(slices):
        suffix = "_slice_%03d" % slice_index if slices > 1 else ""
        path = output_dir / "textures" / ("resource_%s%s.png" % (resource_slug(resource), suffix))
        path.parent.mkdir(parents=True, exist_ok=True)
        save = rd.TextureSave()
        save.resourceId = resource
        save.destType = rd.FileType.PNG
        save.mip = 0
        save.slice.sliceIndex = slice_index
        save.sample.sampleIndex = 0
        save.alpha = rd.AlphaMapping.Preserve
        success = bool(controller.SaveTexture(save, str(path)))
        if success and path.is_file():
            files.append({"slice": slice_index, "file": relative(path, output_dir), "sha256": sha256(path.read_bytes())})
        else:
            errors.append({"slice": slice_index, "error": "SaveTexture returned false"})
    record = {
        "resourceId": key,
        "firstEvent": int(event_id),
        "width": int(texture.width),
        "height": int(texture.height),
        "depth": int(texture.depth),
        "arraySize": int(texture.arraysize),
        "mips": int(texture.mips),
        "format": str(texture.format.Name()),
        "files": files,
        "errors": errors,
    }
    texture_records[key] = record
    return record


def collect_bindings(rd, controller, pipeline, stage, event_id, output_dir, texture_records, textures, config):
    reflection = pipeline.GetShaderReflection(stage)
    reflected = list(reflection.readOnlyResources) if reflection else []
    bindings = []
    for binding in pipeline.GetReadOnlyResources(stage):
        index = int(binding.access.index)
        reflection_binding = reflected[index] if 0 <= index < len(reflected) else None
        metadata = descriptor_metadata(binding, reflection_binding)
        texture = textures.get(metadata["resourceId"])
        if texture is not None:
            record = export_texture(
                rd, controller, binding.descriptor.resource, texture, event_id, output_dir,
                texture_records, bool(config["textures"]["allSlices"]),
            )
            metadata["texture"] = record["files"][0]["file"] if record["files"] else None
        bindings.append(metadata)
    bindings.sort(key=lambda item: (item["shaderBindingIndex"], item["arrayElement"], item["resourceId"]))
    return bindings


def extract_draw(rd, controller, action, world_from_clip, camera_position, output_dir, config, shader_records, texture_records, textures, keep_raw):
    controller.SetFrameEvent(action.eventId, True)
    pipeline = controller.GetPipelineState()
    vertex_shader = resource_name(pipeline.GetShader(rd.ShaderStage.Vertex))
    pixel_shader = resource_name(pipeline.GetShader(rd.ShaderStage.Pixel))
    vertex_reflection = pipeline.GetShaderReflection(rd.ShaderStage.Vertex)
    position, outputs = signature_layout(rd, vertex_reflection)
    if position is None or not position["isFloat"] or position["compCount"] < 4:
        raise RuntimeError("Post-VS position is not float4")
    first = controller.GetPostVSData(0, 0, rd.MeshDataStage.VSOut)
    indices, index_data = parse_indices(rd, controller, first)
    if not indices:
        raise RuntimeError("Draw has no post-VS indices")
    vertex_count = max(indices) + 1
    stride = int(first.vertexByteStride)
    instance_count = max(1, int(action.numInstances))
    instance_bytes = vertex_count * stride
    last = first if instance_count == 1 else controller.GetPostVSData(instance_count - 1, 0, rd.MeshDataStage.VSOut)
    contiguous = (
        first.vertexResourceId == last.vertexResourceId
        and int(last.vertexByteOffset) == int(first.vertexByteOffset) + (instance_count - 1) * instance_bytes
    )
    if contiguous:
        raw_vertex_data = bytes(controller.GetBufferData(first.vertexResourceId, first.vertexByteOffset, instance_count * instance_bytes))
        if len(raw_vertex_data) != instance_count * instance_bytes:
            raise RuntimeError("Contiguous post-VS vertex read was truncated")
        chunks = [raw_vertex_data[index * instance_bytes:(index + 1) * instance_bytes] for index in range(instance_count)]
        source_layout = {
            "kind": "contiguous",
            "resourceId": resource_name(first.vertexResourceId),
            "firstAbsoluteByteOffset": int(first.vertexByteOffset),
            "instanceByteSize": instance_bytes,
            "instanceCount": instance_count,
        }
    else:
        chunks = []
        sources = []
        for instance in range(instance_count):
            mesh = controller.GetPostVSData(instance, 0, rd.MeshDataStage.VSOut)
            data = bytes(controller.GetBufferData(mesh.vertexResourceId, mesh.vertexByteOffset, instance_bytes))
            if len(data) != instance_bytes:
                raise RuntimeError("Post-VS vertex read was truncated for instance %d" % instance)
            chunks.append(data)
            sources.append({"instance": instance, "resourceId": resource_name(mesh.vertexResourceId), "absoluteByteOffset": int(mesh.vertexByteOffset)})
        raw_vertex_data = b"".join(chunks)
        source_layout = {"kind": "perInstance", "sources": sources}
    sample_indices = list(dict.fromkeys(indices))[:64]
    uv_output, normal_output = choose_attributes(outputs, chunks[0], stride, sample_indices, vertex_shader, config)
    source_triangles = triangles_for_topology(rd, first.topology, indices)
    positions = []
    uvs = []
    normals = []
    triangles = []
    seen_triangles = set()
    duplicate_triangles = 0
    projection_errors = []
    invalid_normals = 0
    clip_from_world = invert_matrix(world_from_clip)
    for instance, chunk in enumerate(chunks):
        vertex_base = instance * vertex_count
        for vertex in range(vertex_count):
            clip = list(struct.unpack_from("<4f", chunk, vertex * stride + position["byteOffset"]))
            world_h = matrix_vector(world_from_clip, clip)
            if abs(world_h[3]) < 1.0e-12 or not all(math.isfinite(value) for value in world_h):
                raise RuntimeError("Invalid homogeneous world position for vertex %d instance %d" % (vertex, instance))
            world = [world_h[index] / world_h[3] for index in range(3)]
            positions.extend(world[index] - camera_position[index] for index in range(3))
            reprojection = matrix_vector(clip_from_world, world + [1.0])
            clip_ndc = [clip[index] / clip[3] for index in range(3)]
            reprojection_ndc = [reprojection[index] / reprojection[3] for index in range(3)]
            projection_errors.extend(abs(reprojection_ndc[index] - clip_ndc[index]) for index in range(3))
            if uv_output is not None:
                output = outputs[uv_output]
                uv = struct.unpack_from("<" + "f" * output["compCount"], chunk, vertex * stride + output["byteOffset"])
                uvs.extend((uv[0], uv[1]))
            if normal_output is not None:
                output = outputs[normal_output]
                normal = list(struct.unpack_from("<" + "f" * output["compCount"], chunk, vertex * stride + output["byteOffset"]))[:3]
                length = vector_length(normal)
                if length > 1.0e-12 and all(math.isfinite(value) for value in normal):
                    normals.extend(value / length for value in normal)
                else:
                    normals.extend((0.0, 1.0, 0.0))
                    invalid_normals += 1
        for triangle in source_triangles:
            expanded = tuple(vertex_base + value for value in triangle)
            key = tuple(sorted(expanded))
            if key in seen_triangles:
                duplicate_triangles += 1
                continue
            seen_triangles.add(key)
            triangles.extend(expanded)
    event_name = "eid_%06d" % int(action.eventId)
    mesh_dir = output_dir / "meshes" / event_name
    positions_path = mesh_dir / "positions.f32"
    indices_path = mesh_dir / "triangles.u32"
    uv_path = mesh_dir / "uv0.f32"
    normal_path = mesh_dir / "normals.f32"
    files = {
        "positions": {"file": relative(positions_path, output_dir), "sha256": write_float_file(positions_path, positions)},
        "triangles": {"file": relative(indices_path, output_dir), "sha256": write_uint_file(indices_path, triangles)},
    }
    if uvs:
        files["uv0"] = {"file": relative(uv_path, output_dir), "sha256": write_float_file(uv_path, uvs)}
    if normals:
        files["normals"] = {"file": relative(normal_path, output_dir), "sha256": write_float_file(normal_path, normals)}
    raw = None
    if keep_raw:
        raw_vertex_path = mesh_dir / "postvs_vertices.raw"
        raw_index_path = mesh_dir / "postvs_indices.raw"
        raw_vertex_path.write_bytes(raw_vertex_data)
        raw_index_path.write_bytes(index_data)
        raw = {
            "vertices": {"file": relative(raw_vertex_path, output_dir), "sha256": sha256(raw_vertex_data), "source": source_layout},
            "indices": {
                "file": relative(raw_index_path, output_dir),
                "sha256": sha256(index_data),
                "resourceId": resource_name(first.indexResourceId),
                "absoluteByteOffset": int(first.indexByteOffset),
                "byteStride": int(first.indexByteStride),
            },
        }
    vertex_shader_record = save_shader(rd, controller, pipeline, rd.ShaderStage.Vertex, output_dir, shader_records, config)
    pixel_shader_record = save_shader(rd, controller, pipeline, rd.ShaderStage.Pixel, output_dir, shader_records, config)
    bindings = {}
    for stage_name in config["textures"]["stages"]:
        stage = stage_from_name(rd, stage_name)
        bindings[stage_name] = collect_bindings(rd, controller, pipeline, stage, action.eventId, output_dir, texture_records, textures, config)
    pixel_textures = [binding for binding in bindings.get("Pixel", []) if binding.get("texture")]
    material_override = shader_override(config, "materials", pixel_shader)
    diffuse_slot = int(material_override.get("diffuseTextureSlot", config["materials"]["diffuseTextureSlot"]))
    diffuse = pixel_textures[diffuse_slot] if 0 <= diffuse_slot < len(pixel_textures) else None
    alpha_test = bool(pixel_shader_record and pixel_shader_record["alphaTest"])
    metadata = {
        "eventId": int(action.eventId),
        "actionId": int(action.actionId),
        "name": str(action.GetName(controller.GetStructuredFile())),
        "numIndices": int(action.numIndices),
        "numInstances": int(action.numInstances),
        "topology": str(first.topology),
        "vertexCount": vertex_count * instance_count,
        "triangleCount": len(triangles) // 3,
        "duplicateTrianglesSkipped": duplicate_triangles,
        "postVSVertexStride": stride,
        "postVSOutputs": outputs,
        "selectedAttributes": {"uvOutput": uv_output, "normalOutput": normal_output},
        "invalidNormals": invalid_normals,
        "reprojection": {"maxRelative": max(projection_errors), "meanRelative": sum(projection_errors) / len(projection_errors)},
        "files": files,
        "rawPostVS": raw,
        "shaders": {"vertex": vertex_shader_record, "pixel": pixel_shader_record},
        "resourceBindings": bindings,
        "material": {
            "diffuseTextureSlot": diffuse_slot,
            "diffuseTexture": diffuse["texture"] if diffuse else None,
            "diffuseResourceId": diffuse["resourceId"] if diffuse else None,
            "alphaTest": alpha_test,
            "key": "%s|%s|%s" % (pixel_shader, diffuse["resourceId"] if diffuse else "none", int(alpha_test)),
        },
    }
    json_write(mesh_dir / "mesh.json", metadata)
    metadata["metadataFile"] = relative(mesh_dir / "mesh.json", output_dir)
    return metadata


def run_blender(script_path, blender, manifest_path, output_dir, config, validate):
    importer = script_path.parent / "blender_import_scene.py"
    command = [
        str(Path(blender).resolve()),
        "--background",
        "--factory-startup",
        "--python",
        str(importer),
        "--",
        "--manifest",
        str(manifest_path),
        "--output",
        str(output_dir),
        "--scale",
        str(config["blender"]["scale"]),
    ]
    if config["blender"]["flipV"]:
        command.append("--flip-v")
    if config["blender"]["perDrawFbx"]:
        command.append("--per-draw-fbx")
    subprocess.run(command, check=True)
    if validate:
        validator = script_path.parent / "blender_validate_fbx.py"
        subprocess.run([
            str(Path(blender).resolve()),
            "--background",
            "--factory-startup",
            "--python",
            str(validator),
            "--",
            "--manifest",
            str(manifest_path),
            "--fbx",
            str(output_dir / "scene.fbx"),
            "--output",
            str(output_dir / "blender_validation.json"),
        ], check=True)


def export(arguments):
    script_path = Path(__file__).resolve()
    config = DEFAULT_CONFIG
    if arguments.config:
        config = deep_merge(config, json.loads(Path(arguments.config).read_text(encoding="utf-8")))
    if arguments.calibration_event is not None:
        config = deep_merge(config, {"camera": {"calibrationEvent": arguments.calibration_event}})
    if arguments.world_output is not None:
        config = deep_merge(config, {"camera": {"worldOutput": arguments.world_output}})
    if arguments.no_per_draw_fbx:
        config = deep_merge(config, {"blender": {"perDrawFbx": False}})
    output_dir = Path(arguments.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    rd = load_renderdoc(locate_renderdoc_bin(script_path, arguments.renderdoc_bin))
    rd.InitialiseReplay(rd.GlobalEnvironment(), [])
    capture = rd.OpenCaptureFile()
    controller = None
    try:
        result = capture.OpenFile(str(Path(arguments.capture).resolve()), "", None)
        if result != rd.ResultCode.Succeeded:
            raise RuntimeError("OpenFile failed: %s" % result)
        if not capture.LocalReplaySupport():
            raise RuntimeError("Capture cannot be replayed locally")
        result, controller = capture.OpenCapture(rd.ReplayOptions(), None)
        if result != rd.ResultCode.Succeeded:
            raise RuntimeError("OpenCapture failed: %s" % result)
        structured = controller.GetStructuredFile()
        actions = flatten_actions(controller.GetRootActions())
        actions_by_event = {int(action.eventId): action for action in actions}
        selected, all_passes = select_pass(rd, controller, actions, structured, arguments, config)
        draw_actions = selected.pop("drawActions")
        calibration_actions = draw_actions
        configured_matrix = config["camera"]["clipFromWorld"]
        if configured_matrix is not None:
            calibration = {"selection": "configuredMatrix", "matrix": configured_matrix, "sourceEvent": None, "crossValidation": []}
        else:
            calibration = calibration_from_override(rd, controller, actions_by_event, config)
            if calibration is None:
                calibration = auto_calibrate(rd, controller, calibration_actions, config)
        clip_from_world = calibration["matrix"]
        world_from_clip = invert_matrix(clip_from_world)
        camera = derive_camera(clip_from_world)
        calibration["camera"] = camera
        calibration["constantBuffers"] = (
            save_calibration_cbuffers(rd, controller, calibration["sourceEvent"], output_dir)
            if calibration.get("sourceEvent") is not None else []
        )
        json_write(output_dir / "camera_calibration.json", calibration)
        if arguments.max_draws is not None:
            draw_actions = draw_actions[:arguments.max_draws]
        textures = texture_description_map(controller)
        texture_records = {}
        shader_records = {}
        draws = []
        errors = []
        for draw_index, action in enumerate(draw_actions):
            print("[%d/%d] Exporting EID %d" % (draw_index + 1, len(draw_actions), action.eventId), flush=True)
            try:
                draws.append(extract_draw(
                    rd, controller, action, world_from_clip, camera["position"], output_dir, config,
                    shader_records, texture_records, textures, arguments.keep_raw_postvs,
                ))
            except Exception as error:
                errors.append({"eventId": int(action.eventId), "name": action_name(action, structured), "error": repr(error)})
                if arguments.strict:
                    raise
        pass_summary = {key: value for key, value in selected.items() if key != "drawActions"}
        pass_summary["drawCountRequested"] = len(draw_actions)
        manifest = {
            "schemaVersion": 1,
            "capture": str(Path(arguments.capture).resolve()),
            "api": str(controller.GetAPIProperties().pipelineType),
            "pass": pass_summary,
            "availablePasses": [
                {key: value for key, value in item.items() if key != "drawActions"}
                for item in all_passes
            ],
            "camera": {
                "origin": camera["position"],
                "right": camera["right"],
                "up": camera["up"],
                "forward": camera["forward"],
                "clipFromWorld": clip_from_world,
                "worldFromClip": world_from_clip,
                "calibration": "camera_calibration.json",
            },
            "coordinates": {
                "meshPositions": "capture world coordinates relative to the capture camera",
                "captureUp": "Y",
                "blenderConversion": "(X,Y,Z) -> (X,-Z,Y)",
                "unitScale": config["blender"]["scale"],
                "units": "Capture coordinate units; no metre conversion is asserted",
            },
            "config": config,
            "draws": draws,
            "textures": sorted(texture_records.values(), key=lambda item: item["resourceId"]),
            "shaders": sorted(shader_records.values(), key=lambda item: (item["stage"], item["resourceId"])),
            "errors": errors,
            "totals": {
                "draws": len(draws),
                "vertices": sum(draw["vertexCount"] for draw in draws),
                "triangles": sum(draw["triangleCount"] for draw in draws),
                "textures": len(texture_records),
                "shaders": len(shader_records),
            },
        }
        manifest_path = output_dir / "scene_manifest.json"
        json_write(manifest_path, manifest)
        if arguments.blender:
            run_blender(script_path, arguments.blender, manifest_path, output_dir, config, arguments.validate_fbx)
        return manifest_path, manifest
    finally:
        if controller is not None:
            controller.Shutdown()
        capture.Shutdown()
        rd.ShutdownReplay()


def parse_arguments():
    parser = argparse.ArgumentParser(description="Export a RenderDoc colour pass to Blender FBX resources")
    parser.add_argument("--capture", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--colour-pass", type=int, default=3)
    parser.add_argument("--begin-event", type=int)
    parser.add_argument("--end-event", type=int)
    parser.add_argument("--calibration-event", type=int)
    parser.add_argument("--world-output", type=int)
    parser.add_argument("--config")
    parser.add_argument("--renderdoc-bin")
    parser.add_argument("--blender")
    parser.add_argument("--max-draws", type=int)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--keep-raw-postvs", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--validate-fbx", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--no-per-draw-fbx", action="store_true")
    return parser.parse_args()


def main():
    path, manifest = export(parse_arguments())
    print(json.dumps({"manifest": str(path), "totals": manifest["totals"], "errors": manifest["errors"]}, indent=2, ensure_ascii=False))
    if manifest["errors"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
