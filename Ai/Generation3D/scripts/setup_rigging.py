"""Prepare official RigAnything in an isolated environment and verify on CPU."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = 'd03cdb21dd134fa81df6b0947522469db3f78bd2'
MODEL_REVISION = '30df7c0c390db1d5453c5af12da8d227c5025db6'
MODEL_SHA256 = '84c00971ed5c07f2906495bb4a23891058e7e1ee2afe687ada2011cd082a187a'


def run(argv, **kwargs):
    print('Running:', ' '.join(map(str, argv)), flush=True)
    return subprocess.run(list(map(str, argv)), check=True, **kwargs)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--blender', type=Path)
    p.add_argument('--blender-debs', type=Path, help='Extract existing ARM64 Ubuntu Blender and dependency .deb files into project runtime')
    p.add_argument('--skip-download', action='store_true')
    args = p.parse_args()
    venv = ROOT / '.venvs/riganything'
    python = venv / 'bin/python'
    if not python.exists():
        run([sys.executable, '-m', 'venv', '--system-site-packages', venv])
    run([python, '-m', 'pip', 'install', 'easydict==1.13', 'trimesh==4.12.2', 'transformers==4.57.6'])
    repo = ROOT / 'vendor/RigAnything'
    if not (repo / '.git').exists():
        run(['git', 'clone', 'https://github.com/Isabella98Liu/RigAnything.git', repo])
    head = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    if head != SOURCE_COMMIT:
        run(['git', '-C', repo, 'fetch', 'origin', SOURCE_COMMIT])
        run(['git', '-C', repo, 'checkout', '--detach', SOURCE_COMMIT])
    checkpoint_dir = ROOT / 'models/RigAnything'
    checkpoint = checkpoint_dir / 'riganything_ckpt.pt'
    if not checkpoint.exists() and not args.skip_download:
        # Uses the isolated Hub version; no API inference service.
        run([python, '-c', 'from huggingface_hub import snapshot_download; import sys; snapshot_download("Isabellaliu/RigAnything", revision=sys.argv[1], local_dir=sys.argv[2])', MODEL_REVISION, checkpoint_dir])
    if not checkpoint.exists():
        raise FileNotFoundError('Official checkpoint missing: ' + str(checkpoint))
    digest = hashlib.sha256()
    with checkpoint.open('rb') as stream:
        for chunk in iter(lambda: stream.read(16 * 1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != MODEL_SHA256:
        raise RuntimeError('Downloaded checkpoint SHA256 differs from pinned official weights')
    blender = args.blender
    if args.blender_debs:
        bundle = ROOT / 'runtime/blender_arm/root'
        bundle.mkdir(parents=True, exist_ok=True)
        packages = sorted(args.blender_debs.glob('*.deb'))
        if not packages:
            raise FileNotFoundError('No .deb packages found in ' + str(args.blender_debs))
        for package in packages:
            run(['dpkg-deb', '-x', package, bundle])
        blender = bundle / 'usr/bin/blender'
    if not blender:
        candidates = [Path(shutil.which('blender') or '/missing/blender'), ROOT / 'runtime/blender_arm/root/usr/bin/blender',
            Path('/workspace/3d_pipeline_lab/runtime/blender_arm/root/usr/bin/blender')]
        blender = next((path for path in candidates if path.is_file()), None)
    if not blender:
        raise FileNotFoundError('No compatible Blender found. Supply --blender or --blender-debs; x86 binaries cannot run on ARM64.')
    # A launcher exposes the isolated bundle to callers outside this module too.
    wrapper = ROOT / 'scripts/blender'
    raw_blender = blender.resolve()
    if raw_blender == wrapper.resolve():
        existing_path = ROOT / 'configs/rigging_runtime.json'
        existing = json.loads(existing_path.read_text()) if existing_path.exists() else {}
        raw_blender = Path(existing.get('blender_binary', '/workspace/3d_pipeline_lab/runtime/blender_arm/root/usr/bin/blender')).resolve()
        if raw_blender == wrapper.resolve() or not raw_blender.is_file():
            raise ValueError('Provide the real Blender binary rather than the generated launcher')
    bundle = raw_blender.parents[2] if raw_blender.parent.name == 'bin' and raw_blender.parent.parent.name == 'usr' else None
    import shlex
    lines = ['#!/usr/bin/env bash', 'set -euo pipefail']
    if bundle and (bundle / 'usr/share/blender/scripts').exists():
        lines += ['export BLENDER_SYSTEM_SCRIPTS=' + shlex.quote(str(bundle / 'usr/share/blender/scripts')),
                  'export BLENDER_SYSTEM_DATAFILES=' + shlex.quote(str(bundle / 'usr/share/blender/datafiles'))]
        library_path = ':'.join(str(x) for x in [bundle / 'usr/lib/aarch64-linux-gnu', bundle / 'usr/lib', bundle / 'lib/aarch64-linux-gnu'])
        lines.append('export LD_LIBRARY_PATH=' + shlex.quote(library_path) + ':"${LD_LIBRARY_PATH:-}"')
    lines.append('exec ' + shlex.quote(str(raw_blender)) + ' "$@"')
    wrapper.write_text('\n'.join(lines) + '\n')
    wrapper.chmod(0o755)
    blender = wrapper
    config = {'rigging_backend': 'riganything', 'rigging_python': str(python), 'rigging_repo': str(repo),
              'rigging_checkpoint': str(checkpoint), 'blender': str(blender), 'blender_binary': str(raw_blender)}
    config_path = ROOT / 'configs/rigging_runtime.json'
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2) + '\n')
    # Import the project helper without depending on editable package installation.
    sys.path.insert(0, str(ROOT / 'src'))
    from healthmon.rigging_runner import blender_environment, blender_command
    env = blender_environment(blender, python)
    config['blender_environment'] = {key: env[key] for key in ['BLENDER_SYSTEM_SCRIPTS', 'BLENDER_SYSTEM_DATAFILES', 'LD_LIBRARY_PATH'] if key in env}
    config_path.write_text(json.dumps(config, indent=2) + '\n')
    out = ROOT / 'logs/rigging_preflight'
    out.mkdir(parents=True, exist_ok=True)
    settings = {'repo': str(repo), 'checkpoint': str(checkpoint), 'checkpoint_sha256': MODEL_SHA256,
                'output_dir': str(out), 'seed': 42}
    settings_path = out / 'settings.json'
    settings_path.write_text(json.dumps(settings, indent=2) + '\n')
    with (out / 'preflight.log').open('w') as log:
        run(blender_command(blender, ROOT / 'src/healthmon/riganything_blender_entry.py', ['doctor', '--settings', settings_path]),
            env=env, stdout=log, stderr=subprocess.STDOUT)
    # Preserve dependency metadata from the isolated interpreter.
    metadata_code = 'import json; from importlib.metadata import metadata; names=' + repr(['easydict', 'trimesh', 'transformers', 'torch', 'einops', 'numpy', 'scipy', 'PyYAML', 'rich', 'huggingface-hub']) + '; print(json.dumps({name:dict(metadata(name).items()) for name in names}))'
    (out / 'dependency_licenses.json').write_text(subprocess.check_output([str(python), '-c', metadata_code], text=True))
    identity = {'repository': 'Isabellaliu/RigAnything', 'revision': MODEL_REVISION, 'path': str(checkpoint), 'bytes': checkpoint.stat().st_size, 'sha256': MODEL_SHA256, 'weights_only_load': True, 'source_license': 'Adobe Research License, noncommercial research and teaching only'}
    (checkpoint_dir / 'checkpoint_identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    print('CPU preflight passed:', out / 'riganything_preflight.json')
    print('Runtime fragment:', config_path)
    print('GPU inference was not executed.')


if __name__ == '__main__':
    main()
