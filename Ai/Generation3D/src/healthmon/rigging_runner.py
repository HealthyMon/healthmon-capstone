"""Run the official RigAnything checkpoint and preserve the original textured mesh."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
OFFICIAL_SHA256 = '84c00971ed5c07f2906495bb4a23891058e7e1ee2afe687ada2011cd082a187a'


def blender_environment(executable, python=None, extra=None):
    env = os.environ.copy()
    binary = Path(executable).resolve()
    # Supports the isolated Ubuntu ARM64 bundle without changing system libraries.
    bundle = binary.parents[2] if binary.parent.name == 'bin' and binary.parent.parent.name == 'usr' else None
    if bundle and (bundle / 'usr/share/blender/scripts').exists():
        libraries = [bundle / 'usr/lib/aarch64-linux-gnu', bundle / 'usr/lib', bundle / 'lib/aarch64-linux-gnu']
        env['LD_LIBRARY_PATH'] = ':'.join(str(p) for p in libraries) + ':' + env.get('LD_LIBRARY_PATH', '')
        env['BLENDER_SYSTEM_SCRIPTS'] = str(bundle / 'usr/share/blender/scripts')
        env['BLENDER_SYSTEM_DATAFILES'] = str(bundle / 'usr/share/blender/datafiles')
    if python:
        result = subprocess.run([str(python), '-c', 'import json,site; print(json.dumps(site.getsitepackages()))'], check=True, text=True, capture_output=True)
        env['HEALTHMON_RIGGING_SITE_PACKAGES'] = json.dumps(json.loads(result.stdout))
    env['PYTHONUNBUFFERED'] = '1'
    env['HEALTHMON_PROJECT'] = str(PROJECT)
    if extra:
        env.update({str(k): str(v) for k, v in extra.items()})
    return env


def command_record(command, cwd, path, env=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    attempt = 1
    if path.exists():
        while path.with_name(path.stem + f'.attempt_{attempt}' + path.suffix).exists():
            attempt += 1
        archive = path.with_name(path.stem + f'.attempt_{attempt}' + path.suffix)
        path.rename(archive)
        previous_command = path.with_suffix('.command.json')
        if previous_command.exists():
            previous_command.rename(archive.with_suffix('.command.json'))
        attempt += 1
    record = {'argv': [str(x) for x in command], 'cwd': str(cwd), 'started_unix': time.time(), 'attempt': attempt}
    path.with_suffix('.command.json').write_text(json.dumps(record, indent=2) + '\n')
    with path.open('w') as log:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, text=True)
    record.update(returncode=result.returncode, duration_seconds=time.time() - record['started_unix'])
    path.with_suffix('.command.json').write_text(json.dumps(record, indent=2) + '\n')
    if result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode}); see {path}')
    return record


def blender_command(executable, script, arguments):
    return [str(executable), '-b', '--python-exit-code', '1', '-P', str(script), '--', *map(str, arguments)]


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(16 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--output-dir', required=True)
    p.add_argument('--config', type=Path, default=PROJECT / 'configs/runtime.json')
    p.add_argument('--backend')
    p.add_argument('--repo', type=Path)
    p.add_argument('--python', type=Path)
    p.add_argument('--checkpoint', type=Path)
    p.add_argument('--blender', type=Path)
    p.add_argument('--faces', type=int, default=8192)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--size', type=int, default=512)
    p.add_argument('--front-azimuth', type=float, default=0)
    args = p.parse_args()
    config = json.loads(args.config.read_text()) if args.config.exists() else {}
    backend = args.backend or config.get('rigging_backend', 'riganything')
    if backend != 'riganything':
        raise ValueError('This inspected adapter implements official RigAnything. UniRig requires its separate officially inspected adapter.')
    repo = Path(args.repo or config.get('rigging_repo', PROJECT / 'vendor/RigAnything')).resolve()
    python = Path(args.python or config.get('rigging_python', PROJECT / '.venvs/riganything/bin/python')).absolute()
    checkpoint = Path(args.checkpoint or config.get('rigging_checkpoint', PROJECT / 'models/RigAnything/riganything_ckpt.pt')).resolve()
    blender = Path(args.blender or config.get('blender', '')).absolute()
    original = Path(args.input).resolve()
    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    for label, path in [('input GLB', original), ('official checkpoint', checkpoint), ('Blender executable', blender), ('Python executable', python), ('official inference.py', repo / 'inference.py')]:
        if not path.is_file():
            raise FileNotFoundError(f'Missing {label}: {path}')
    if original.suffix.lower() != '.glb':
        raise ValueError('Original textured GLB required; conversions that discard materials are not accepted')
    identity = file_hash(checkpoint)
    if identity != OFFICIAL_SHA256:
        raise ValueError('RigAnything checkpoint does not match the pinned public official checkpoint SHA256')
    settings = {'repo': str(repo), 'python': str(python), 'checkpoint': str(checkpoint), 'checkpoint_sha256': identity,
                'input': str(original), 'input_sha256': file_hash(original), 'output_dir': str(out), 'seed': args.seed, 'backend': backend,
                'official_model_repository': 'Isabellaliu/RigAnything', 'official_revision': '30df7c0c390db1d5453c5af12da8d227c5025db6'}
    settings_path = out / 'inference_settings.json'
    settings_path.write_text(json.dumps(settings, indent=2) + '\n')
    tool = PROJECT / 'src/healthmon/blender_tool.py'
    env = blender_environment(blender, python, config.get('blender_environment'))
    command_record(blender_command(blender, tool, ['validate', '--input', original, '--report', out / 'original_validation.json']), PROJECT, out / 'original_validation.log', env)
    proxy = out / 'proxy.glb'
    command_record(blender_command(blender, tool, ['prepare-rig', '--input', original, '--output', proxy, '--faces', args.faces]), PROJECT, out / 'prepare_proxy.log', env)
    settings['proxy'] = str(proxy)
    settings['proxy_sha256'] = file_hash(proxy)
    settings_path.write_text(json.dumps(settings, indent=2) + '\n')
    entry = PROJECT / 'src/healthmon/riganything_blender_entry.py'
    command_record(blender_command(blender, entry, ['infer', '--settings', settings_path]), repo, out / 'riganything_inference.log', env)
    prediction = out / 'proxy.npz'
    if not prediction.is_file():
        raise RuntimeError('Official neural inference did not produce the predicted skeleton and weights NPZ')
    command_record(blender_command(blender, entry, ['export', '--settings', settings_path]), repo, out / 'official_export.log', env)
    predicted_rig = out / 'proxy_rig.glb'
    if not predicted_rig.is_file():
        raise RuntimeError('Official exporter did not produce the predicted rig GLB')
    final = out / 'final_rigged.glb'
    command_record(blender_command(blender, tool, ['transfer-rig', '--source-textured', original, '--predicted-rig', predicted_rig,
        '--output', final, '--report', out / 'spatial_transfer.json']), PROJECT, out / 'spatial_transfer.log', env)
    command_record(blender_command(blender, tool, ['validate', '--input', final, '--report', out / 'validation.json', '--require-rig',
        '--preview-dir', out / 'validation', '--size', args.size, '--front-azimuth', args.front_azimuth]), PROJECT, out / 'validation.log', env)
    for name in ['neutral.png', 'skeleton_preview.png']:
        shutil.copy2(out / 'validation' / name, out / name)
    command_record(blender_command(blender, tool, ['render', '--input', final, '--out-dir', out / 'renders', '--size', args.size,
        '--front-azimuth', args.front_azimuth]), PROJECT, out / 'renders.log', env)
    print(json.dumps({'final_rigged_glb': str(final), 'validation': str(out / 'validation.json'),
        'neutral': str(out / 'validation/neutral.png'), 'pose_test': str(out / 'validation/pose_test.png'),
        'skeleton_preview': str(out / 'validation/skeleton_preview.png')}))


if __name__ == '__main__':
    main()
