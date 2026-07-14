#!/usr/bin/env python3
"""Produce validated world-space terrain evidence from a RenderDoc draw call."""

import argparse
import hashlib
import json
import math
import os
import struct
from pathlib import Path


def sub(left, right): return [left[i] - right[i] for i in range(len(left))]
def add(left, right): return [left[i] + right[i] for i in range(len(left))]
def scale(vector, scalar): return [value * scalar for value in vector]
def dot(left, right): return sum(left[i] * right[i] for i in range(len(left)))
def cross(left, right): return [left[1]*right[2]-left[2]*right[1], left[2]*right[0]-left[0]*right[2], left[0]*right[1]-left[1]*right[0]]
def norm(vector): return math.sqrt(dot(vector, vector))
def normalise(vector):
    value = norm(vector)
    if value < 1.0e-12: raise ValueError("Cannot normalise zero-length vector")
    return scale(vector, 1.0 / value)
def mat_mul(left, right): return [[sum(left[row][i] * right[i][column] for i in range(4)) for column in range(4)] for row in range(4)]
def mat_vec(matrix, vector): return [sum(matrix[row][column] * vector[column] for column in range(4)) for row in range(4)]
def flatten(actions):
    result = []
    for action in actions:
        result.append(action)
        result.extend(flatten(action.children))
    return result

def invert4(matrix):
    rows = [list(matrix[row]) + [1.0 if row == column else 0.0 for column in range(4)] for row in range(4)]
    for column in range(4):
        pivot = max(range(column, 4), key=lambda row: abs(rows[row][column]))
        if abs(rows[pivot][column]) < 1.0e-12: raise ValueError("The captured local-to-world matrix is singular")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        rows[column] = [value / divisor for value in rows[column]]
        for row in range(4):
            if row != column:
                factor = rows[row][column]
                rows[row] = [rows[row][entry] - factor * rows[column][entry] for entry in range(8)]
    return [row[4:] for row in rows]

def matrix_from_bytes(data, offset, rows):
    values = struct.unpack_from("<" + "f" * (rows * 4), data, offset)
    return [list(values[row * 4 : row * 4 + 4]) for row in range(rows)]

def parse_indices(data, stride):
    formats = {1: "B", 2: "H", 4: "I"}
    if stride not in formats: raise ValueError("Unsupported post-VS index stride %d" % stride)
    return list(struct.unpack("<" + formats[stride] * (len(data) // stride), data))

def bounds(points):
    minimum = [min(point[i] for point in points) for i in range(3)]
    maximum = [max(point[i] for point in points) for i in range(3)]
    return {"min": minimum, "max": maximum, "span": sub(maximum, minimum)}

def summary(values): return {"min": min(values), "max": max(values), "mean": sum(values) / len(values)}

def point_triangle_distance(point, vertex0, vertex1, vertex2):
    edge0, edge1, point0 = sub(vertex1, vertex0), sub(vertex2, vertex0), sub(point, vertex0)
    dot00, dot01 = dot(edge0, point0), dot(edge1, point0)
    if dot00 <= 0.0 and dot01 <= 0.0: return norm(point0)
    point1 = sub(point, vertex1); dot10, dot11 = dot(edge0, point1), dot(edge1, point1)
    if dot10 >= 0.0 and dot11 <= dot10: return norm(point1)
    area0 = dot00 * dot11 - dot10 * dot01
    if area0 <= 0.0 and dot00 >= 0.0 and dot10 <= 0.0: return norm(sub(point0, scale(edge0, dot00 / (dot00 - dot10))))
    point2 = sub(point, vertex2); dot20, dot21 = dot(edge0, point2), dot(edge1, point2)
    if dot21 >= 0.0 and dot20 <= dot21: return norm(point2)
    area1 = dot20 * dot01 - dot00 * dot21
    if area1 <= 0.0 and dot01 >= 0.0 and dot21 <= 0.0: return norm(sub(point0, scale(edge1, dot01 / (dot01 - dot21))))
    denominator = area0 + area1 + dot10 * dot21 - dot20 * dot11
    if abs(denominator) < 1.0e-20: return min(norm(point0), norm(point1), norm(point2))
    closest = add(vertex0, add(scale(edge0, area0 / denominator), scale(edge1, area1 / denominator)))
    return norm(sub(point, closest))

def derive_camera(clip_from_world):
    row0, row1, row3 = clip_from_world[0], clip_from_world[1], clip_from_world[3]
    forward_scale = norm(row3[:3]); forward = normalise(row3[:3])
    row0_forward, row1_forward = dot(row0[:3], forward), dot(row1[:3], forward)
    right_raw, up_raw = sub(row0[:3], scale(forward, row0_forward)), sub(row1[:3], scale(forward, row1_forward))
    right_scale, up_scale = norm(right_raw), norm(up_raw)
    right, up = normalise(right_raw), normalise(up_raw)
    forward_coordinate = -row3[3] / forward_scale
    right_coordinate = -(row0[3] - row0_forward * row3[3] / forward_scale) / right_scale
    up_coordinate = -(row1[3] - row1_forward * row3[3] / forward_scale) / up_scale
    position = add(add(scale(right, right_coordinate), scale(up, up_coordinate)), scale(forward, forward_coordinate))
    return {"position": position, "right": right, "up": up, "forward": forward, "cameraClipW": mat_vec(clip_from_world, position + [1.0])[3], "projectionXScale": right_scale, "projectionYScale": up_scale}

def locate_bin(script_path, override):
    if override: return Path(override)
    for parent in script_path.resolve().parents:
        candidate = parent / "x64" / "Development"
        if candidate.is_dir(): return candidate
    return None

def load_renderdoc(bin_dir):
    if os.name == "nt" and bin_dir:
        os.add_dll_directory(str(bin_dir))
        modules = bin_dir / "pymodules"
        if modules.is_dir(): os.add_dll_directory(str(modules))
    try: import renderdoc as rd
    except ImportError as error: raise RuntimeError("Set PYTHONPATH to x64/Development/pymodules and use the matching Python ABI") from error
    return rd

def analyze(arguments):
    rd = load_renderdoc(locate_bin(Path(__file__), arguments.renderdoc_bin))
    out_dir = Path(arguments.output).resolve(); out_dir.mkdir(parents=True, exist_ok=True)
    rd.InitialiseReplay(rd.GlobalEnvironment(), [])
    capture = rd.OpenCaptureFile(); controller = None
    try:
        result = capture.OpenFile(str(Path(arguments.capture).resolve()), "", None)
        if result != rd.ResultCode.Succeeded: raise RuntimeError("OpenFile failed: %s" % result)
        replay_result, controller = capture.OpenCapture(rd.ReplayOptions(), None)
        if replay_result != rd.ResultCode.Succeeded: raise RuntimeError("OpenCapture failed: %s" % replay_result)
        actions = [action for action in flatten(controller.GetRootActions()) if action.eventId == arguments.event]
        if len(actions) != 1: raise RuntimeError("Expected one action for event %d, got %d" % (arguments.event, len(actions)))
        action = actions[0]
        if not action.flags & rd.ActionFlags.Drawcall or not action.flags & rd.ActionFlags.Instanced: raise RuntimeError("Event %d must be an instanced draw call" % arguments.event)
        controller.SetFrameEvent(arguments.event, True)
        pipeline = controller.GetPipelineState(); vertex_shader = pipeline.GetShaderReflection(rd.ShaderStage.Vertex)
        if vertex_shader is None or arguments.cbuffer_index >= len(vertex_shader.constantBlocks): raise RuntimeError("Vertex CBuffer index %d is unavailable" % arguments.cbuffer_index)
        descriptor = pipeline.GetConstantBlock(rd.ShaderStage.Vertex, arguments.cbuffer_index, 0).descriptor
        cbuffer = bytes(controller.GetBufferData(descriptor.resource, descriptor.byteOffset, descriptor.byteSize))
        local_to_world = matrix_from_bytes(cbuffer, arguments.local_to_world_offset, 3) + [[0.0, 0.0, 0.0, 1.0]]
        local_to_clip = matrix_from_bytes(cbuffer, arguments.local_to_clip_offset, 4)
        clip_from_world = mat_mul(local_to_clip, invert4(local_to_world)); camera = derive_camera(clip_from_world)
        first = controller.GetPostVSData(0, 0, rd.MeshDataStage.VSOut); last = controller.GetPostVSData(action.numInstances - 1, 0, rd.MeshDataStage.VSOut)
        index_data = bytes(controller.GetBufferData(first.indexResourceId, first.indexByteOffset, first.numIndices * first.indexByteStride))
        indices = parse_indices(index_data, first.indexByteStride); vertices = sorted(set(indices)); vertex_count = max(vertices) + 1
        if first.vertexByteStride < 96: raise RuntimeError("Post-VS stride %d cannot hold gl_Position plus five float4 outputs" % first.vertexByteStride)
        instance_bytes = vertex_count * first.vertexByteStride
        if last.vertexByteOffset != first.vertexByteOffset + (action.numInstances - 1) * instance_bytes: raise RuntimeError("Post-VS data is not a contiguous per-instance stream")
        postvs = bytes(controller.GetBufferData(first.vertexResourceId, first.vertexByteOffset, action.numInstances * instance_bytes))
        if len(postvs) != action.numInstances * instance_bytes: raise RuntimeError("Post-VS data read was truncated")
        tiles, all_points, errors = [], [], []
        farthest_3d, farthest_xz = {"distance": -1.0}, {"distance": -1.0}
        for instance in range(action.numInstances):
            tile = []
            for vertex in vertices:
                values = struct.unpack_from("<24f", postvs, instance * instance_bytes + vertex * first.vertexByteStride)
                clip, world = list(values[:4]), list(values[4:7]); projected = mat_vec(clip_from_world, world + [1.0]); projected[2] = 2.0 * projected[2] - projected[3]
                errors.extend(abs(projected[i] - clip[i]) for i in range(4))
                distance3d = norm(sub(world, camera["position"])); distance_xz = math.hypot(world[0] - camera["position"][0], world[2] - camera["position"][2])
                if distance3d > farthest_3d["distance"]: farthest_3d = {"distance": distance3d, "instance": instance, "vertex": vertex, "worldPosition": world}
                if distance_xz > farthest_xz["distance"]: farthest_xz = {"distance": distance_xz, "instance": instance, "vertex": vertex, "worldPosition": world}
                tile.append(world); all_points.append(world)
            tiles.append(tile)
        nearest_surface = {"distance": math.inf}; surface_area = 0.0; projected_area = 0.0; nondegenerate = 0
        for instance, tile in enumerate(tiles):
            for triangle_offset in range(0, len(indices), 3):
                vertex0, vertex1, vertex2 = [tile[indices[triangle_offset + i]] for i in range(3)]
                area = 0.5 * norm(cross(sub(vertex1, vertex0), sub(vertex2, vertex0)))
                if area <= 1.0e-12: continue
                nondegenerate += 1; surface_area += area
                projected_area += 0.5 * abs((vertex1[0] - vertex0[0]) * (vertex2[2] - vertex0[2]) - (vertex2[0] - vertex0[0]) * (vertex1[2] - vertex0[2]))
                distance = point_triangle_distance(camera["position"], vertex0, vertex1, vertex2)
                if distance < nearest_surface["distance"]: nearest_surface = {"distance": distance, "instance": instance, "triangle": triangle_offset // 3}
        world_bounds = bounds(all_points); per_tile = [bounds(tile)["span"] for tile in tiles]
        name = str(action.customName) if action.customName else str(action.GetName(controller.GetStructuredFile()))
        output = {
            "capture": str(Path(arguments.capture).resolve()),
            "event": {"eventId": int(action.eventId), "actionId": int(action.actionId), "name": name, "numIndices": int(action.numIndices), "numInstances": int(action.numInstances), "flags": int(action.flags)},
            "constantBuffer": {"index": arguments.cbuffer_index, "resourceId": str(descriptor.resource), "descriptorByteOffset": int(descriptor.byteOffset), "descriptorByteSize": int(descriptor.byteSize), "sha256": hashlib.sha256(cbuffer).hexdigest(), "localToWorld": local_to_world, "localToClip": local_to_clip, "clipFromWorld": clip_from_world},
            "postVS": {"vertexResourceId": str(first.vertexResourceId), "vertexByteOffset": int(first.vertexByteOffset), "vertexByteStride": int(first.vertexByteStride), "vertexCountPerInstance": vertex_count, "indexResourceId": str(first.indexResourceId), "indexByteOffset": int(first.indexByteOffset), "indexByteStride": int(first.indexByteStride), "indices": indices, "sha256": hashlib.sha256(postvs).hexdigest(), "worldPositionRecordOffset": 16},
            "verification": {"matrixConvention": "row-major matrices multiplied by column vectors; shader applies final z=2*z-w", "projectionMaxAbsoluteError": max(errors), "projectionMeanAbsoluteError": sum(errors) / len(errors), "tolerance": arguments.tolerance, "verified": max(errors) <= arguments.tolerance},
            "camera": camera,
            "geometry": {"usedVerticesPerInstance": len(vertices), "totalUsedVertices": len(all_points), "trianglesIssued": len(indices) // 3 * int(action.numInstances), "nonDegenerateTriangles": nondegenerate, "worldAABB": world_bounds, "worldAABBDiagonal": norm(world_bounds["span"]), "worldXZProjectedAABB": {"min": [world_bounds["min"][0], world_bounds["min"][2]], "max": [world_bounds["max"][0], world_bounds["max"][2]], "span": [world_bounds["span"][0], world_bounds["span"][2]], "diagonal": math.hypot(world_bounds["span"][0], world_bounds["span"][2])}, "summedSurfaceArea": surface_area, "summedWorldXZProjectedArea": projected_area, "perInstanceAABBSpan": {"x": summary([value[0] for value in per_tile]), "y": summary([value[1] for value in per_tile]), "z": summary([value[2] for value in per_tile])}},
            "distanceFromCamera": {"nearestSurfaceEuclidean": nearest_surface, "farthestVertexEuclidean": farthest_3d, "farthestVertexHorizontalXZ": farthest_xz},
            "units": "Capture world-coordinate units. This script does not assert a metre conversion."
        }
        (out_dir / "vertex_cbuffer_raw.bin").write_bytes(cbuffer); (out_dir / "postvs_vertices_raw.bin").write_bytes(postvs); (out_dir / "postvs_indices_raw.bin").write_bytes(index_data)
        destination = out_dir / "terrain_evidence.json"; destination.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
        return destination, output
    finally:
        if controller is not None: controller.Shutdown()
        capture.Shutdown(); rd.ShutdownReplay()

def main():
    parser = argparse.ArgumentParser(description="Validate terrain world bounds from a RenderDoc event")
    parser.add_argument("--capture", required=True); parser.add_argument("--event", required=True, type=int); parser.add_argument("--output", required=True)
    parser.add_argument("--renderdoc-bin"); parser.add_argument("--cbuffer-index", type=int, default=1); parser.add_argument("--local-to-world-offset", type=int, default=0); parser.add_argument("--local-to-clip-offset", type=int, default=112); parser.add_argument("--tolerance", type=float, default=1.0e-3)
    path, evidence = analyze(parser.parse_args())
    print(json.dumps({"evidence": str(path), "verified": evidence["verification"]["verified"], "camera": evidence["camera"]["position"], "worldAABB": evidence["geometry"]["worldAABB"], "farthestVertexEuclidean": evidence["distanceFromCamera"]["farthestVertexEuclidean"]}, indent=2))

if __name__ == "__main__": main()