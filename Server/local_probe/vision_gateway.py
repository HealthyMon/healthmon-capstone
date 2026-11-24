"""Explicit local CPU Vision bridge; no downloads, GPU or legacy app imports."""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import hmac
import io
import json
import math
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Literal
import uuid
import warnings

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from Server.healthmon.gateway import Envelope, FoodResult

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'Ai/Vision'
CONTRACT = 'healthmon.ai.v1'
BACKEND = 'team-fasterrcnn-swin-resnet18-cpu'
MULTIFOOD_BACKEND = 'dishseg-noisyvit-food2k-fpb-cpu'
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_REQUEST_BYTES = 17 * 1024 * 1024
MAX_PIXELS = 16_000_000
WEIGHTS = ('food_detector.pth', 'food_weight_checkpoint.pth', 'cuboid_model.pth')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_digest(path):
    hashed = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b''):
            hashed.update(block)
    return hashed.hexdigest()


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    os.replace(temporary, path)


class VisionInput(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, strict=True)
    image_base64: str = Field(min_length=4, max_length=4 * ((MAX_IMAGE_BYTES + 2) // 3))
    content_type: Literal['image/jpeg', 'image/png']


class RequestBody(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, strict=True)
    contract_version: Literal['healthmon.ai.v1']
    request_id: str = Field(min_length=8, max_length=100)
    pet_id: str = Field(min_length=1, max_length=100)
    input: VisionInput


class RequestLimit:
    """Bound actual streamed JSON bytes before FastAPI buffers/parses them."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('path') != '/v1/food':
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        try:
            declared = int(headers.get(b'content-length', b'0'))
        except ValueError:
            return await JSONResponse({'code': 'invalid_content_length'}, status_code=400)(scope, receive, send)
        if declared < 0 or declared > MAX_REQUEST_BYTES:
            return await JSONResponse({'code': 'vision_request_too_large'}, status_code=413)(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body.extend(message.get('body', b''))
            if len(body) > MAX_REQUEST_BYTES:
                return await JSONResponse({'code': 'vision_request_too_large'}, status_code=413)(scope, receive, send)
            if not message.get('more_body', False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()

        return await self.app(scope, replay, send)


def decode_image(value):
    from PIL import Image, UnidentifiedImageError
    try:
        raw = base64.b64decode(value.image_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, {'code': 'invalid_image_base64'}) from None
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(413, {'code': 'vision_image_too_large'})
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as picture:
                actual = {'JPEG': 'image/jpeg', 'PNG': 'image/png'}.get(picture.format)
                if actual is None or actual != value.content_type:
                    raise HTTPException(415, {'code': 'image_mime_mismatch'})
                if picture.width * picture.height > MAX_PIXELS:
                    raise HTTPException(413, {'code': 'vision_image_pixel_limit'})
                picture.verify()
            with Image.open(io.BytesIO(raw)) as picture:
                picture.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise HTTPException(422, {'code': 'invalid_image_bytes'}) from None
    return raw


def verify_assets(assets, source=SOURCE):
    """Check pinned LFS identities with either pointers or hydrated checkouts.

    The small tracked manifest preserves the Git LFS identities after checkout
    replaces pointers with binary checkpoints; Git is not required at runtime.
    """
    checked = {}
    manifest_path = source / 'weights-manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    for name in WEIGHTS:
        declaration = source / name
        # Never decode a full (possibly hundreds of MB) binary checkpoint.
        with declaration.open('rb') as stream:
            header = stream.read(512)
        match = re.fullmatch(rb'version https://git-lfs.github.com/spec/v1\r?\noid sha256:([0-9a-f]{64})\r?\nsize ([0-9]+)(?:\r?\n)?', header)
        expected = {'sha256': match[1].decode('ascii'), 'size_bytes': int(match[2])} if match else manifest.get(name)
        if (not isinstance(expected, dict) or not re.fullmatch(r'[0-9a-f]{64}', str(expected.get('sha256', '')))
                or type(expected.get('size_bytes')) is not int or expected['size_bytes'] <= 0):
            raise ValueError('Expected pinned Git LFS model identity declaration')
        if name in manifest and manifest[name] != expected:
            raise ValueError('Vision manifest and Git LFS pointer disagree')
        if not match and (declaration.stat().st_size != expected['size_bytes'] or file_digest(declaration) != expected['sha256']):
            raise ValueError('Hydrated Vision checkpoint differs from its pinned identity')
        path = assets / name
        if path.stat().st_size != expected['size_bytes'] or file_digest(path) != expected['sha256']:
            raise ValueError('Existing Vision model differs from its declared identity')
        checked[name] = expected
    return checked


def normalize_result(raw):
    """Map legacy seven-nutrient candidates without fabricating measurements."""
    if not isinstance(raw, dict) or raw.get('backend') not in (BACKEND, MULTIFOOD_BACKEND):
        raise ValueError('Vision backend identity mismatch')
    candidates = raw.get('candidates')
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 3:
        raise ValueError('Vision did not return one to three actual candidates')
    mapped = []
    for item in candidates:
        if not isinstance(item, dict) or not isinstance(item.get('per_100g'), dict):
            raise ValueError('Vision candidate nutrients are invalid')
        nutrients = {key: item['per_100g'].get(key) for key in
                     ('energy_kcal', 'carbohydrate_g', 'protein_g', 'fat_g')}
        nutrients['vegetable_fruit_g'] = None  # No such measurement exists in the team model.
        for number in [item.get('confidence'), item.get('estimated_grams')] + list(nutrients.values()):
            if number is not None and (isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number)):
                raise ValueError('Vision numeric measurement is invalid')
        mapped.append({'food': item.get('food'), 'confidence': item.get('confidence'),
                       'per_100g': nutrients, 'estimated_grams': item.get('estimated_grams')})
    value = {'candidates': mapped}
    if raw['backend'] == MULTIFOOD_BACKEND:
        if not raw.get('vision'):
            raise ValueError('Multi-food result has no regions')
        value['vision'] = raw['vision']
    result = FoodResult.model_validate(value).model_dump(mode='json')
    if result['vision'] is None:
        result.pop('vision')
    return result


class NoFoodDetected(ValueError):
    pass


class VisionRunner:
    def __init__(self, config, runtime):
        self.multifood = config.get('vision_backend') == 'multifood'
        self.container = self.multifood and config.get('vision_container') is True
        # POSIX venv executables are symlinks. Resolving the link launches the
        # base interpreter and discards the vision environment's dependencies.
        self.python = Path(os.path.abspath(config['vision_python']))
        self.assets = Path(config['vision_assets']).resolve()
        self.runtime = runtime
        if not self.python.is_file() or not self.assets.is_dir():
            raise ValueError('Existing local Vision runtime and assets required')
        # Reuse only the available CPU image-validation dependency. This is
        # appended after the server environment; no installation or model
        # import occurs, and existing FastAPI/Pydantic resolution stays first.
        try:
            import PIL
        except ModuleNotFoundError:
            existing_site = self.python.parent.parent / 'Lib/site-packages'
            if not (existing_site / 'PIL/__init__.py').is_file():
                raise ValueError('Existing Vision Pillow dependency unavailable') from None
            sys.path.append(str(existing_site))
            import PIL
        self.timeout = config.get('timeout_seconds', 300)
        if isinstance(self.timeout, bool) or not isinstance(self.timeout, int) or not 1 <= self.timeout <= 300:
            raise ValueError('Vision timeout must be one to300 seconds')
        if self.multifood:
            from Ai.Vision.multifood.assets import verify
            self.docker = shutil.which('docker') if self.container else None
            if self.container and not self.docker:
                raise ValueError('Docker is required for the multi-food runtime')
            self.identity = {'backend': MULTIFOOD_BACKEND, 'device': 'cpu', 'downloaded': False,
                'model_sha256': verify(self.assets),
                'nutrition_sha256': file_digest(self.assets / 'nutrition.csv'),
                'source_sha256': {'worker.py': file_digest(SOURCE / 'multifood/worker.py')},
                'gateway_sha256': file_digest(Path(__file__)), 'model_loaded_at_startup': False}
            return
        self.identity = {'backend': BACKEND, 'device': 'cpu', 'downloaded': False,
            'model_sha256': verify_assets(self.assets),
            'nutrition_sha256': file_digest(self.assets / 'nutrition.json'),
            'source_sha256': {name: file_digest(SOURCE / name) for name in ('main.py', 'service_worker.py')},
            'worker_sha256': file_digest(Path(__file__).with_name('vision_worker.py')),
            'gateway_sha256': file_digest(Path(__file__)), 'model_loaded_at_startup': False}

    def analyze(self, image, request_key):
        started = time.monotonic()
        command = [str(self.python), '-X', 'utf8', '-B', '-u', str(Path(__file__).with_name('vision_worker.py')),
                   '--source', str(SOURCE), '--assets', str(self.assets)]
        image_path = str(image)
        container_name = None
        if self.multifood:
            command = [str(self.python), '-X', 'utf8', '-B', str(SOURCE / 'multifood/worker.py')]
        if self.container:
            container_name = 'healthmon-food-' + uuid.uuid4().hex
            command = [self.docker, 'run', '--rm', '--network', 'none', '-i', '--name', container_name,
                '--mount', f'type=bind,src={SOURCE},dst=/app/Ai/Vision,readonly',
                '--mount', f'type=bind,src={image.parent},dst=/input,readonly',
                '--entrypoint', '/opt/vision/bin/python', 'healthmon-multifood:local',
                '-B', '/app/Ai/Vision/multifood/worker.py']
            image_path = '/input/' + image.name
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', CUDA_VISIBLE_DEVICES='',
                           HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', TORCH_HOME=str(self.runtime / 'cache'))
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', cwd=self.runtime, env=environment,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), start_new_session=os.name != 'nt')
        try:
            stdout, stderr = process.communicate(json.dumps({'id': request_key, 'image': image_path}), timeout=self.timeout)
        except subprocess.TimeoutExpired:
            if container_name:
                try:
                    subprocess.run([self.docker, 'rm', '-f', container_name], capture_output=True, timeout=15,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                except (OSError, subprocess.TimeoutExpired):
                    pass  # Still reap the owned docker client and its pipes below.
            cleanup = stop_owned_worker(process)
            atomic_json(self.runtime / 'logs' / (request_key + '.timeout-cleanup.json'), cleanup)
            try:
                _, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                stderr = 'Owned worker pipe did not close after bounded tree cleanup.'
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()
            (self.runtime / 'logs' / (request_key + '.stderr.log')).write_text(stderr or '', encoding='utf-8')
            raise
        (self.runtime / 'logs' / (request_key + '.stderr.log')).write_text(stderr, encoding='utf-8')
        response = json.loads(stdout)
        if response.get('id') == request_key and response.get('no_food'):
            raise NoFoodDetected('No food detected')
        if process.returncode or response.get('id') != request_key or 'error' in response:
            raise RuntimeError('Existing Vision worker failed')
        raw = response['result']
        return raw, {'elapsed_seconds': round(time.monotonic() - started, 3),
                     'worker_result_sha256': digest(raw), 'backend': self.identity['backend'], 'device': 'cpu'}


def stop_owned_worker(process):
    """Bound cleanup to the Popen worker this caller spawned, including its launcher child."""
    audit = {'root_pid': process.pid, 'root_reaped': False,
             'owned_tree_termination_confirmed': False}
    try:
        if os.name == 'nt':
            # The Windows venv redirector can own a Python child. Kill that
            # exact PID tree before reaping the redirector, never by image name.
            stopped = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                capture_output=True, timeout=10, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            audit.update(method='taskkill_owned_pid_tree', tree_stop_returncode=stopped.returncode)
            audit['owned_tree_termination_confirmed'] = stopped.returncode == 0
        elif os.getpgid(process.pid) == process.pid:
            os.killpg(process.pid, signal.SIGKILL)
            audit.update(method='isolated_owned_process_group', owned_tree_termination_confirmed=True)
        else:
            process.kill()
            audit['method'] = 'owned_root_only_unconfirmed_tree'
    except Exception as exc:
        audit['cleanup_error_name'] = type(exc).__name__
        if process.poll() is None:
            process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
    audit['root_reaped'] = process.poll() is not None
    audit['owned_tree_termination_confirmed'] = audit['owned_tree_termination_confirmed'] and audit['root_reaped']
    return audit


def create_app(config_path, *, runner=None):
    config_path = Path(config_path).resolve()
    runtime = config_path.parent
    if not runtime.is_relative_to(ROOT / '.runtime'):
        raise ValueError('Vision private runtime must stay in this checkout .runtime')
    config = json.loads(config_path.read_text(encoding='utf-8'))
    if config.get('environment') != 'test' or config.get('vision_enabled') is not True or not isinstance(config.get('server_token'), str) or not config['server_token']:
        raise ValueError('Explicit test Vision opt-in and private authentication required')
    for folder in ('requests', 'responses', 'work', 'logs', 'cache'):
        (runtime / folder).mkdir(exist_ok=True)
    actual_runner = runner if runner is not None else VisionRunner(config, runtime)
    lock = threading.RLock()
    app = FastAPI(title='HEALTHMON explicit local CPU Vision bridge')
    app.add_middleware(RequestLimit)
    app.state.runner = actual_runner

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_, exc):
        oversized = any(item['type'] == 'string_too_long' and item['loc'][-1] == 'image_base64'
                        for item in exc.errors())
        return JSONResponse({'code': 'vision_image_too_large' if oversized else 'invalid_vision_request'},
                            status_code=413 if oversized else 422)

    def authenticate(authorization: str | None = Header(default=None)):
        token = authorization[len('Bearer '):] if authorization and authorization.startswith('Bearer ') else ''
        if not hmac.compare_digest(token, config['server_token']):
            raise HTTPException(401, {'code': 'server_authentication_required'})

    @app.get('/health')
    def health():
        return {'ready': True, 'provenance': 'real', 'local_acceptance_only': True,
                'contract_version': CONTRACT, 'capability': 'food', 'model': actual_runner.identity}

    @app.post('/v1/food', dependencies=[Depends(authenticate)])
    def food(body: RequestBody):
        raw = decode_image(body.input)
        fingerprint = digest(body.model_dump(mode='json'))  # All four public fields.
        key = digest({'capability': 'food', 'request_id': body.request_id})
        journal, cache = runtime / 'requests' / (key + '.json'), runtime / 'responses' / (key + '.json')
        with lock:
            if journal.is_file() and json.loads(journal.read_text(encoding='utf-8'))['fingerprint'] != fingerprint:
                raise HTTPException(409, {'code': 'request_id_content_conflict'})
            if cache.is_file():
                try:
                    stored = json.loads(cache.read_text(encoding='utf-8'))
                    if stored['fingerprint'] != fingerprint:
                        raise HTTPException(409, {'code': 'request_id_content_conflict'})
                    envelope = Envelope.model_validate(stored['envelope'])
                    FoodResult.model_validate(envelope.result)
                except (ValueError, KeyError, ValidationError):
                    raise HTTPException(503, {'code': 'vision_cached_result_invalid'}) from None
                if envelope.contract_version != CONTRACT or envelope.request_id != body.request_id or envelope.provenance != 'real':
                    raise HTTPException(503, {'code': 'vision_cached_identity_invalid'})
                return envelope.model_dump(mode='json')
            record = {'fingerprint': fingerprint, 'request_id': body.request_id, 'pet_id': body.pet_id,
                      'image_sha256': hashlib.sha256(raw).hexdigest(), 'status': 'running'}
            atomic_json(journal, record)
            try:
                with tempfile.TemporaryDirectory(prefix='image-', dir=runtime / 'work') as folder:
                    image = Path(folder) / ('image.png' if body.input.content_type == 'image/png' else 'image.jpg')
                    image.write_bytes(raw)
                    legacy, metrics = actual_runner.analyze(image, key)
                result = normalize_result(legacy)
                envelope = Envelope(contract_version=CONTRACT, request_id=body.request_id,
                                    provenance='real', result=result).model_dump(mode='json')
                atomic_json(cache, {'fingerprint': fingerprint, 'envelope': envelope,
                    'image_sha256': record['image_sha256'], 'model': actual_runner.identity,
                    'metrics': metrics, 'legacy_result': legacy,
                    'consumption_confirmed': False, 'result_sha256': digest(result)})
                atomic_json(journal, dict(record, status='succeeded'))
                return envelope
            except Exception as exc:
                atomic_json(journal, dict(record, status='failed', error_type=type(exc).__name__))
                atomic_json(runtime / 'last-error.json', {'request_id': body.request_id, 'pet_id': body.pet_id,
                    'error_type': type(exc).__name__, 'fingerprint': fingerprint, 'fallback': False})
                status = 422 if isinstance(exc, NoFoodDetected) else 504 if isinstance(exc, subprocess.TimeoutExpired) else 502
                raise HTTPException(status,
                                    {'code': 'no_food_detected' if isinstance(exc, NoFoodDetected) else 'real_vision_failed',
                                     'type': type(exc).__name__, 'fallback': False}) from None

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(create_app(args.config), host='127.0.0.1', port=18094, workers=1, access_log=False)


if __name__ == '__main__':
    main()
