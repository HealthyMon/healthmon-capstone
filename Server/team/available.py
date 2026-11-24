"""Offline prerequisite selection for an existing full AI installation.

Missing one capability never prevents starting another. No model imports,
downloads, inference, changes to credentials or model directories occur here.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def require(path, size=None):
    path = Path(path)
    if not path.is_file() or (size is not None and path.stat().st_size != size):
        raise ValueError('missing/incomplete file: ' + path.name)
    if path.stat().st_size <= 1024 and path.read_bytes().startswith(b'version https://git-lfs.github.com/spec/v1'):
        raise ValueError('Git LFS pointer instead of model: ' + path.name)
    return path


def checkpoint(directory):
    directory = Path(directory)
    require(directory / 'config.json')
    indexes = list(directory.glob('*.index.json'))
    if indexes:
        for index in indexes:
            for name in set(read(index)['weight_map'].values()):
                require(directory / name)
    else:
        files = list(directory.glob('*.safetensors')) + list(directory.glob('pytorch_model*.bin'))
        if not files:
            raise ValueError('model weights not installed')
        for path in files:
            require(path)


def configuration(path):
    from Server.local_probe import local_services as svc
    path = svc.resolve(path)
    if not path.is_relative_to(svc.RUNTIME):
        raise ValueError('Configuration must stay in this checkout runtime')
    raw = read(path)
    config = dict(raw, path=path, python=svc.interpreter_path(raw.get('python', sys.executable)),
                  enabled=['router'], skipped={}, available_only=True)
    token = None
    profile_path = svc.ROOT / '.runtime/native-server.json'
    if profile_path.is_file():
        profile = read(profile_path)
        environment = read(svc.resolve(profile['api_env']))
        if environment.get('APP_ENV') != 'test':
            raise ValueError('Existing native API must be a test environment')
        token = environment.get('AI_SERVER_TOKEN')
    # Read an existing token even when its associated model is absent.
    for key in ('llm_config', 'vision_config'):
        if raw.get(key):
            config[key] = svc.resolve(raw[key])
            try:
                private = read(config[key])
                if private.get('environment') == 'test' and private.get('server_token'):
                    token = token or private['server_token']
            except (OSError, ValueError):
                pass
    if not token:
        raise ValueError('No local API-to-AI token is configured; run menu 5')
    config['token'] = token
    router_key = svc.RUNTIME / 'available-router.json'
    router_key.write_text(json.dumps({'server_token': token}), encoding='utf-8')
    config['router_config'] = router_key

    def select(name, check):
        try:
            check()
            config['enabled'].append(name)
        except (OSError, ValueError, KeyError, TypeError) as error:
            config['skipped'][name] = str(error)

    def private(key):
        value = read(config[key])
        if value.get('environment') != 'test' or value.get('server_token') != token:
            raise ValueError('private service credential does not match')
        return value

    def llm():
        config['llm_python'] = require(svc.interpreter_path(raw['llm_python']))
        model = private('llm_config')
        checkpoint(model['model_path'])
        checkpoint(model['embedding_path'])
        if model.get('adapter_path'):
            adapter = Path(model['adapter_path'])
            require(adapter / 'adapter_config.json')
            require(adapter / 'adapter_model.safetensors')
            require(adapter / 'healthmon-model.json')

    def vision():
        model = private('vision_config')
        require(model['vision_python'])
        if model.get('vision_backend') == 'multifood':
            assets = Path(model['vision_assets'])
            for name, spec in read(assets / 'models/manifest.json').items():
                require(assets / 'models' / name, spec['size_bytes'])
            require(assets / 'nutrition.csv')
            require(assets / 'worker.py')
            if model.get('vision_container') is True:
                docker = shutil.which('docker')
                if not docker:
                    raise ValueError('multi-food Docker runtime is not installed; run menu 5')
                try:
                    result = subprocess.run([docker, 'image', 'inspect', 'healthmon-multifood:local'],
                        capture_output=True, timeout=15, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                except subprocess.TimeoutExpired:
                    raise ValueError('multi-food Docker runtime did not respond') from None
                if result.returncode:
                    raise ValueError('multi-food Docker image is unavailable; start Docker or run menu 5')
            return
        source = svc.ROOT / 'Ai/Vision'
        for name, spec in read(source / 'weights-manifest.json').items():
            require(Path(model['vision_assets']) / name, spec['size_bytes'])
        require(Path(model['vision_assets']) / 'nutrition.json')

    def evolution():
        config['evolution_config'] = svc.resolve(raw['evolution_config'])
        value = read(config['evolution_config'])
        for key in ('work_root', 'model_root', 'vendor_root', 'image_model_root'):
            if value.get(key):
                value[key] = svc.resolve(value[key])
        manifest = read(svc.ROOT / 'Ai/Generation3D/migration/model_manifest.json')
        for item in manifest['files']:
            if item.get('required'):
                name = str(Path(item['target']).relative_to('models'))
                require(value['model_root'] / name, item['bytes'])
        if not value['vendor_root'].is_dir():
            raise ValueError('3D execution environment not installed')
        if value.get('image_model_root'):
            from Ai.Generation3D.runtime.evolution_2511.assets import base_files, CONFIG
            for _, spec, target, _ in base_files(value['image_model_root']):
                require(target, spec['bytes'])
            for spec in read(CONFIG / 'upload_manifest.json')['files']:
                require(value['image_model_root'] / 'adapter' / spec['path'], spec['bytes'])
        config['evolution'] = value

    def pose():
        python = raw.get('pose_python') or svc.ROOT / '.runtime/pose-venv/Scripts/python.exe'
        config['pose_python'] = require(svc.interpreter_path(python))
        directory = svc.ROOT / 'Ai/Pose/mac-exercise-counter/models'
        for spec in read(directory / 'manifest.json').values():
            require(directory / spec['file'])

    for name, check in (('llm', llm), ('vision', vision), ('evolution', evolution), ('pose', pose)):
        select(name, check)
    return config
