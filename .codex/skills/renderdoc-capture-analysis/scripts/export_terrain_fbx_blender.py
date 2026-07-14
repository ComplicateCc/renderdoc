import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

import bpy


def sub(left, right): return [left[index] - right[index] for index in range(3)]
def dot(left, right): return sum(left[index] * right[index] for index in range(3))
def cross(left, right): return [left[1] * right[2] - left[2] * right[1], left[2] * right[0] - left[0] * right[2], left[0] * right[1] - left[1] * right[0]]
def norm(vector): return math.sqrt(dot(vector, vector))
def blender_position(position): return (position[0], -position[2], position[1])

def parse_arguments():
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="Export validated terrain post-VS data through Blender's binary FBX writer")
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--vertices", required=True)
    parser.add_argument("--indices", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--camera-radius", type=float, default=32.0)
    return parser.parse_args(arguments)

def main():
    arguments = parse_arguments()
    evidence_path, vertices_path, indices_path, output_path = map(Path, (arguments.evidence, arguments.vertices, arguments.indices, arguments.output))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    vertex_data, index_data = vertices_path.read_bytes(), indices_path.read_bytes()
    if hashlib.sha256(vertex_data).hexdigest() != evidence["postVS"]["sha256"]:
        raise ValueError("Post-VS vertex hash does not match terrain_evidence.json")
    stride = int(evidence["postVS"]["vertexByteStride"])
    vertex_count = int(evidence["postVS"]["vertexCountPerInstance"])
    instance_count = int(evidence["event"]["numInstances"])
    if stride < 48 or len(vertex_data) != stride * vertex_count * instance_count:
        raise ValueError("Post-VS vertex stream does not match evidence dimensions")
    if int(evidence["postVS"]["indexByteStride"]) != 2:
        raise ValueError("This exporter expects uint16 post-VS indices")
    indices = list(struct.unpack("<" + "H" * (len(index_data) // 2), index_data))

    terrain_vertices, terrain_faces, skipped = [], [], 0
    capture_positions = []
    for instance in range(instance_count):
        base = len(terrain_vertices)
        positions = []
        for vertex in range(vertex_count):
            values = struct.unpack_from("<12f", vertex_data, (instance * vertex_count + vertex) * stride)
            capture_position = [values[4], values[5], values[6]]
            positions.append(capture_position)
            capture_positions.append(capture_position)
            terrain_vertices.append(blender_position(capture_position))
        for start in range(0, len(indices), 3):
            local = indices[start:start + 3]
            face_normal = cross(sub(positions[local[1]], positions[local[0]]), sub(positions[local[2]], positions[local[0]]))
            if norm(face_normal) <= 1.0e-12:
                skipped += 1
                continue
            terrain_faces.append((base + local[0], base + local[1], base + local[2]))

    expected_triangles = int(evidence["geometry"]["nonDegenerateTriangles"])
    if len(terrain_faces) != expected_triangles:
        raise ValueError("Non-degenerate triangle count differs from terrain evidence")

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    terrain_mesh = bpy.data.meshes.new("Terrain_PostVS_EID_1026")
    terrain_mesh.from_pydata(terrain_vertices, [], terrain_faces)
    terrain_mesh.update()
    terrain = bpy.data.objects.new("Terrain_PostVS_EID_1026", terrain_mesh)
    bpy.context.collection.objects.link(terrain)
    terrain["source"] = "RenderDoc EID 1026 post-VS world positions"
    terrain["capture_units"] = "No metres-per-unit conversion asserted"
    terrain["vertices"] = len(terrain_vertices)
    terrain["triangles"] = len(terrain_faces)

    camera_capture = evidence["camera"]["position"]
    camera_blender = blender_position(camera_capture)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=arguments.camera_radius, location=camera_blender)
    marker = bpy.context.active_object
    marker.name = "Camera_Position_Marker_Sphere"
    marker.data.name = "Camera_Position_Marker_Sphere"
    marker["capture_position"] = list(camera_capture)
    marker["capture_radius"] = arguments.camera_radius

    output_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.fbx(filepath=str(output_path), use_selection=False, object_types={"MESH"}, add_leaf_bones=False, bake_anim=False, axis_forward="-Z", axis_up="Y")

    manifest = {
        "fbx": str(output_path.resolve()),
        "terrain": {"vertices": len(terrain_vertices), "triangles": len(terrain_faces), "degenerateTrianglesSkipped": skipped, "postVSHash": evidence["postVS"]["sha256"]},
        "cameraMarker": {"name": marker.name, "capturePosition": list(camera_capture), "blenderPosition": list(camera_blender), "radius": arguments.camera_radius},
        "coordinateConversion": "capture (X,Y,Z, Y-up) -> Blender (X,-Z,Y, Z-up)",
        "units": evidence["units"],
    }
    manifest_path = output_path.with_suffix(output_path.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    main()