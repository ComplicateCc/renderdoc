#!/usr/bin/env python3
"""Import the combined FBX in a clean Blender process and validate scene totals."""

import argparse
import json
import math
import sys
from pathlib import Path

import bpy


def arguments():
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--fbx", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args(values)


def main():
    args = arguments()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.fbx(filepath=str(Path(args.fbx).resolve()), use_custom_normals=True)
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    cameras = [obj for obj in bpy.context.scene.objects if obj.type == "CAMERA"]
    vertices = sum(len(obj.data.vertices) for obj in meshes)
    triangles = sum(len(obj.data.polygons) for obj in meshes)
    finite = all(math.isfinite(value) for obj in meshes for corner in obj.bound_box for value in corner)
    expected = manifest["totals"]
    expected_draws = {"EID_%06d" % draw["eventId"]: draw for draw in manifest["draws"]}
    mismatches = []
    for obj in meshes:
        draw = expected_draws.get(obj.name)
        if draw is None:
            mismatches.append({"object": obj.name, "error": "Unexpected object"})
            continue
        if len(obj.data.vertices) != draw["vertexCount"] or len(obj.data.polygons) != draw["triangleCount"]:
            mismatches.append({
                "object": obj.name,
                "expectedVertices": draw["vertexCount"],
                "actualVertices": len(obj.data.vertices),
                "expectedTriangles": draw["triangleCount"],
                "actualTriangles": len(obj.data.polygons),
            })
    checks = {
        "meshObjectCount": len(meshes) == expected["draws"],
        "vertexCount": vertices == expected["vertices"],
        "triangleCount": triangles == expected["triangles"],
        "cameraPresent": len(cameras) == 1,
        "finiteBounds": finite,
        "materialsPresent": all(len(obj.data.materials) > 0 for obj in meshes),
    }
    result = {
        "fbx": str(Path(args.fbx).resolve()),
        "checks": checks,
        "actual": {
            "meshObjects": len(meshes),
            "vertices": vertices,
            "triangles": triangles,
            "cameras": len(cameras),
            "materials": len(bpy.data.materials),
            "images": len(bpy.data.images),
        },
        "expected": expected,
        "drawMismatches": mismatches,
        "verified": all(checks.values()),
    }
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not result["verified"]:
        raise RuntimeError("FBX validation failed")


if __name__ == "__main__":
    main()
