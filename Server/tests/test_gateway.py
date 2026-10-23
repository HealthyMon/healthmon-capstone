"""Real loopback HTTP contract tests; no GPU, model, or paid service required."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import struct
import threading
import time

import pytest

from healthmon.config import Settings
from healthmon.gateway import AIUnavailable, Gateway
from healthmon.worker import validate_glb


def speech():
    return {'speech': 'contract fixture', 'emotion': 'neutral', 'animation': 'idle', 'memory_ids': [],
            'classification': {'target': 'other', 'sentiment': 'neutral', 'motivation': 'neutral',
                               'character_affection': 'neutral', 'acceptance': 'none', 'confidence': .6}}


def embedding():
    return {'model_id': 'BAAI/bge-m3', 'model_version': '1', 'dimension': 1024,
            'vector': [1.] + [0.] * 1023}


def food():
    return {'candidates': [{'food': 'fixture rice', 'confidence': .9,
                           'per_100g': {'energy_kcal': 150, 'carbohydrate_g': 30,
                                       'protein_g': 3, 'fat_g': 2, 'vegetable_fruit_g': None},
                           'estimated_grams': None}]}


def envelope(body, result, **extra):
    return {'contract_version': 'healthmon.ai.v1', 'request_id': body['request_id'],
            'provenance': 'real', 'result': result, **extra}


@pytest.fixture
def remote():
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *_):
            pass

        def handle(self):
            try:
                super().handle()
            except ConnectionError:
                # The timeout fixture intentionally closes its socket early.
                pass

        def respond(self):
            content = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            body = json.loads(content) if content else None
            item = {'method': self.command, 'path': self.path, 'body': body,
                    'authorization': self.headers.get('Authorization')}
            self.server.requests.append(item)
            behavior = self.server.behavior
            if behavior:
                status, output, headers = behavior(item)
            else:
                if self.path.startswith('/v1/chat'):
                    result = speech()
                elif self.path.startswith('/v1/food'):
                    result = food()
                elif self.path.startswith('/v1/embedding'):
                    result = embedding()
                else:
                    request_id = self.path.rsplit('/', 1)[-1]
                    result = {'job_id': request_id, 'stage': 1, 'status': 'queued'}
                    body = body or {'request_id': request_id}
                status, output, headers = 200, envelope(body, result), {}
            output = output if isinstance(output, bytes) else json.dumps(output).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(output)))
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            try:
                self.wfile.write(output)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        do_POST = respond
        do_GET = respond
        do_PUT = respond

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    server.requests = []
    server.behavior = None
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    server.url = f'http://127.0.0.1:{server.server_address[1]}'
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def settings(remote=None, **extra):
    values = {'database_url': 'postgresql://unused/isolated_contract_test', 'environment': 'test',
              'ai_mode': 'remote' if remote else 'disabled', 'ai_base_url': remote.url if remote else '',
              'ai_token': 'contract-test-token', 'allow_http_ai': True,
              'test_owners': frozenset({'test-owner'}), 'ai_timeout': .5}
    return Settings(**{**values, **extra})


def call(gateway, capability='chat', request_id='stable-request-123', payload=None,
         owner='test-owner', database_is_test=True, **extra):
    return gateway.call(capability, request_id, 'fixture-pet', payload or {}, owner, database_is_test, **extra)


@pytest.mark.parametrize('capability', ['chat', 'food', 'embedding', 'evolutions'])
def test_real_http_success_contract_and_server_auth(remote, capability):
    payload = {'stage': 1} if capability == 'evolutions' else {'image_base64': 'fixture-bytes', 'content_type': 'image/png'} if capability == 'food' else {'text': 'fixture'}
    result, provenance = call(Gateway(settings(remote)), capability, payload=payload,
                              method='PUT' if capability == 'evolutions' else 'POST')
    assert provenance == 'real'
    assert result
    item = remote.requests[0]
    assert item['authorization'] == 'Bearer contract-test-token'
    assert item['body'] == {'contract_version': 'healthmon.ai.v1', 'request_id': 'stable-request-123',
                            'pet_id': 'fixture-pet', 'input': payload}
    assert item['path'] == '/v1/' + capability + ('/stable-request-123' if capability == 'evolutions' else '')


def test_food_missing_measurements_remain_null_not_zero(remote):
    result, _ = call(Gateway(settings(remote)), 'food')
    assert result['candidates'][0]['per_100g']['vegetable_fruit_g'] is None
    assert result['candidates'][0]['estimated_grams'] is None


@pytest.mark.parametrize('status,code,retryable', [(401, 'ai_authentication_failed', False),
    (403, 'ai_authentication_failed', False), (422, 'ai_http_error', False),
    (429, 'ai_http_error', True), (500, 'ai_http_error', True), (503, 'ai_http_error', True)])
def test_http_failures_no_fallback_or_hidden_retries(remote, status, code, retryable):
    remote.behavior = lambda _: (status, {'detail': 'fixture failure'}, {})
    with pytest.raises(AIUnavailable) as caught:
        call(Gateway(settings(remote)))
    assert caught.value.code == code and caught.value.retryable is retryable
    assert len(remote.requests) == 1


def test_timeout_is_retryable_and_does_not_switch_mode(remote):
    def slow(item):
        time.sleep(.1)
        return 200, envelope(item['body'], speech()), {}
    remote.behavior = slow
    gateway = Gateway(settings(remote, ai_timeout=.02))
    with pytest.raises(AIUnavailable) as caught:
        call(gateway)
    assert caught.value.code == 'ai_timeout' and caught.value.retryable is True
    assert gateway.settings.ai_mode == 'remote' and len(remote.requests) == 1


@pytest.mark.parametrize('output', [b'not-json', b'{', b'[]', {'speech': 'missing envelope'},
                                  {'contract_version': 'healthmon.ai.v1', 'request_id': 'stable-request-123', 'provenance': 'real', 'result': None}])
def test_bad_json_or_envelope_is_rejected(remote, output):
    remote.behavior = lambda _: (200, output, {})
    with pytest.raises(AIUnavailable) as caught:
        call(Gateway(settings(remote)))
    assert caught.value.code == 'ai_invalid_json_or_envelope'


@pytest.mark.parametrize('extra', [{'contract_version': 'unrecognized.v9'}, {'request_id': 'another-request'}])
def test_contract_and_request_identity_checked(remote, extra):
    remote.behavior = lambda item: (200, envelope(item['body'], speech(), **extra), {})
    with pytest.raises(AIUnavailable) as caught:
        call(Gateway(settings(remote)))
    assert caught.value.code == 'ai_contract_or_request_id_mismatch'


@pytest.mark.parametrize('result', [{**speech(), 'emotion': 'unsupported'}, {**speech(), 'speech': ''},
    {**speech(), 'classification': {**speech()['classification'], 'confidence': 1.1}},
    {**speech(), 'classification': {**speech()['classification'], 'mood': 100}}])
def test_invalid_chat_result_is_rejected(remote, result):
    remote.behavior = lambda item: (200, envelope(item['body'], result), {})
    with pytest.raises(AIUnavailable) as caught:
        call(Gateway(settings(remote)))
    assert caught.value.code == 'ai_invalid_result'


@pytest.mark.parametrize('owner,is_test,allowed', [('test-owner', True, True), ('real-owner', True, False), ('test-owner', False, False)])
def test_remote_synthetic_provenance_requires_test_owner_and_database(remote, owner, is_test, allowed):
    remote.behavior = lambda item: (200, envelope(item['body'], speech(), provenance='synthetic'), {})
    gateway = Gateway(settings(remote))
    if allowed:
        assert call(gateway, owner=owner, database_is_test=is_test)[1] == 'synthetic'
    else:
        with pytest.raises(AIUnavailable) as caught:
            call(gateway, owner=owner, database_is_test=is_test)
        assert caught.value.code == 'synthetic_result_rejected'


def test_disabled_performs_no_http_even_if_remote_url_exists(remote):
    gateway = Gateway(settings(remote, ai_mode='disabled'))
    with pytest.raises(AIUnavailable) as caught:
        call(gateway)
    assert caught.value.code == 'ai_unavailable' and remote.requests == []


def test_mock_is_explicit_deterministic_scoped_and_never_invents_completed_asset():
    gateway = Gateway(settings(ai_mode='mock'))
    assert call(gateway) == call(gateway)
    assert call(gateway)[1] == 'synthetic'
    assert gateway.space != Gateway(settings()).space
    result, _ = call(gateway, 'evolutions', payload={'stage': 3})
    assert result['status'] == 'unsupported' and result['model_url'] is None
    for owner, is_test in [('real-owner', True), ('test-owner', False)]:
        with pytest.raises(AIUnavailable, match='mock_requires_test_owner_and_database'):
            call(gateway, owner=owner, database_is_test=is_test)
    with pytest.raises(ValueError, match='Mock AI requires'):
        settings(ai_mode='mock', environment='production')


@pytest.mark.parametrize('changed', [{'model_id': 'other-model'}, {'model_version': 'other-version'},
    {'dimension': 768}, {'vector': [1.] * 768}])
def test_embedding_space_model_version_dimension_and_length_are_checked(remote, changed):
    remote.behavior = lambda item: (200, envelope(item['body'], {**embedding(), **changed}), {})
    with pytest.raises(AIUnavailable) as caught:
        call(Gateway(settings(remote)), 'embedding')
    assert caught.value.code == 'embedding_space_mismatch'


@pytest.mark.parametrize('vector,code', [([0.] * 1024, 'invalid_embedding_vector'),
    ([float('nan')] + [0.] * 1023, 'ai_invalid_result'), ([float('inf')] + [0.] * 1023, 'ai_invalid_result')])
def test_embedding_rejects_zero_and_nonfinite_vectors(remote, vector, code):
    remote.behavior = lambda item: (200, envelope(item['body'], {**embedding(), 'vector': vector}), {})
    with pytest.raises(AIUnavailable) as caught:
        call(Gateway(settings(remote)), 'embedding')
    assert caught.value.code == code


def test_mock_vector_cannot_be_labeled_as_real_remote_space(remote):
    remote.behavior = lambda item: (200, envelope(item['body'], {**embedding(), 'model_id': 'mock.embedding'}), {})
    with pytest.raises(AIUnavailable, match='embedding_space_mismatch'):
        call(Gateway(settings(remote)), 'embedding')


def test_evolution_put_then_get_reuses_original_job_identity(remote):
    gateway = Gateway(settings(remote))
    for method in ('PUT', 'GET', 'GET'):
        result, _ = call(gateway, 'evolutions', request_id='stable-job-id', payload={'stage': 1}, method=method)
        assert result['job_id'] == 'stable-job-id'
    assert [item['path'] for item in remote.requests] == ['/v1/evolutions/stable-job-id'] * 3
    assert [item['method'] for item in remote.requests] == ['PUT', 'GET', 'GET']


@pytest.mark.parametrize('changed', [{'job_id': 'foreign-job'}, {'stage': 2}])
def test_evolution_result_cannot_change_job_or_frozen_stage(remote, changed):
    remote.behavior = lambda item: (200, envelope(item['body'], {'job_id': 'stable-request-123', 'stage': 1, 'status': 'queued', **changed}), {})
    with pytest.raises(AIUnavailable, match='evolution_job_identity_mismatch'):
        call(Gateway(settings(remote)), 'evolutions', payload={'stage': 1})


def test_evolution_succeeded_requires_asset_integrity_metadata(remote):
    remote.behavior = lambda item: (200, envelope(item['body'], {'job_id': 'stable-request-123', 'stage': 1, 'status': 'succeeded'}), {})
    with pytest.raises(AIUnavailable, match='evolution_asset_metadata_required'):
        call(Gateway(settings(remote)), 'evolutions', payload={'stage': 1})


def test_response_payload_size_limit(remote):
    remote.behavior = lambda _: (200, b'x' * (2 * 1024 * 1024 + 1), {})
    with pytest.raises(AIUnavailable, match='ai_response_too_large'):
        call(Gateway(settings(remote)))


@pytest.mark.parametrize('url', ['https://elsewhere.invalid/model.glb', '//elsewhere.invalid/model.glb',
    'http://user@127.0.0.1/model.glb', '/asset.glb#fragment'])
def test_asset_origin_and_credentials_are_rejected_before_download(remote, url):
    with pytest.raises(AIUnavailable, match='asset_origin_rejected'):
        Gateway(settings(remote)).asset(url, 'a' * 64, 100)
    assert remote.requests == []


def test_asset_auth_hash_size_and_no_redirect(remote):
    data = b'contract asset bytes'
    digest = hashlib.sha256(data).hexdigest()
    remote.behavior = lambda _: (200, data, {})
    gateway = Gateway(settings(remote))
    assert gateway.asset('/asset.glb', digest, len(data)) == data
    assert remote.requests[-1]['authorization'] == 'Bearer contract-test-token'
    with pytest.raises(AIUnavailable, match='asset_integrity_failed'):
        gateway.asset('/asset.glb', '0' * 64, len(data))
    with pytest.raises(AIUnavailable, match='asset_size_mismatch'):
        gateway.asset('/asset.glb', digest, len(data) - 1)
    with pytest.raises(AIUnavailable, match='asset_integrity_failed'):
        gateway.asset('/asset.glb', digest, len(data) + 1)
    remote.behavior = lambda _: (302, b'', {'Location': '/redirected.glb'})
    before = len(remote.requests)
    with pytest.raises(AIUnavailable, match='asset_download_failed'):
        gateway.asset('/asset.glb', digest, len(data))
    assert len(remote.requests) == before + 1


def test_asset_metadata_is_required(remote):
    with pytest.raises(AIUnavailable, match='asset_integrity_metadata_required'):
        Gateway(settings(remote)).asset('/asset.glb', None, None)
    assert remote.requests == []


def test_full_quality_rigged_asset_above_previous_50_mib_limit_streams_with_integrity(remote):
    # Existing full-quality generated avatars exceed 50 MiB. Exercise a real HTTP
    # transfer in that range without requiring a model checkpoint in the CPU suite.
    data = b'x' * (50 * 1024 * 1024 + 1)
    remote.behavior = lambda _: (200, data, {})
    gateway = Gateway(settings(remote))
    assert gateway.asset('/full-quality.glb', hashlib.sha256(data).hexdigest(), len(data)) == data
    assert remote.requests[-1]['authorization'] == 'Bearer contract-test-token'


def test_oversize_asset_metadata_is_rejected_before_http_download(remote):
    with pytest.raises(AIUnavailable, match='asset_size_mismatch'):
        Gateway(settings(remote)).asset('/oversize.glb', 'a' * 64, 64 * 1024 * 1024 + 1)
    assert remote.requests == []


def glb(doc):
    encoded = json.dumps(doc).encode()
    encoded += b' ' * ((-len(encoded)) % 4)
    return struct.pack('<4sIIII', b'glTF', 2, 20 + len(encoded), len(encoded), 0x4E4F534A) + encoded


def rig_fixture():
    # Structural validation fixture, not a generated or renderable avatar asset.
    return {'asset': {'version': '2.0'}, 'skins': [{'joints': [0]}],
            'meshes': [{'primitives': [{'attributes': {'JOINTS_0': 0, 'WEIGHTS_0': 1}}]}],
            'nodes': [{'skin': 0, 'mesh': 0}], 'images': [{'bufferView': 0}], 'buffers': [{'byteLength': 0}]}


def test_glb_structural_contract_fixture_and_bad_header():
    assert validate_glb(glb(rig_fixture()))['asset']['version'] == '2.0'
    for bad in (b'', b'not-a-glb-file-contents', glb(rig_fixture())[:-1]):
        with pytest.raises(AIUnavailable, match='invalid_glb'):
            validate_glb(bad)


@pytest.mark.parametrize('change,code', [({'skins': []}, 'glb_requires_textured_rigged_mesh'),
    ({'images': [{'uri': 'file:///private/texture.png'}]}, 'glb_external_resources_rejected'),
    ({'buffers': [{'uri': 'https://untrusted.invalid/data.bin'}]}, 'glb_external_resources_rejected'),
    ({'nodes': [{}]}, 'glb_missing_skinned_node'),
    ({'meshes': [{'primitives': [{'attributes': {'POSITION': 0}}]}]}, 'glb_missing_skin_weights')])
def test_glb_rejects_missing_skin_texture_and_external_resources(change, code):
    with pytest.raises(AIUnavailable, match=code):
        validate_glb(glb({**rig_fixture(), **change}))


def test_glb_nonobject_json_is_validation_error_not_uncaught_exception():
    with pytest.raises(AIUnavailable, match='invalid_glb'):
        validate_glb(glb([]))
