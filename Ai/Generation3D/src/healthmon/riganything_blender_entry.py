"""Execute official RigAnything entry points inside actual Blender, without a bpy wheel."""
import argparse
import ast
import gc
import importlib
import json
import os
from pathlib import Path
import runpy
import site
import sys

for packages in json.loads(os.environ.get('HEALTHMON_RIGGING_SITE_PACKAGES', '[]')):
    site.addsitedir(packages)
# The isolated venv's dependencies take priority over Blender/system packages.
packages = json.loads(os.environ.get('HEALTHMON_RIGGING_SITE_PACKAGES', '[]'))
for package in reversed(packages):
    if package in sys.path:
        sys.path.remove(package)
    sys.path.insert(0, package)
import bpy


def main():
    p = argparse.ArgumentParser()
    p.add_argument('operation', choices=['doctor', 'infer', 'export'])
    p.add_argument('--settings', type=Path, required=True)
    args = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    settings = json.loads(args.settings.read_text())
    repo = Path(settings['repo']).resolve()
    out = Path(settings['output_dir']).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.chdir(repo)
    sys.path.insert(0, str(repo))
    import torch
    import numpy as np
    import yaml
    import trimesh
    from easydict import EasyDict
    from model.ar_rig_diffusion import RigARDiffusion
    checkpoint_path = Path(settings['checkpoint'])
    if args.operation == 'doctor':
        # CPU-only strict checkpoint architecture and full dependency import preflight.
        checkpoint = torch.load(checkpoint_path, map_location='cpu', weights_only=True)
        config = EasyDict(yaml.safe_load((repo / 'config.yaml').read_text()))
        model = RigARDiffusion(config, device='cpu')
        status = model.load_state_dict(checkpoint['model'], strict=True)
        report = {'ready': True, 'cpu_only': True, 'blender': bpy.app.version_string, 'python': sys.version,
            'torch': torch.__version__, 'torch_cuda': torch.version.cuda, 'trimesh': trimesh.__version__,
            'parameters': sum(p.numel() for p in model.parameters()), 'strict_official_checkpoint_load': True,
            'missing_keys': list(status.missing_keys), 'unexpected_keys': list(status.unexpected_keys),
            'checkpoint_sha256': settings.get('checkpoint_sha256'), 'checkpoint_step': checkpoint.get('fwdbwd_pass_step'),
            'real_inference_executed': False}
        (out / 'riganything_preflight.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report), flush=True)
        return
    bpy.ops.wm.read_factory_settings(use_empty=args.operation != 'export')
    if args.operation == 'export':
        # Independently verify the upstream normalization/inverse-axis chain.
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=settings['proxy'])
        with np.load(out / 'proxy.npz', allow_pickle=False) as prediction:
            reconstructed = prediction['pointcloud'] @ np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]])
            actual = []
            for name in prediction['mesh_list']:
                obj = bpy.data.objects[str(name)]
                actual.extend(tuple(obj.matrix_world @ vertex.co) for vertex in obj.data.vertices)
            actual = np.asarray(actual)
        if actual.shape != reconstructed.shape or not np.isfinite(reconstructed).all():
            raise ValueError('Official NPZ pointcloud does not correspond to the imported proxy')
        difference = np.linalg.norm(actual - reconstructed, axis=1)
        extent = float(np.ptp(actual, axis=0).max())
        tolerance = max(extent * 1e-5, 1e-7)
        valid = bool(float(difference.max()) <= tolerance)
        coordinate_report = {'valid': valid, 'vertices': len(actual), 'max_world_error': float(difference.max()),
            'mean_world_error': float(difference.mean()), 'world_tolerance': tolerance,
            'inverse_axis_matrix_row_vectors': [[1, 0, 0], [0, 0, 1], [0, -1, 0]],
            'method': 'Compare official denormalized NPZ pointcloud after inverse axes with independently imported proxy Blender world vertices',
            'original_sha256': settings.get('input_sha256'), 'proxy_sha256': settings.get('proxy_sha256')}
        (out / 'coordinate_validation.json').write_text(json.dumps(coordinate_report, indent=2) + '\n')
        if not valid:
            raise ValueError('Predicted NPZ coordinates differ from proxy Blender world coordinates')
        # Upstream exporter calls object.parent_set before clearing/importing; it
        # needs the active default Cube. It immediately deletes the startup scene.
        bpy.ops.wm.read_factory_settings(use_empty=False)
        sys.argv = ['inference_utils/vis_skel.py', '--data_path', str(out / 'proxy.npz'), '--save_path', str(out), '--mesh_path', settings['proxy']]
        runpy.run_path(str(repo / 'inference_utils/vis_skel.py'), run_name='__main__')
        return
    # The upstream loader catches load errors. Guard it so random weights can never
    # silently become a claimed neural rig on a newer PyTorch release.
    loaded = {'ok': False}
    original_load = RigARDiffusion.load_state_dict
    original_generate = RigARDiffusion.generate_sequence
    def checked_load(self, state_dict, strict=True, **kwargs):
        status = original_load(self, state_dict, strict=True, **kwargs)
        loaded['ok'] = True
        return status
    def checked_generate(self, *positional, **keywords):
        if not loaded['ok']:
            raise RuntimeError('Refusing inference: official checkpoint did not load strictly')
        return original_generate(self, *positional, **keywords)
    RigARDiffusion.load_state_dict = checked_load
    RigARDiffusion.generate_sequence = checked_generate
    np.random.seed(settings['seed'])
    # Modern trimesh uses a separate Generator; seed its documented interface too.
    original_sample = trimesh.sample.sample_surface_even
    def seeded_sample(*positional, **keywords):
        keywords.setdefault('seed', settings['seed'])
        return original_sample(*positional, **keywords)
    trimesh.sample.sample_surface_even = seeded_sample
    source_path = repo / 'inference.py'
    tree = ast.parse(source_path.read_text(), filename=str(source_path))
    class SeedOverride(ast.NodeTransformer):
        count = 0
        def visit_Call(self, node):
            self.generic_visit(node)
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == 'torch' and node.func.attr == 'manual_seed' and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == 777:
                node.args[0] = ast.Constant(value=settings['seed'])
                self.count += 1
            return node
    override = SeedOverride()
    tree = override.visit(tree)
    if override.count != 1:
        raise RuntimeError('Official inference source changed; expected exactly one fixed seed site')
    ast.fix_missing_locations(tree)
    sys.argv = ['inference.py', '--config', str(repo / 'config.yaml'), '--load', str(checkpoint_path),
        '-s', 'inference', 'true', '-s', 'inference_out_dir', str(out), '--mesh_path', settings['proxy']]
    (out / 'adapter_notes.json').write_text(json.dumps({'official_source_unchanged_on_disk': True,
        'entry': str(source_path), 'adapter_changes': ['Seed-only AST override: upstream 777 -> experiment seed',
        'Strict checkpoint load and refusal to generate unless official weights loaded',
        'Documented trimesh surface sampling seed override'], 'seed': settings['seed']}, indent=2) + '\n')
    exec(compile(tree, str(source_path), 'exec'), {'__name__': '__main__', '__file__': str(source_path)})


if __name__ == '__main__':
    main()
