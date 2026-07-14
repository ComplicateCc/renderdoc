import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def sub(left, right): return [left[index] - right[index] for index in range(3)]
def dot(left, right): return sum(left[index] * right[index] for index in range(3))
def cross(left, right): return [left[1] * right[2] - left[2] * right[1], left[2] * right[0] - left[0] * right[2], left[0] * right[1] - left[1] * right[0]]
def norm(vector): return math.sqrt(dot(vector, vector))

def arguments():
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--vertices", required=True)
    parser.add_argument("--indices", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--blend", required=True)
    parser.add_argument("--preview", required=True)
    parser.add_argument("--scale", type=float, default=0.1)
    parser.add_argument("--camera-radius", type=float, default=32.0)
    return parser.parse_args(values)

def material(name, color, metallic=0.0, roughness=0.6):
    result = bpy.data.materials.new(name)
    result.diffuse_color = color
    result.use_nodes = True
    bsdf = result.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return result

def look_at(camera, target):
    camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()

def main():
    args = arguments()
    evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
    vertex_data, index_data = Path(args.vertices).read_bytes(), Path(args.indices).read_bytes()
    if hashlib.sha256(vertex_data).hexdigest() != evidence["postVS"]["sha256"]: raise ValueError("Post-VS hash mismatch")
    stride, vertex_count, instance_count = int(evidence["postVS"]["vertexByteStride"]), int(evidence["postVS"]["vertexCountPerInstance"]), int(evidence["event"]["numInstances"])
    if len(vertex_data) != stride * vertex_count * instance_count: raise ValueError("Post-VS dimensions mismatch")
    indices = list(struct.unpack("<" + "H" * (len(index_data) // 2), index_data))
    origin = evidence["camera"]["position"]
    terrain_vertices, terrain_faces, skipped = [], [], 0
    for instance in range(instance_count):
        base = len(terrain_vertices)
        capture_positions = []
        for vertex in range(vertex_count):
            values = struct.unpack_from("<12f", vertex_data, (instance * vertex_count + vertex) * stride)
            capture = [values[4], values[5], values[6]]
            capture_positions.append(capture)
            relative = [(capture[index] - origin[index]) * args.scale for index in range(3)]
            terrain_vertices.append((relative[0], -relative[2], relative[1]))
        for start in range(0, len(indices), 3):
            local = indices[start:start + 3]
            face_normal = cross(sub(capture_positions[local[1]], capture_positions[local[0]]), sub(capture_positions[local[2]], capture_positions[local[0]]))
            if norm(face_normal) <= 1.0e-12:
                skipped += 1
            else:
                terrain_faces.append((base + local[0], base + local[1], base + local[2]))
    if len(terrain_faces) != int(evidence["geometry"]["nonDegenerateTriangles"]): raise ValueError("Triangle count mismatch")

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    terrain_mesh = bpy.data.meshes.new("Terrain_PostVS_EID_1026")
    terrain_mesh.from_pydata(terrain_vertices, [], terrain_faces)
    terrain_mesh.update()
    terrain = bpy.data.objects.new("Terrain_PostVS_EID_1026__CameraRelative", terrain_mesh)
    bpy.context.collection.objects.link(terrain)
    terrain_mesh.materials.append(material("Terrain_Default_Material", (0.19, 0.42, 0.12, 1.0), roughness=0.82))
    for polygon in terrain_mesh.polygons: polygon.use_smooth = True
    terrain["coordinate_space"] = "camera-relative capture coordinates, then (X,-Z,Y) for Blender"
    terrain["capture_scale"] = args.scale
    terrain["capture_camera_origin"] = list(origin)

    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=args.camera_radius * args.scale, location=(0.0, 0.0, 0.0))
    marker = bpy.context.active_object
    marker.name = "Camera_Position_Marker_Sphere__Origin"
    marker.data.name = marker.name
    marker.data.materials.append(material("Camera_Marker_Default_Material", (0.92, 0.05, 0.02, 1.0), metallic=0.1, roughness=0.28))

    bounds_min = [min(vertex[index] for vertex in terrain_vertices) for index in range(3)]
    bounds_max = [max(vertex[index] for vertex in terrain_vertices) for index in range(3)]
    center = [(bounds_min[index] + bounds_max[index]) * 0.5 for index in range(3)]
    extent = max(bounds_max[index] - bounds_min[index] for index in range(3))

    bpy.ops.object.light_add(type="SUN", location=(0.0, 0.0, 120.0))
    sun = bpy.context.active_object
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(25.0), math.radians(-20.0), math.radians(-35.0))
    bpy.ops.object.light_add(type="AREA", location=(center[0] - extent * 0.5, center[1] - extent * 0.5, extent * 0.9))
    area = bpy.context.active_object
    area.data.energy = 16000.0
    area.data.shape = "DISK"
    area.data.size = max(20.0, extent * 0.7)
    look_at(area, center)
    bpy.ops.object.camera_add(location=(center[0] + extent * 0.75, center[1] - extent * 0.95, center[2] + extent * 0.7))
    render_camera = bpy.context.active_object
    render_camera.name = "Preview_Render_Camera"
    render_camera.data.lens = 52.0
    render_camera.data.clip_end = max(1000.0, extent * 8.0)
    look_at(render_camera, center)
    bpy.context.scene.camera = render_camera
    world = bpy.context.scene.world
    world.color = (0.035, 0.035, 0.035)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(Path(args.preview))

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    terrain.select_set(True)
    marker.select_set(True)
    bpy.context.view_layer.objects.active = terrain
    bpy.ops.export_scene.fbx(filepath=args.output, use_selection=True, object_types={"MESH"}, add_leaf_bones=False, bake_anim=False, axis_forward="-Z", axis_up="Y")
    bpy.ops.wm.save_as_mainfile(filepath=args.blend)
    bpy.ops.render.render(write_still=True)
    manifest = {
        "fbx": str(Path(args.output).resolve()), "blend": str(Path(args.blend).resolve()), "preview": str(Path(args.preview).resolve()),
        "terrain": {"vertices": len(terrain_vertices), "triangles": len(terrain_faces), "degenerateTrianglesSkipped": skipped, "material": "Terrain_Default_Material"},
        "cameraMarker": {"name": marker.name, "position": [0.0, 0.0, 0.0], "radius": args.camera_radius * args.scale, "material": "Camera_Marker_Default_Material"},
        "coordinateConversion": "camera-relative capture coordinates scaled by 0.1, then capture (X,Y,Z) -> Blender (X,-Z,Y)",
    }
    Path(args.output + ".manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2))

if __name__ == "__main__": main()