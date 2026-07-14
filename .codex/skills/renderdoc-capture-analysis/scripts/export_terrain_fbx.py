#!/usr/bin/env python3
"""Export validated terrain post-VS data to an ASCII FBX mesh with a camera marker sphere."""

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path


def sub(left, right): return [left[index] - right[index] for index in range(3)]
def dot(left, right): return sum(left[index] * right[index] for index in range(3))
def cross(left, right): return [left[1] * right[2] - left[2] * right[1], left[2] * right[0] - left[0] * right[2], left[0] * right[1] - left[1] * right[0]]
def norm(vector): return math.sqrt(dot(vector, vector))
def normalise(vector):
    value = norm(vector)
    return [0.0, 1.0, 0.0] if value < 1.0e-12 else [component / value for component in vector]
def float_text(value):
    return format(0.0 if abs(value) < 1.0e-15 else value, ".9g")

def write_array(handle, name, values, formatter, indent="        ", per_line=18):
    handle.write(f"{indent}{name}: *{len(values)} {{\n")
    handle.write(f"{indent}    a: ")
    for index, value in enumerate(values):
        if index and index % per_line == 0:
            handle.write("\n" + indent + "    ")
        elif index:
            handle.write(",")
        handle.write(formatter(value))
    handle.write("\n" + indent + "}\n")

def write_geometry(handle, object_id, name, vertices, polygons, polygon_normals):
    flattened_vertices = [value for vertex in vertices for value in vertex]
    flattened_normals = [value for normal in polygon_normals for value in normal]
    handle.write(f'    Geometry: {object_id}, "Geometry::{name}", "Mesh" {{\n')
    handle.write("        GeometryVersion: 124\n")
    write_array(handle, "Vertices", flattened_vertices, float_text)
    write_array(handle, "PolygonVertexIndex", polygons, str)
    handle.write("        LayerElementNormal: 0 {\n")
    handle.write("            Version: 101\n            Name: \"\"\n            MappingInformationType: \"ByPolygonVertex\"\n            ReferenceInformationType: \"Direct\"\n")
    write_array(handle, "Normals", flattened_normals, float_text, indent="            ")
    handle.write("        }\n")
    handle.write("        Layer: 0 {\n            Version: 100\n            LayerElement: {\n                Type: \"LayerElementNormal\"\n                TypedIndex: 0\n            }\n        }\n")
    handle.write("    }\n")

def write_model(handle, object_id, name, translation):
    handle.write(f'    Model: {object_id}, "Model::{name}", "Mesh" {{\n')
    handle.write("        Version: 232\n        Properties70:  {\n")
    handle.write(f'            P: "Lcl Translation", "Lcl Translation", "", "A",{float_text(translation[0])},{float_text(translation[1])},{float_text(translation[2])}\n')
    handle.write("            P: \"Lcl Rotation\", \"Lcl Rotation\", \"\", \"A\",0,0,0\n            P: \"Lcl Scaling\", \"Lcl Scaling\", \"\", \"A\",1,1,1\n        }\n        Shading: T\n        Culling: \"CullingOff\"\n    }\n")

def sphere_mesh(radius, segments, rings):
    vertices = [[0.0, radius, 0.0]]
    for ring in range(1, rings):
        phi = math.pi * ring / rings
        y = radius * math.cos(phi)
        radial = radius * math.sin(phi)
        for segment in range(segments):
            theta = 2.0 * math.pi * segment / segments
            vertices.append([radial * math.cos(theta), y, radial * math.sin(theta)])
    bottom_index = len(vertices)
    vertices.append([0.0, -radius, 0.0])
    polygons, normals = [], []
    for segment in range(segments):
        next_segment = (segment + 1) % segments
        polygons.extend([0, 1 + next_segment, -(1 + segment) - 1])
        normals.extend([normalise(vertices[0]), normalise(vertices[1 + next_segment]), normalise(vertices[1 + segment])])
    for ring in range(1, rings - 1):
        current = 1 + (ring - 1) * segments
        following = current + segments
        for segment in range(segments):
            next_segment = (segment + 1) % segments
            quad = [current + segment, current + next_segment, following + next_segment, following + segment]
            polygons.extend([quad[0], quad[1], -quad[2] - 1, quad[0], quad[2], -quad[3] - 1])
            normals.extend([normalise(vertices[index]) for index in (quad[0], quad[1], quad[2], quad[0], quad[2], quad[3])])
    last_ring = 1 + (rings - 2) * segments
    for segment in range(segments):
        next_segment = (segment + 1) % segments
        polygons.extend([last_ring + segment, last_ring + next_segment, -bottom_index - 1])
        normals.extend([normalise(vertices[last_ring + segment]), normalise(vertices[last_ring + next_segment]), normalise(vertices[bottom_index])])
    return vertices, polygons, normals

def load_terrain(evidence, vertex_data, index_data):
    post = evidence["postVS"]
    event = evidence["event"]
    stride = int(post["vertexByteStride"])
    vertex_count = int(post["vertexCountPerInstance"])
    instance_count = int(event["numInstances"])
    if stride < 48 or len(vertex_data) != stride * vertex_count * instance_count:
        raise ValueError("Post-VS stream does not match evidence dimensions")
    if int(post["indexByteStride"]) != 2:
        raise ValueError("This exporter currently expects uint16 post-VS indices")
    indices = list(struct.unpack("<" + "H" * (len(index_data) // 2), index_data))
    vertices, normals = [], []
    for instance in range(instance_count):
        for vertex in range(vertex_count):
            values = struct.unpack_from("<12f", vertex_data, (instance * vertex_count + vertex) * stride)
            vertices.append([values[4], values[5], values[6]])
            normals.append(normalise([values[8], values[9], values[10]]))
    polygons, polygon_normals, skipped = [], [], 0
    for instance in range(instance_count):
        base = instance * vertex_count
        for start in range(0, len(indices), 3):
            local = indices[start:start + 3]
            source = [base + index for index in local]
            positions = [vertices[index] for index in source]
            face_normal = cross(sub(positions[1], positions[0]), sub(positions[2], positions[0]))
            if norm(face_normal) <= 1.0e-12:
                skipped += 1
                continue
            polygons.extend([source[0], source[1], -source[2] - 1])
            polygon_normals.extend([normals[index] for index in source])
    return vertices, polygons, polygon_normals, skipped, indices

def export_fbx(output_path, terrain_vertices, terrain_polygons, terrain_normals, sphere_vertices, sphere_polygons, sphere_normals, camera):
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("; FBX 7.4.0 project file\n; Generated from RenderDoc post-VS evidence\n\n")
        handle.write("FBXHeaderExtension:  {\n    FBXHeaderVersion: 1003\n    FBXVersion: 7400\n    Creator: \"RenderDoc Capture Analysis\"\n}\n")
        handle.write("GlobalSettings:  {\n    Version: 1000\n    Properties70:  {\n        P: \"UpAxis\", \"int\", \"Integer\", \"\",1\n        P: \"UpAxisSign\", \"int\", \"Integer\", \"\",1\n        P: \"FrontAxis\", \"int\", \"Integer\", \"\",2\n        P: \"FrontAxisSign\", \"int\", \"Integer\", \"\",-1\n        P: \"CoordAxis\", \"int\", \"Integer\", \"\",0\n        P: \"CoordAxisSign\", \"int\", \"Integer\", \"\",1\n        P: \"UnitScaleFactor\", \"double\", \"Number\", \"\",1\n        P: \"OriginalUnitScaleFactor\", \"double\", \"Number\", \"\",1\n    }\n}\n")
        handle.write("Definitions:  {\n    Version: 100\n    Count: 4\n    ObjectType: \"Geometry\" { Count: 2 }\n    ObjectType: \"Model\" { Count: 2 }\n}\n")
        handle.write("Objects:  {\n")
        write_geometry(handle, 100000, "Terrain_PostVS_EID_1026", terrain_vertices, terrain_polygons, terrain_normals)
        write_model(handle, 100001, "Terrain_PostVS_EID_1026", [0.0, 0.0, 0.0])
        write_geometry(handle, 100002, "Camera_Position_Marker_Sphere", sphere_vertices, sphere_polygons, sphere_normals)
        write_model(handle, 100003, "Camera_Position_Marker_Sphere", camera)
        handle.write("}\nConnections:  {\n    C: \"OO\",100000,100001\n    C: \"OO\",100001,0\n    C: \"OO\",100002,100003\n    C: \"OO\",100003,0\n}\n")

def main():
    parser = argparse.ArgumentParser(description="Export terrain post-VS data and a camera sphere marker to ASCII FBX")
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--vertices", required=True)
    parser.add_argument("--indices", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--camera-radius", type=float, default=32.0)
    parser.add_argument("--sphere-segments", type=int, default=32)
    parser.add_argument("--sphere-rings", type=int, default=16)
    arguments = parser.parse_args()
    evidence_path, vertex_path, index_path, output_path = map(Path, (arguments.evidence, arguments.vertices, arguments.indices, arguments.output))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    vertex_data, index_data = vertex_path.read_bytes(), index_path.read_bytes()
    expected_hash = evidence["postVS"]["sha256"]
    actual_hash = hashlib.sha256(vertex_data).hexdigest()
    if actual_hash != expected_hash: raise ValueError("Post-VS vertex hash does not match terrain_evidence.json")
    terrain_vertices, terrain_polygons, terrain_normals, skipped, indices = load_terrain(evidence, vertex_data, index_data)
    expected_triangles = int(evidence["geometry"]["nonDegenerateTriangles"])
    exported_triangles = len(terrain_polygons) // 3
    if exported_triangles != expected_triangles: raise ValueError(f"Expected {expected_triangles} non-degenerate triangles, exported {exported_triangles}")
    sphere_vertices, sphere_polygons, sphere_normals = sphere_mesh(arguments.camera_radius, arguments.sphere_segments, arguments.sphere_rings)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    export_fbx(output_path, terrain_vertices, terrain_polygons, terrain_normals, sphere_vertices, sphere_polygons, sphere_normals, evidence["camera"]["position"])
    manifest = {
        "fbx": str(output_path.resolve()), "terrain": {"vertices": len(terrain_vertices), "triangles": exported_triangles, "degenerateTrianglesSkipped": skipped, "postVSHash": actual_hash, "indexCount": len(indices)},
        "cameraMarker": {"name": "Camera_Position_Marker_Sphere", "position": evidence["camera"]["position"], "radius": arguments.camera_radius, "vertices": len(sphere_vertices), "triangles": len(sphere_polygons) // 3},
        "units": evidence["units"],
    }
    manifest_path = output_path.with_suffix(output_path.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2))

if __name__ == "__main__": main()