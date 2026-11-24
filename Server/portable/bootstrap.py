"""Portable installation and lifecycle. Installation never loads a GPU model."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / '.runtime/portable'
MODELS = ROOT / '.runtime/models'
LOCK = json.loads(Path(__file__).with_name('model-lock.json').read_text(encoding='utf-8'))


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b''):
            value.update(block)
    return value.hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def dialogue_manifest():
    model = LOCK['dialogue']
    return dict(model_version='v1', status='ready', format='peft_lora',
                base_model_id=model['repo_id'], base_revision=model['revision'],
                base_config_sha256=model['config_sha256'], artifact_checksums=model['adapter_checksums'])


def bundle_files():
    from Ai.Generation3D.runtime.evolution_2511.assets import CONFIG, read
    files = {f'evolution/{item["path"]}': item['sha256']
             for item in read(CONFIG / 'upload_manifest.json')['files']}
    files.update({'dialogue/' + name: digest for name, digest in LOCK['dialogue']['adapter_checksums'].items()})
    return files


def export_bundle(destination, evolution, dialogue):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    sources = {}
    for name, digest in bundle_files().items():
        group, relative = name.split('/', 1)
        source = Path(evolution if group == 'evolution' else dialogue) / relative
        if sha(source) != digest:
            raise ValueError('Private adapter differs from the pinned model: ' + name)
        sources[name] = source
    # No personal configuration, credentials, game data, or arbitrary archive members.
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for name, path in sources.items():
            archive.write(path, name)
    print('Private adapter bundle prepared:', destination)


def import_bundle(source):
    destinations = {'evolution': MODELS / 'evolution-2511/adapter', 'dialogue': MODELS / 'dialogue-adapter'}
    required = bundle_files()
    with zipfile.ZipFile(source) as archive:
        if len(archive.namelist()) != len(required) or set(archive.namelist()) != set(required):
            raise ValueError('Unexpected or incomplete adapter bundle contents')
        for name, digest in required.items():
            group, relative = name.split('/', 1)
            target = destinations[group] / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if sha(target) != digest:
                    raise ValueError('Different existing model preserved: ' + name)
                continue
            temporary = target.with_suffix(target.suffix + '.partial')
            with archive.open(name) as source_stream, temporary.open('wb') as destination:
                shutil.copyfileobj(source_stream, destination, 8 * 1024**2)
            if sha(temporary) != digest:
                raise ValueError('Adapter bundle checksum mismatch: ' + name)
            temporary.replace(target)
    write(destinations['dialogue'] / 'healthmon-model.json', dialogue_manifest())


def download_public(name):
    from huggingface_hub import snapshot_download
    spec = LOCK[name]
    directory = MODELS / name
    snapshot_download(spec['repo_id'], revision=spec['revision'], local_dir=directory,
                      allow_patterns=['*.safetensors', '*.json', '*.txt', '*.model', '*.jinja'], max_workers=2)
    # Bind full hashes to the immutable Hub download metadata; no model import.
    for path in directory.rglob('*'):
        if not path.is_file() or '.cache' in path.parts:
            continue
        metadata = directory / '.cache/huggingface/download' / (path.relative_to(directory).as_posix() + '.metadata')
        lines = metadata.read_text(encoding='utf-8').splitlines()
        if len(lines) < 2 or lines[0] != spec['revision']:
            raise ValueError('Unpinned downloaded model: ' + str(path))
        if len(lines[1]) == 64:
            actual = sha(path)
        elif len(lines[1]) == 40:
            digest = hashlib.sha1(f'blob {path.stat().st_size}\0'.encode())
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(8 * 1024**2), b''):
                    digest.update(block)
            actual = digest.hexdigest()
        else:
            raise ValueError('Unknown Hub file identity')
        if actual != lines[1]:
            raise ValueError('Downloaded model checksum mismatch: ' + str(path))
    if name == 'dialogue' and sha(directory / 'config.json') != spec['config_sha256']:
        raise ValueError('Dialogue base config does not match its adapter')


def install_assets(bundle):
    from Server.portable.downloads import lfs_assets
    if bundle is None:
        raise ValueError('Full AI setup requires an existing private adapter bundle. Menu 5 installs the team test environment without it.')
    lfs_assets(ROOT, "food")
    lfs_assets(ROOT, "client")
    from Ai.Generation3D.runtime.evolution_2511.assets import download_base, verify
    import_bundle(bundle)
    for name in ('dialogue', 'embedding'):
        download_public(name)
    subprocess.run([sys.executable, str(ROOT / 'Ai/Generation3D/migration/tools/models.py'),
                    'download', '--runtime-root', str(MODELS / 'generation3d')], check=True)
    download_base(MODELS / 'evolution-2511')
    verify(MODELS / 'evolution-2511')
    # Nested writable kernel-cache mounts require pre-existing mount points.
    for name in ('flex_gemm', 'torch_extensions', 'triton'):
        (MODELS / 'generation3d/models/trellis' / name).mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(ROOT / 'Ai/Pose/mac-exercise-counter/scripts/download_models.py')], check=True)
    vision = ROOT / 'Ai/Vision'
    for name, spec in json.loads((vision / 'weights-manifest.json').read_text()).items():
        if (vision / name).stat().st_size != spec['size_bytes'] or sha(vision / name) != spec['sha256']:
            raise ValueError('Run git lfs pull for the food models: ' + name)
    write(STATE / 'assets-ready.json', {'integrity': 'PASS', 'inference_verified': False})


def prepare_connection():
    from dotenv import dotenv_values
    from Server.scripts.manage import initialize
    initialize(test=True, port=18092)
    path = ROOT / '.env'
    current = dotenv_values(path)
    if current.get('APP_ENV') != 'test':
        raise ValueError('Only the local test environment is supported')
    token_path = STATE / 'server-token'
    token = current.get('AI_SERVER_TOKEN') or (token_path.read_text().strip() if token_path.exists() else secrets.token_urlsafe(36))
    STATE.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token, encoding='utf-8')
    if os.name != 'nt':
        token_path.chmod(0o600)
    updates = dict(AI_MODE='remote', AI_BASE_URL='http://host.docker.internal:18090',
                   AI_SERVER_TOKEN=token, AI_TIMEOUT_SECONDS='180', ALLOW_HTTP_AI='true')
    lines = []
    original = path.read_text(encoding='utf-8-sig')
    for line in original.splitlines():
        key = line.partition('=')[0]
        lines.append(key + '=' + updates.pop(key) if key in updates else line)
    lines.extend(key + '=' + value for key, value in updates.items())
    updated = '\n'.join(lines) + '\n'
    if updated != original:
        backup = STATE / ('before-setup-' + str(time.time_ns()) + '.env')
        backup.write_text(original, encoding='utf-8')
        path.write_text(updated, encoding='utf-8')
    print('Local credentials prepared; no services or models started.')


def configure_container():
    token = (STATE / 'server-token').read_text().strip()
    if not token:
        raise ValueError('Portable installation must provision a server token first')
    config = STATE / 'config'
    llm = dict(environment='test', server_token=token, warmup=True,
               model_path='/models/dialogue', embedding_path='/models/embedding',
               adapter_path='/models/dialogue-adapter', expected_model_mode='lora', expected_model_version='v1',
               quality_refinement=True, prompt_projection=True, compact_voice=True,
               full_personality_facts=True, structured_dialogue=True, merge_adapter_for_inference=True,
               trained_style_profile=True, bounded_candidate_search=False, base_seed=20261022,
               max_real_generations=3, max_quality_candidates=2)
    write(config / 'llm/private.json', llm)
    write(config / 'vision/private.json', dict(environment='test', server_token=token, vision_enabled=True,
          vision_python='/opt/healthmon-envs/vision/bin/python', vision_assets='/app/Ai/Vision', timeout_seconds=300))
    write(config / 'evolution.json', dict(work_root=str(STATE / 'evolution'),
          model_root='/models/generation3d', vendor_root='/opt/healthmon/Ai/Generation3D/vendor',
          image_model_root='/models/evolution2511', execution_mode='process'))
    write(config / 'services.json', dict(python='/opt/healthmon-envs/control/bin/python',
          llm_python='/opt/healthmon-envs/dialogue/bin/python', pose_python='/opt/healthmon-envs/pose/bin/python',
          llm_config=str(config / 'llm/private.json'), vision_config=str(config / 'vision/private.json'), evolution_config=str(config / 'evolution.json')))
    return config / 'services.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['assets', 'client-assets', 'connection', 'serve', 'stop', 'health', 'export'])
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--evolution-adapter', type=Path)
    parser.add_argument('--dialogue-adapter', type=Path)
    args = parser.parse_args()
    if args.action == 'export':
        if not all((args.bundle, args.evolution_adapter, args.dialogue_adapter)):
            parser.error('export requires --bundle, --evolution-adapter, --dialogue-adapter')
        export_bundle(args.bundle, args.evolution_adapter, args.dialogue_adapter)
    elif args.action == 'assets':
        install_assets(args.bundle)
    elif args.action == 'client-assets':
        from Server.portable.downloads import lfs_assets
        lfs_assets(ROOT, 'client')
    elif args.action == 'connection':
        prepare_connection()
    elif args.action == 'stop':
        (STATE / 'local-services.stop').touch()
    elif args.action == 'health':
        status = json.loads((STATE / 'local-services-status.json').read_text())
        if time.time() - status['updated_at'] > 30 or status['phase'] not in ('ready', 'generating_3d'):
            raise SystemExit(1)
    else:
        path = configure_container()
        os.environ['HEALTHMON_SERVICE_STATE'] = str(STATE)
        from Server.local_probe.local_services import configuration, supervise
        config = configuration(path, available_only=True)
        config['path'] = path
        supervise(config)


if __name__ == '__main__':
    main()
