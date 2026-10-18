"""Real headless Blender operations; invoke with Blender -b -P this_file -- ... ."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import struct
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def import_asset(path, reset=True):
    if reset:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    before = set(bpy.data.objects)
    path = Path(path).resolve()
    if path.suffix.lower() == '.glb':
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif path.suffix.lower() == '.fbx':
        bpy.ops.import_scene.fbx(filepath=str(path), use_image_search=True)
    else:
        raise ValueError('Only GLB and FBX inputs are supported')
    return [o for o in bpy.data.objects if o not in before]


def character_meshes(objects=None):
    objects = list(objects) if objects is not None else list(bpy.context.scene.objects)
    shapes = {b.custom_shape for o in objects if o.type == 'ARMATURE' for b in o.pose.bones if b.custom_shape}
    for shape in shapes:
        shape.hide_render = True
    return [o for o in objects if o.type == 'MESH' and o not in shapes and not o.hide_render and len(o.data.vertices)]


def world_positions(objects, evaluated=False):
    result = []
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for original in objects:
        obj = original.evaluated_get(depsgraph) if evaluated else original
        mesh = obj.to_mesh() if evaluated else obj.data
        xyz = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
        mesh.vertices.foreach_get('co', xyz)
        matrix = np.asarray(obj.matrix_world)
        result.append(xyz.reshape(-1, 3) @ matrix[:3, :3].T + matrix[:3, 3])
        if evaluated:
            obj.to_mesh_clear()
    return np.concatenate(result) if result else np.empty((0, 3))


def setup_render(meshes, size=768, front_azimuth=0):
    points = world_positions(meshes, evaluated=True)
    if not len(points) or not np.isfinite(points).all():
        raise ValueError('Cannot frame empty/nonfinite geometry')
    low, high = points.min(0), points.max(0)
    center = Vector(((low + high) / 2).tolist())
    extent = float((high - low).max())
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 16
    scene.cycles.use_denoising = False
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = 8
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'Medium High Contrast' if 'Medium High Contrast' in [x.identifier for x in scene.view_settings.bl_rna.properties['look'].enum_items] else 'None'
    scene.world = scene.world or bpy.data.worlds.new('Neutral World')
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value = (.8, .8, .8, 1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value = .6
    data = bpy.data.cameras.new('HEALTHMON Camera')
    camera = bpy.data.objects.new('HEALTHMON Camera', data)
    scene.collection.objects.link(camera)
    data.type = 'ORTHO'
    data.ortho_scale = extent * 1.48
    data.clip_start = max(extent * .001, .00001)
    data.clip_end = max(extent * 100, 100)
    scene.camera = camera
    for name, offset, power in [('Key', (-3, -4, 5), 850), ('Fill', (4, -2, 3), 500), ('Rim', (0, 4, 4), 700)]:
        light_data = bpy.data.lights.new(name, 'AREA')
        light_data.energy = power * extent * extent
        light_data.size = extent * 3
        light = bpy.data.objects.new(name, light_data)
        scene.collection.objects.link(light)
        light.location = center + Vector(offset) * extent
        light.rotation_euler = (center - light.location).to_track_quat('-Z', 'Y').to_euler()
    return center, extent, camera


def aim_camera(center, extent, camera, degrees):
    azimuth = math.radians(degrees)
    camera.location = center + Vector((math.sin(azimuth) * 3.5, -math.cos(azimuth) * 3.5, .45)) * extent
    camera.rotation_euler = (center - camera.location).to_track_quat('-Z', 'Y').to_euler()


def render_to(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(path.resolve())
    bpy.ops.render.render(write_still=True)


def render_views(args):
    import_asset(args.input)
    meshes = character_meshes()
    center, extent, camera = setup_render(meshes, args.size)
    out = Path(args.out_dir)
    views = {'front': 0, 'three_quarter': 45, 'side': 90, 'back': 180}
    for name, angle in views.items():
        aim_camera(center, extent, camera, angle + args.front_azimuth)
        render_to(out / (name + '.png'))
    write_json(out / 'render_metadata.json', {'source': str(Path(args.input).resolve()), 'blender_version': bpy.app.version_string,
        'engine': 'CYCLES', 'device': 'CPU', 'size': args.size, 'front_azimuth_degrees': args.front_azimuth,
        'world_up': '+Z in Blender; glTF +Y converted by importer', 'front_direction': 'Camera looks from Blender -Y by default; visual review required',
        'bounds': [world_positions(meshes).min(0).tolist(), world_positions(meshes).max(0).tolist()], 'views': views})


def glb_structure(path):
    if Path(path).suffix.lower() != '.glb':
        return None
    with open(path, 'rb') as stream:
        header = stream.read(12)
        magic, version, length = struct.unpack('<4sII', header)
        if magic != b'glTF' or version != 2 or length != Path(path).stat().st_size:
            raise ValueError('Invalid GLB header')
        chunk_length, chunk_type = struct.unpack('<I4s', stream.read(8))
        if chunk_type != b'JSON':
            raise ValueError('GLB JSON chunk missing')
        document = json.loads(stream.read(chunk_length))
    primitives = [p for m in document.get('meshes', []) for p in m.get('primitives', [])]
    return {'skins': len(document.get('skins', [])), 'joints': [len(s.get('joints', [])) for s in document.get('skins', [])],
        'primitives': len(primitives), 'skinned_primitives': sum('JOINTS_0' in p.get('attributes', {}) and 'WEIGHTS_0' in p.get('attributes', {}) for p in primitives),
        'materials': len(document.get('materials', [])), 'textures': len(document.get('textures', [])), 'images': len(document.get('images', [])),
        'images_embedded': all('bufferView' in x or x.get('uri', '').startswith('data:') for x in document.get('images', []))}


def material_info(meshes):
    materials = {m for obj in meshes for m in obj.data.materials if m}
    textures = {n.image for m in materials if m.use_nodes for n in m.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image}
    return {'materials': sorted(m.name for m in materials),
        'textures': [{'name': image.name, 'width': int(image.size[0]), 'height': int(image.size[1]), 'packed': bool(image.packed_file)} for image in textures],
        'meshes': [{'name': obj.name, 'vertices': len(obj.data.vertices), 'polygons': len(obj.data.polygons), 'uv_layers': list(obj.data.uv_layers.keys()),
                    'material_slots': len(obj.data.materials)} for obj in meshes]}


def inspect_rig(meshes, arms):
    errors = []
    if len(arms) != 1:
        return {'errors': ['Expected exactly one armature'], 'valid': False}
    arm = arms[0]
    names = set(arm.data.bones.keys())
    influence = dict.fromkeys(names, 0.0)
    invalid = 0
    blended = 0
    bound = 0
    roots = [b.name for b in arm.data.bones if b.parent is None]
    if len(roots) != 1:
        errors.append('Expected a connected hierarchy with exactly one root joint')
    if len(names) < 2:
        errors.append('Armature has fewer than two bones')
    for bone in arm.data.bones:
        seen = {bone.name}
        parent = bone.parent
        while parent:
            if parent.name in seen:
                errors.append('Cyclic joint hierarchy')
                break
            seen.add(parent.name)
            parent = parent.parent
        if not np.isfinite(np.asarray(bone.matrix_local)).all():
            errors.append('Nonfinite bone matrix')
    for obj in meshes:
        attached = any(m.type == 'ARMATURE' and m.object == arm for m in obj.modifiers)
        bound += int(attached)
        if not attached:
            errors.append('Mesh is not bound to armature: ' + obj.name)
        groups = {g.index: g.name for g in obj.vertex_groups}
        for vertex in obj.data.vertices:
            weights = [(groups.get(g.group), g.weight) for g in vertex.groups if groups.get(g.group) in names and g.weight > 0]
            total = sum(w for _, w in weights)
            if not weights or not all(math.isfinite(w) and 0 <= w <= 1.001 for _, w in weights) or abs(total - 1) > .015:
                invalid += 1
            if sum(w > .01 for _, w in weights) > 1:
                blended += 1
            for name, weight in weights:
                influence[name] += weight
    active = sum(w > .01 for w in influence.values())
    if invalid:
        errors.append(f'{invalid} vertices have missing or invalid skinning weights')
    if active < 2:
        errors.append('Skinning weights affect fewer than two joints')
    return {'valid': not errors, 'errors': errors, 'bone_count': len(names), 'root_joints': roots, 'bound_meshes': bound,
        'invalid_weight_vertices': invalid, 'blended_vertices': blended, 'active_joint_count': active,
        'joints': [{'name': b.name, 'parent': b.parent.name if b.parent else None, 'head': list(b.head_local),
                    'tail': list(b.tail_local), 'total_skin_weight': influence[b.name]} for b in arm.data.bones]}


def pose_test(meshes, arm, rig_report):
    rest = world_positions(meshes, evaluated=True)
    extent = float(np.ptp(rest, axis=0).max())
    tests = []
    # Choose nonroot joints with measurable direct influence, and use three local axes.
    candidates = sorted(rig_report['joints'], key=lambda j: j['total_skin_weight'], reverse=True)
    for joint in candidates:
        bone = arm.pose.bones[joint['name']]
        if bone.parent is None or joint['total_skin_weight'] < .1:
            continue
        original, mode = bone.matrix_basis.copy(), bone.rotation_mode
        for axis in range(3):
            bone.rotation_mode = 'XYZ'
            bone.rotation_euler = (0, 0, 0)
            bone.rotation_euler[axis] = math.radians(15)
            posed = world_positions(meshes, evaluated=True)
            movement = np.linalg.norm(posed - rest, axis=1)
            # All nonzero bone/descendant weights define mathematical deformation support.
            # A 1% cutoff incorrectly classified small valid blended influences as leakage.
            region_names = {bone.name} | {b.name for b in bone.children_recursive}
            region = []
            for obj in meshes:
                groups = {g.index: g.name for g in obj.vertex_groups}
                region.extend(sum(g.weight for g in v.groups if groups.get(g.group) in region_names) > 1e-8 for v in obj.data.vertices)
            region = np.asarray(region)
            moved = movement > max(extent * 1e-6, 1e-9)
            tests.append({'bone': bone.name, 'local_axis': axis, 'rotation_degrees': 15,
                'max_displacement': float(movement.max()), 'mean_displacement': float(movement.mean()),
                'moved_vertices': int(moved.sum()), 'vertices_total': len(rest), 'weighted_region_vertices': int(region.sum()),
                'moved_outside_weighted_region': int(np.logical_and(moved, ~region).sum())})
            bone.matrix_basis, bone.rotation_mode = original, mode
            bpy.context.view_layer.update()
        if len(tests) >= 12:
            break
    local = [t for t in tests if 0 < t['moved_vertices'] < len(rest) * .9 and t['moved_outside_weighted_region'] <= max(2, len(rest) * .001)]
    best = max(local, key=lambda t: t['max_displacement']) if local else None
    valid = bool(best and best['max_displacement'] > extent * 1e-5)
    return {'valid': valid, 'engine': 'Blender evaluated dependency graph with imported Armature modifier',
            'tests': tests, 'best': best, 'anatomical_review_required': True,
            'limitation': 'Numerical local deformation validates binding; it does not certify anatomical rig quality.'}


def skeleton_visualization(arm, extent):
    created = []
    material = bpy.data.materials.new('Skeleton Preview Cyan')
    material.diffuse_color = (.02, .7, 1, 1)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (.02, .7, 1, 1)
    for bone in arm.data.bones:
        head = arm.matrix_world @ bone.head_local
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=6, radius=extent * .011, location=head)
        obj = bpy.context.object
        obj.data.materials.append(material)
        created.append(obj)
        # RigAnything predicts joint heads and parents; exporter leaf tails are
        # display stubs. Show each actual hierarchy edge, including siblings.
        parent_head = arm.matrix_world @ bone.parent.head_local if bone.parent else head
        delta = head - parent_head
        if bone.parent and delta.length > extent * 1e-5:
            bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=extent * .006, depth=delta.length, location=(parent_head + head) / 2)
            obj = bpy.context.object
            obj.rotation_euler = delta.to_track_quat('Z', 'Y').to_euler()
            obj.data.materials.append(material)
            created.append(obj)
    return created


def validate(args):
    import_asset(args.input)
    meshes = character_meshes()
    arms = [o for o in bpy.context.scene.objects if o.type == 'ARMATURE']
    points = world_positions(meshes)
    errors = []
    if not len(points) or not meshes or not sum(len(o.data.polygons) for o in meshes):
        errors.append('Empty mesh geometry')
    elif not np.isfinite(points).all() or float(np.ptp(points, axis=0).max()) < 1e-7:
        errors.append('Nonfinite or degenerate mesh bounds')
    materials = material_info(meshes)
    if not materials['materials']:
        errors.append('No materials')
    if not args.allow_untextured and (not materials['textures'] or not all(o.data.uv_layers for o in meshes)):
        errors.append('Missing UV coordinates or image textures')
    raw = glb_structure(args.input)
    if raw and not raw['images_embedded']:
        errors.append('GLB image textures are externally referenced rather than embedded')
    report = {'source': str(Path(args.input).resolve()), 'actual_file_reopened': True, 'blender_version': bpy.app.version_string,
        'geometry': {'vertices': len(points), 'bounds': [points.min(0).tolist(), points.max(0).tolist()] if len(points) else None},
        **materials, 'glb_structure': raw, 'errors': errors}
    if args.require_rig:
        rig = inspect_rig(meshes, arms)
        report['rig'] = rig
        errors.extend(rig['errors'])
        if raw and (not raw['skins'] or raw['skinned_primitives'] != raw['primitives']):
            errors.append('GLB lacks skin/JOINTS_0/WEIGHTS_0 on a mesh primitive')
        if rig['valid']:
            report['pose_test'] = pose_test(meshes, arms[0], rig)
            if not report['pose_test']['valid']:
                errors.append('No verified local mesh deformation from joint rotation')
    if args.preview_dir and meshes:
        out = Path(args.preview_dir)
        center, extent, camera = setup_render(meshes, args.size)
        aim_camera(center, extent, camera, args.front_azimuth + 35)
        render_to(out / 'neutral.png')
        if args.require_rig and report.get('pose_test', {}).get('best'):
            best = report['pose_test']['best']
            bone = arms[0].pose.bones[best['bone']]
            original, mode = bone.matrix_basis.copy(), bone.rotation_mode
            bone.rotation_mode = 'XYZ'
            bone.rotation_euler[best['local_axis']] = math.radians(best['rotation_degrees'])
            render_to(out / 'pose_test.png')
            bpy.ops.wm.save_as_mainfile(filepath=str((out / 'pose_test.blend').resolve()))
            bone.matrix_basis, bone.rotation_mode = original, mode
            skeleton_visualization(arms[0], extent)
            # A separate skeleton-only view makes every predicted joint visible.
            for obj in meshes:
                obj.hide_render = True
            render_to(out / 'skeleton_preview.png')
    report['technical_valid'] = not errors
    report['status'] = 'PASS' if not errors else 'FAIL'
    write_json(args.report, report)
    print('HEALTHMON_VALIDATION', json.dumps({'technical_valid': report['technical_valid'], 'errors': errors}))
    if errors:
        raise RuntimeError('Asset validation failed: ' + '; '.join(errors))


def prepare_rig(args):
    import_asset(args.input)
    meshes = character_meshes()
    total = sum(len(o.data.polygons) for o in meshes)
    ratio = min(1.0, args.faces / max(total, 1))
    for obj in meshes:
        if ratio < 1:
            bpy.context.view_layer.objects.active = obj
            modifier = obj.modifiers.new('Rigging Proxy Decimate', 'DECIMATE')
            modifier.ratio = ratio
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        bpy.context.view_layer.objects.active = obj
        modifier = obj.modifiers.new('Rigging Proxy Triangulate', 'TRIANGULATE')
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(Path(args.output).resolve()), export_format='GLB', export_materials='EXPORT')
    write_json(Path(args.output).with_suffix('.provenance.json'), {'source': str(Path(args.input).resolve()), 'original_preserved': True,
        'simplified_separate_copy': True, 'original_polygons': total, 'proxy_polygons': sum(len(o.data.polygons) for o in meshes),
        'coordinate_changes': False, 'blender_version': bpy.app.version_string})


def barycentric(point, a, b, c):
    v0, v1, v2 = b - a, c - a, point - a
    d00, d01, d11 = np.dot(v0, v0), np.dot(v0, v1), np.dot(v1, v1)
    denominator = d00 * d11 - d01 * d01
    if abs(denominator) < 1e-20:
        distances = [np.linalg.norm(point - p) for p in [a, b, c]]
        result = np.zeros(3)
        result[int(np.argmin(distances))] = 1
        return result
    u = (d11 * np.dot(v2, v0) - d01 * np.dot(v2, v1)) / denominator
    v = (d00 * np.dot(v2, v1) - d01 * np.dot(v2, v0)) / denominator
    result = np.maximum([1 - u - v, u, v], 0)
    return result / max(result.sum(), 1e-20)


def transfer_rig(args):
    predicted_objects = import_asset(args.predicted_rig)
    predicted = character_meshes(predicted_objects)
    arms = [o for o in predicted_objects if o.type == 'ARMATURE']
    rig = inspect_rig(predicted, arms)
    if not rig['valid']:
        raise ValueError('Predicted neural rig invalid: ' + str(rig['errors']))
    arm = arms[0]
    bone_names = list(arm.data.bones.keys())
    name_index = {name: i for i, name in enumerate(bone_names)}
    positions, weights, triangles = [], [], []
    for obj in predicted:
        offset = len(positions)
        groups = {g.index: g.name for g in obj.vertex_groups}
        for vertex in obj.data.vertices:
            positions.append(tuple(obj.matrix_world @ vertex.co))
            row = np.zeros(len(bone_names), dtype=np.float64)
            for group in vertex.groups:
                if groups.get(group.group) in name_index:
                    row[name_index[groups[group.group]]] += group.weight
            weights.append(row)
        obj.data.calc_loop_triangles()
        triangles.extend(tuple(offset + i for i in face.vertices) for face in obj.data.loop_triangles)
    points = np.asarray(positions)
    weights = np.asarray(weights)
    bvh = BVHTree.FromPolygons([Vector(p) for p in positions], triangles, all_triangles=True)
    original_objects = import_asset(args.source_textured, reset=False)
    originals = character_meshes(original_objects)
    original_materials = material_info(originals)
    target_points = world_positions(originals)
    extent = float(np.ptp(target_points, axis=0).max())
    distances, indices, coefficients = [], [], []
    assignments = []
    for point in target_points:
        location, normal, triangle_id, distance = bvh.find_nearest(Vector(point))
        if location is None:
            raise ValueError('Spatial correspondence query failed')
        triangle = triangles[triangle_id]
        coefficient = barycentric(np.asarray(location), *points[list(triangle)])
        row = coefficient @ weights[list(triangle)]
        # GLB/Unity-compatible four influences, all derived from neural model weights.
        keep = np.argsort(row)[-4:]
        clipped = np.zeros_like(row)
        clipped[keep] = row[keep]
        if not np.isfinite(clipped).all() or clipped.sum() <= 1e-10:
            raise ValueError('Transferred neural weights are empty/nonfinite')
        clipped /= clipped.sum()
        assignments.append(clipped)
        distances.append(distance)
        indices.append(triangle)
        coefficients.append(coefficient)
    distances = np.asarray(distances)
    p95 = float(np.quantile(distances, .95))
    maximum = float(distances.max())
    report = {'source_textured': str(Path(args.source_textured).resolve()), 'predicted_rig': str(Path(args.predicted_rig).resolve()),
        'method': 'Closest triangle surface in common world coordinates; barycentric interpolation of predicted neural skin weights',
        'alignment': 'No guessed rotation/scale/translation; original and proxy must share world coordinates',
        'max_influences': 4, 'vertices': len(target_points), 'source_triangles': len(triangles),
        'distance_p95': p95, 'distance_max': maximum, 'mesh_extent': extent,
        'distance_p95_fraction': p95 / extent, 'distance_max_fraction': maximum / extent,
        'tolerance_fraction_p95': args.max_distance_fraction, 'materials_before': original_materials}
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(report_path.with_suffix('.mapping.npz'), source_triangle_vertex_ids=np.asarray(indices),
        barycentric=np.asarray(coefficients), distance=distances, target_world_positions=target_points)
    if p95 > args.max_distance_fraction * extent or maximum > args.max_distance_fraction * extent * 3:
        report['valid'] = False
        write_json(report_path, report)
        raise ValueError('Rig proxy spatial correspondence exceeds tolerance; refusing to bind unrelated meshes')
    cursor = 0
    for obj in originals:
        for modifier in list(obj.modifiers):
            if modifier.type == 'ARMATURE':
                obj.modifiers.remove(modifier)
        for group in list(obj.vertex_groups):
            obj.vertex_groups.remove(group)
        groups = [obj.vertex_groups.new(name=name) for name in bone_names]
        for vertex in obj.data.vertices:
            for i in np.flatnonzero(assignments[cursor + vertex.index] > 1e-8):
                groups[int(i)].add([vertex.index], float(assignments[cursor + vertex.index][i]), 'REPLACE')
        cursor += len(obj.data.vertices)
        modifier = obj.modifiers.new('Predicted Neural Rig', 'ARMATURE')
        modifier.object = arm
        # Parenting preserves the original world transform.
        matrix = obj.matrix_world.copy()
        obj.parent = arm
        obj.matrix_world = matrix
    for obj in predicted:
        bpy.data.objects.remove(obj, do_unlink=True)
    for obj in original_objects:
        if obj.type == 'ARMATURE':
            bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.object.select_all(action='DESELECT')
    for obj in originals + [arm]:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = arm
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(Path(args.output).resolve()), export_format='GLB', use_selection=True,
        export_materials='EXPORT', export_skins=True, export_animations=False, export_all_influences=False)
    report['valid'] = True
    report['materials_after'] = material_info(originals)
    report['output'] = str(Path(args.output).resolve())
    write_json(report_path, report)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='command', required=True)
    render = sub.add_parser('render')
    render.add_argument('--input', required=True)
    render.add_argument('--out-dir', required=True)
    render.add_argument('--size', type=int, default=768)
    render.add_argument('--front-azimuth', type=float, default=0)
    render.set_defaults(function=render_views)
    check = sub.add_parser('validate')
    check.add_argument('--input', required=True)
    check.add_argument('--report', required=True)
    check.add_argument('--require-rig', action='store_true')
    check.add_argument('--allow-untextured', action='store_true')
    check.add_argument('--preview-dir')
    check.add_argument('--size', type=int, default=512)
    check.add_argument('--front-azimuth', type=float, default=0)
    check.set_defaults(function=validate)
    prepare = sub.add_parser('prepare-rig')
    prepare.add_argument('--input', required=True)
    prepare.add_argument('--output', required=True)
    prepare.add_argument('--faces', type=int, default=8192)
    prepare.set_defaults(function=prepare_rig)
    transfer = sub.add_parser('transfer-rig')
    transfer.add_argument('--source-textured', required=True)
    transfer.add_argument('--predicted-rig', required=True)
    transfer.add_argument('--output', required=True)
    transfer.add_argument('--report', required=True)
    transfer.add_argument('--max-distance-fraction', type=float, default=.05)
    transfer.set_defaults(function=transfer_rig)
    args = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    args.function(args)


if __name__ == '__main__':
    main()
