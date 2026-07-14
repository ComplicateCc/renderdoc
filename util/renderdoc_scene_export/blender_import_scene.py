#!/usr/bin/env python3
"""Build Blender meshes and binary FBX files from a scene export manifest."""

import argparse
import array
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def arguments():
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--flip-v", action="store_true")
    parser.add_argument("--per-draw-fbx", action="store_true")
    return parser.parse_args(values)


def read_array(path, code):
    values = array.array(code)
    with Path(path).open("rb") as handle:
        values.fromfile(handle, Path(path).stat().st_size // values.itemsize)
    return values


def capture_to_blender(vector, scale=1.0):
    return (vector[0] * scale, -vector[2] * scale, vector[1] * scale)


def material_color(key):
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return tuple(0.25 + digest[index] / 255.0 * 0.55 for index in range(3)) + (1.0,)


def create_material(root, draw, cache):
    description = draw["material"]
    key = description["key"]
    if key in cache:
        return cache[key]
    material = bpy.data.materials.new("Material_%s" % hashlib.sha1(key.encode("utf-8")).hexdigest()[:12])
    material.use_nodes = True
    material.diffuse_color = material_color(key)
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Base Color"].default_value = material.diffuse_color
    shader.inputs["Roughness"].default_value = 0.65
    material.node_tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    texture_file = description.get("diffuseTexture")
    if texture_file:
        image_path = root / texture_file
        if image_path.is_file():
            image = bpy.data.images.load(str(image_path), check_existing=True)
            texture = nodes.new("ShaderNodeTexImage")
            texture.image = image
            material.node_tree.links.new(texture.outputs["Color"], shader.inputs["Base Color"])
            material.node_tree.links.new(texture.outputs["Alpha"], shader.inputs["Alpha"])
            material["renderdoc_diffuse_resource"] = description.get("diffuseResourceId", "")
            material["renderdoc_diffuse_file"] = texture_file
    if description.get("alphaTest"):
        material.blend_method = "CLIP"
        material.surface_render_method = "DITHERED"
        material.alpha_threshold = 0.5
        material.use_transparency_overlap = False
        material["renderdoc_alpha_test"] = True
    cache[key] = material
    return material


def transform_normal(normal):
    converted = Vector((normal[0], -normal[2], normal[1]))
    if converted.length_squared > 1.0e-20:
        converted.normalize()
    return tuple(converted)


def create_mesh(root, draw, scale, flip_v, materials):
    files = draw["files"]
    positions = read_array(root / files["positions"]["file"], "f")
    triangle_indices = read_array(root / files["triangles"]["file"], "I")
    vertices = [capture_to_blender(positions[index:index + 3], scale) for index in range(0, len(positions), 3)]
    faces = [tuple(triangle_indices[index:index + 3]) for index in range(0, len(triangle_indices), 3)]
    name = "EID_%06d" % draw["eventId"]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    if "uv0" in files:
        uvs = read_array(root / files["uv0"]["file"], "f")
        layer = mesh.uv_layers.new(name="UVMap")
        for loop in mesh.loops:
            source = loop.vertex_index * 2
            layer.data[loop.index].uv = (uvs[source], 1.0 - uvs[source + 1] if flip_v else uvs[source + 1])
    if "normals" in files:
        normals = read_array(root / files["normals"]["file"], "f")
        converted = [transform_normal(normals[index:index + 3]) for index in range(0, len(normals), 3)]
        mesh.normals_split_custom_set_from_vertices(converted)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    mesh.materials.append(create_material(root, draw, materials))
    obj["renderdoc_event_id"] = draw["eventId"]
    obj["renderdoc_action_id"] = draw["actionId"]
    obj["renderdoc_capture_units"] = True
    obj["renderdoc_camera_relative"] = True
    obj["renderdoc_vertex_count"] = draw["vertexCount"]
    obj["renderdoc_triangle_count"] = draw["triangleCount"]
    return obj


def export_fbx(path, selection):
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in selection:
        obj.select_set(True)
    if selection:
        bpy.context.view_layer.objects.active = selection[0]
    bpy.ops.export_scene.fbx(
        filepath=str(path),
        use_selection=True,
        object_types={"MESH", "CAMERA"},
        use_mesh_modifiers=False,
        add_leaf_bones=False,
        bake_anim=False,
        path_mode="RELATIVE",
        embed_textures=False,
        axis_forward="-Z",
        axis_up="Y",
    )


def main():
    args = arguments()
    manifest_path = Path(args.manifest).resolve()
    root = manifest_path.parent
    output = Path(args.output).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    materials = {}
    objects = []
    for index, draw in enumerate(manifest["draws"]):
        print("[%d/%d] Building EID %d" % (index + 1, len(manifest["draws"]), draw["eventId"]), flush=True)
        objects.append(create_mesh(root, draw, args.scale, args.flip_v, materials))
    bpy.ops.object.camera_add(location=(0.0, 0.0, 0.0))
    camera = bpy.context.active_object
    camera.name = "RenderDoc_Capture_Camera_Origin"
    camera.data.name = camera.name
    forward = capture_to_blender(manifest["camera"]["forward"])
    camera.rotation_euler = Vector(forward).to_track_quat("-Z", "Y").to_euler()
    camera.data.clip_start = 0.01
    camera.data.clip_end = 1000000.0
    camera["capture_origin"] = manifest["camera"]["origin"]
    bpy.context.scene.camera = camera
    output.mkdir(parents=True, exist_ok=True)
    combined_fbx = output / "scene.fbx"
    blend_path = output / "scene.blend"
    export_fbx(combined_fbx, objects + [camera])
    per_draw = []
    if args.per_draw_fbx:
        for index, obj in enumerate(objects):
            path = output / "fbx" / (obj.name.lower() + ".fbx")
            print("[%d/%d] Exporting %s" % (index + 1, len(objects), path.name), flush=True)
            export_fbx(path, [obj])
            per_draw.append(str(path.relative_to(output)).replace("\\", "/"))
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    result = {
        "blend": str(blend_path),
        "combinedFbx": str(combined_fbx),
        "perDrawFbx": per_draw,
        "objects": len(objects),
        "vertices": sum(len(obj.data.vertices) for obj in objects),
        "triangles": sum(len(obj.data.polygons) for obj in objects),
        "materials": len(materials),
        "images": len(bpy.data.images),
        "cameraAtOrigin": list(camera.location),
    }
    (output / "blender_export.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
