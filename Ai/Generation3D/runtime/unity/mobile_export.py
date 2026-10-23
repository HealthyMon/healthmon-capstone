"""Make a separate mobile GLB; preserve full-resolution source and skin groups."""
import argparse
import json
from pathlib import Path
import sys
import bpy

parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--triangles', type=int, default=60000)
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(Path(args.input).resolve()))
meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
before = sum(len(obj.data.polygons) for obj in meshes)
for obj in meshes:
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    ratio = min(1.0, args.triangles / max(before, 1))
    if ratio < 1:
        modifier = obj.modifiers.new('MobileDecimation', 'DECIMATE')
        modifier.ratio = ratio
        modifier.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    obj.select_set(False)
for image in bpy.data.images:
    if image.type == 'IMAGE' and max(image.size) > 1024:
        factor = 1024 / max(image.size)
        image.scale(max(1, int(image.size[0] * factor)), max(1, int(image.size[1] * factor)))
output = Path(args.output).resolve()
output.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.export_scene.gltf(filepath=str(output), export_format='GLB', export_animations=False,
    export_skins=True, export_all_influences=False, export_texcoords=True, export_normals=True)
report = dict(source=str(Path(args.input).resolve()), output=str(output), source_polygons=before,
    exported_polygons=sum(len(obj.data.polygons) for obj in meshes), triangle_target=args.triangles,
    max_texture_size=1024, original_preserved=True, validation_required=True)
output.with_suffix('.optimization.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
