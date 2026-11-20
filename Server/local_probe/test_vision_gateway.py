"""CPU contract tests use labelled doubles; no model/runtime imports or inference."""
import base64
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest

Image = pytest.importorskip('PIL.Image', reason='Use the existing Vision CPU Pillow runtime for these optional integration tests')

from Server.local_probe import vision_gateway as vision


def picture(color='red', size=(8, 8), format='PNG'):
    data = io.BytesIO()
    Image.new('RGB', size, color).save(data, format=format)
    return data.getvalue()


def legacy():
    return {'backend': vision.BACKEND, 'detected_count': 1, 'candidates': [
        {'food': 'fixture meal', 'confidence': .375, 'estimated_grams': None,
         'weight_warning': 'fixture unknown weight',
         'per_100g': {'energy_kcal': 123., 'carbohydrate_g': 20., 'protein_g': 3., 'fat_g': None,
                     'sugar_g': None, 'fiber_g': 1., 'sodium_mg': 4.}}]}


class FixtureRunner:
    identity = {'backend': vision.BACKEND, 'device': 'cpu', 'test_double': True}

    def __init__(self):
        self.calls = []
        self.output = legacy()

    def analyze(self, path, key):
        self.calls.append((path.read_bytes(), key))
        if isinstance(self.output, Exception):
            raise self.output
        return deepcopy(self.output), {'test_double': True}


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    monkeypatch.setattr(vision, 'ROOT', tmp_path)
    runtime = tmp_path / '.runtime' / 'vision-fixture'
    runtime.mkdir(parents=True)
    config = runtime / 'private.json'
    config.write_text(json.dumps({'environment': 'test', 'vision_enabled': True,
                                  'server_token': 'fixture-private-bearer'}), encoding='utf-8')
    runner = FixtureRunner()
    client = TestClient(vision.create_app(config, runner=runner))
    return client, runner, runtime


def request(raw=None, **changes):
    value = {'contract_version': vision.CONTRACT, 'request_id': 'fixture-request-001',
             'pet_id': 'fixture-pet', 'input': {'content_type': 'image/png',
             'image_base64': base64.b64encode(raw if raw is not None else picture()).decode()}}
    value.update(changes)
    return value


def post(bridge, body=None, **kwargs):
    return bridge[0].post('/v1/food', json=body if body is not None else request(),
        headers={'Authorization': 'Bearer fixture-private-bearer'}, **kwargs)


def test_authenticated_exact_envelope_and_nullable_measurements(bridge):
    response = post(bridge)
    assert response.status_code == 200
    value = response.json()
    assert set(value) == {'contract_version', 'request_id', 'provenance', 'result'}
    assert value['provenance'] == 'real'  # HTTP contract fixture, not actual model evidence.
    candidate = value['result']['candidates'][0]
    assert candidate['confidence'] == .375
    assert candidate['estimated_grams'] is None
    assert candidate['per_100g'] == {'energy_kcal': 123., 'carbohydrate_g': 20.,
        'protein_g': 3., 'fat_g': None, 'vegetable_fruit_g': None}
    assert len(bridge[1].calls) == 1 and bridge[1].calls[0][0] == picture()
    cached = json.loads(next((bridge[2] / 'responses').glob('*.json')).read_text(encoding='utf-8'))
    assert cached['consumption_confirmed'] is False and cached['metrics']['test_double'] is True
    assert cached['legacy_result'] == legacy()


def test_same_four_field_input_is_exactly_cached_without_second_worker(bridge):
    body = request()
    first = post(bridge, body)
    assert post(bridge, deepcopy(body)).json() == first.json()
    assert len(bridge[1].calls) == 1
    cached = json.loads(next((bridge[2] / 'responses').glob('*.json')).read_text(encoding='utf-8'))
    assert cached['fingerprint'] == vision.digest(body)
    assert not any((bridge[2] / 'work').iterdir())


@pytest.mark.parametrize('changed', ['pet', 'image'])
def test_request_id_cannot_move_pet_or_change_image(bridge, changed):
    assert post(bridge).status_code == 200
    body = request(pet_id='another-pet') if changed == 'pet' else request(picture('blue'))
    assert post(bridge, body).status_code == 409
    assert len(bridge[1].calls) == 1


def test_missing_or_wrong_bearer_does_not_run_worker(bridge):
    for headers in ({}, {'Authorization': 'Bearer wrong'}):
        assert bridge[0].post('/v1/food', json=request(), headers=headers).status_code == 401
    assert bridge[1].calls == []


@pytest.mark.parametrize('extra', ['image_path', 'path', 'image_url', 'url'])
def test_local_or_remote_path_input_is_rejected_without_echo(bridge, extra):
    body = request()
    body['input'][extra] = 'private-path-or-url-must-not-be-echoed'
    response = post(bridge, body)
    assert response.status_code == 422
    assert 'private-path-or-url' not in response.text
    assert bridge[1].calls == []


@pytest.mark.parametrize('raw', ['not base64!!', 'data:image/png;base64,AAAA', 'C:/private/image.jpg'])
def test_invalid_base64_and_data_urls_are_rejected(bridge, raw):
    body = request()
    body['input']['image_base64'] = raw
    assert post(bridge, body).status_code == 422
    assert bridge[1].calls == []


@pytest.mark.parametrize('format,mime,status', [('JPEG', 'image/jpeg', 200), ('PNG', 'image/jpeg', 415),
                                               ('GIF', 'image/png', 415)])
def test_content_bytes_and_declared_mime_must_agree(bridge, format, mime, status):
    body = request(picture(format=format))
    body['input']['content_type'] = mime
    assert post(bridge, body).status_code == status


def test_malformed_image_bytes_are_not_treated_as_a_model_result(bridge):
    assert post(bridge, request(b'not-an-image')).status_code == 422
    assert bridge[1].calls == []


def test_sixteen_megapixel_limit_is_checked_before_model(bridge):
    assert post(bridge, request(picture(size=(4001, 4000)))).status_code == 413
    assert bridge[1].calls == []


def test_decoded_byte_limit_is_twelve_mib(bridge):
    value = picture() + b'\0' * vision.MAX_IMAGE_BYTES
    assert post(bridge, request(value)).status_code == 413
    assert bridge[1].calls == []


def test_streamed_json_and_declared_length_are_both_bounded(bridge):
    client = bridge[0]
    headers = {'Authorization': 'Bearer fixture-private-bearer', 'Content-Type': 'application/json'}
    response = client.post('/v1/food', content=iter([b' ' * (vision.MAX_REQUEST_BYTES + 1)]), headers=headers)
    assert response.status_code == 413
    response = client.post('/v1/food', content=b'{}', headers=dict(headers, **{'Content-Length': str(vision.MAX_REQUEST_BYTES + 1)}))
    assert response.status_code == 413 and bridge[1].calls == []


@pytest.mark.parametrize('failure', [RuntimeError('private fixture failure'), subprocess.TimeoutExpired('private command', 300)])
def test_actual_worker_failure_is_preserved_without_canned_result(bridge, failure):
    bridge[1].output = failure
    response = post(bridge)
    assert response.status_code == (504 if isinstance(failure, subprocess.TimeoutExpired) else 502)
    assert response.json()['detail']['fallback'] is False
    assert 'private' not in response.text
    assert not any((bridge[2] / 'responses').iterdir())
    journal = json.loads(next((bridge[2] / 'requests').glob('*.json')).read_text(encoding='utf-8'))
    assert journal['status'] == 'failed'
    assert post(bridge, request(pet_id='changed-after-failure')).status_code == 409
    bridge[1].output = legacy()
    assert post(bridge).status_code == 200


@pytest.mark.parametrize('change', ['empty', 'backend', 'nan', 'bool', 'negative', 'zero_weight', 'too_many'])
def test_invalid_or_missing_vision_measurements_never_become_a_fabricated_success(bridge, change):
    raw = bridge[1].output
    if change == 'empty': raw['candidates'] = []
    elif change == 'backend': raw['backend'] = 'synthetic'
    elif change == 'nan': raw['candidates'][0]['confidence'] = float('nan')
    elif change == 'bool': raw['candidates'][0]['per_100g']['protein_g'] = True
    elif change == 'negative': raw['candidates'][0]['per_100g']['protein_g'] = -1
    elif change == 'zero_weight': raw['candidates'][0]['estimated_grams'] = 0
    else: raw['candidates'] *= 4
    assert post(bridge).status_code == 502


def test_unmeasured_vegetable_grams_are_always_null_and_weight_stays_estimate():
    raw = legacy()
    raw['candidates'][0]['per_100g']['vegetable_fruit_g'] = 100
    raw['candidates'][0]['estimated_grams'] = 42.5
    result = vision.normalize_result(raw)['candidates'][0]
    assert result['per_100g']['vegetable_fruit_g'] is None
    assert result['estimated_grams'] == 42.5 and result['confidence'] == .375


def test_lfs_declarations_require_exact_existing_model_bytes(tmp_path):
    source, assets = tmp_path / 'source', tmp_path / 'assets'
    source.mkdir(); assets.mkdir()
    for name in vision.WEIGHTS:
        raw = ('fixture-weight-' + name).encode()
        (assets / name).write_bytes(raw)
        (source / name).write_text('version https://git-lfs.github.com/spec/v1\n'
            + 'oid sha256:' + hashlib.sha256(raw).hexdigest() + '\nsize ' + str(len(raw)) + '\n', encoding='utf-8')
    assert len(vision.verify_assets(assets, source)) == 3
    (assets / vision.WEIGHTS[0]).write_bytes(b'wrong-checkpoint')
    with pytest.raises(ValueError):
        vision.verify_assets(assets, source)


@pytest.mark.parametrize('change', [{'environment': 'production'}, {'vision_enabled': False}, {'server_token': ''}])
def test_private_explicit_opt_in_is_required(bridge, change):
    config = bridge[2] / 'private.json'
    value = json.loads(config.read_text(encoding='utf-8'));value.update(change)
    config.write_text(json.dumps(value), encoding='utf-8')
    with pytest.raises(ValueError):
        vision.create_app(config, runner=FixtureRunner())


def test_runner_timeout_invokes_its_owned_tree_cleanup_and_keeps_failure_metadata(tmp_path, monkeypatch):
    class OwnedProcess:
        pid = 424242
        calls = 0
        returncode = -1

        def communicate(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired('fixture-private-command', 1)
            return '', 'fixture diagnostic retained privately'

    owned, stopped = OwnedProcess(), []
    monkeypatch.setattr(vision.subprocess, 'Popen', lambda *args, **kwargs: owned)
    monkeypatch.setattr(vision, 'stop_owned_worker', lambda process: stopped.append(process) or {
        'root_pid': process.pid, 'root_reaped': True, 'owned_tree_termination_confirmed': True})
    runner = vision.VisionRunner.__new__(vision.VisionRunner)
    runner.python, runner.assets, runner.runtime, runner.timeout = Path(sys.executable), tmp_path, tmp_path, 1
    (tmp_path / 'logs').mkdir()
    with pytest.raises(subprocess.TimeoutExpired):
        runner.analyze(tmp_path / 'fixture.jpg', 'fixture-key')
    assert stopped == [owned] and owned.calls == 2
    cleanup = json.loads((tmp_path / 'logs/fixture-key.timeout-cleanup.json').read_text(encoding='utf-8'))
    assert cleanup['root_pid'] == owned.pid and cleanup['owned_tree_termination_confirmed'] is True
    assert 'private-command' not in json.dumps(cleanup)


@pytest.mark.skipif(sys.platform != 'win32', reason='Actual Windows venv launcher tree regression')
def test_windows_timeout_cleanup_reaps_only_its_owned_launcher_and_child():
    import ctypes

    command = 'import subprocess,sys,time; child=subprocess.Popen([sys.executable,"-B","-c","import time; time.sleep(30)"]); print(child.pid,flush=True); time.sleep(30)'
    owned = subprocess.Popen([sys.executable, '-B', '-u', '-c', command], stdout=subprocess.PIPE,
                             text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    unrelated = subprocess.Popen([sys.executable, '-B', '-c', 'import time; time.sleep(30)'],
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    child_pid = int(owned.stdout.readline())
    try:
        audit = vision.stop_owned_worker(owned)
        assert audit['root_pid'] == owned.pid and audit['root_reaped'] is True
        assert audit['owned_tree_termination_confirmed'] is True
        assert audit['method'] == 'taskkill_owned_pid_tree'
        assert unrelated.poll() is None
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x100000, False, child_pid)
        if handle:
            try:
                kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
                assert kernel.WaitForSingleObject(handle, 1000) == 0
            finally:
                kernel.CloseHandle.argtypes = [ctypes.c_void_p]
                kernel.CloseHandle(handle)
    finally:
        if owned.poll() is None:
            vision.stop_owned_worker(owned)
        owned.stdout.close()
        unrelated.terminate()
        unrelated.wait(timeout=5)
