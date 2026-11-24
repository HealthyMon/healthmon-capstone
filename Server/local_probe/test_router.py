"""Controlled real HTTP routing: no AI, GPU or actual health photographs."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread

from fastapi.testclient import TestClient
import pytest

from Server.healthmon.gateway import Envelope, FoodResult
from Server.local_probe import router

TOKEN = 'synthetic-router-fixture-token'
HEADERS = {'Authorization': 'Bearer ' + TOKEN}


@pytest.fixture
def upstreams(tmp_path, monkeypatch):
    servers, observed = [], []
    result = {'candidates': [{'food': 'fixture food', 'confidence': .8,
        'per_100g': {'energy_kcal': None, 'carbohydrate_g': None, 'protein_g': None,
                    'fat_g': None, 'vegetable_fruit_g': None}, 'estimated_grams': None}]}

    def start(capability):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def serve(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                observed.append({'capability': capability, 'method': self.command, 'path': self.path,
                    'body_sha256': hashlib.sha256(body).hexdigest(), 'size': len(body),
                    'authorization': self.headers.get('Authorization'), 'content_type': self.headers.get('Content-Type')})
                if self.path == '/health':
                    content, status = json.dumps({'ready': getattr(self.server, 'ready', True)}).encode(), 200
                elif self.path == '/v1/food':
                    value = json.loads(body)
                    content = json.dumps({'contract_version': 'healthmon.ai.v1', 'request_id': value['request_id'],
                        'provenance': 'real', 'result': result}).encode()
                    status = getattr(self.server, 'food_status', 200)
                else:
                    content, status = b'{"fixture":true}', 200
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            do_POST = do_PUT = do_GET = serve

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        thread.start()
        servers.append((server, thread))
        monkeypatch.setitem(router.CAPABILITY_ORIGINS, capability, 'http://127.0.0.1:' + str(server.server_port))
        return server

    for capability in router.CAPABILITY_ORIGINS:
        start(capability)
    key = tmp_path/'private.json'
    key.write_text(json.dumps({'server_token': TOKEN}), encoding='utf-8')
    with TestClient(router.create_app(key)) as client:
        yield client, observed, {capability: server for capability,(server,_) in zip(router.CAPABILITY_ORIGINS,servers)}
    for server, thread in servers:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def wrapper(size=8):
    return {'contract_version': 'healthmon.ai.v1', 'request_id': 'router-fixture-request',
            'pet_id': 'pseudonymous-router-pet',
            'input': {'image_base64': base64.b64encode(b'\x89PNG\r\n\x1a\n'+b'\0'*(size-8)).decode(),
                      'content_type': 'image/png'}}


def test_real_food_http_forwards_complete_twelve_mib_raw_equivalent(upstreams):
    client, seen, _ = upstreams
    raw = json.dumps(wrapper(12*1024*1024), separators=(',', ':')).encode()
    assert 16*1024*1024 < len(raw) < router.FOOD_REQUEST_LIMIT
    response = client.post('/v1/food', content=raw, headers=HEADERS)
    assert response.status_code == 200 and response.headers['cache-control'] == 'private, no-store'
    envelope = Envelope.model_validate(response.json())
    assert envelope.request_id == 'router-fixture-request' and envelope.provenance == 'real'
    assert len(FoodResult.model_validate(envelope.result).candidates) == 1
    assert seen == [{'capability': 'food', 'method': 'POST', 'path': '/v1/food',
        'body_sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw), 'authorization': HEADERS['Authorization'],
        'content_type': 'application/json'}]


@pytest.mark.parametrize('method,path,capability', [('POST','chat','chat'), ('POST','embedding','embedding'),
    ('PUT','evolutions/fixture-job','evolutions'), ('GET','evolutions/fixture-job','evolutions'),
    ('GET','assets/fixture-job/model.glb','evolutions')])
def test_other_capability_routes_and_bytes_remain_exact(upstreams, method, path, capability):
    client, seen, _ = upstreams
    response = client.request(method, '/v1/'+path, content=b'{"fixture":"exact"}', headers=HEADERS)
    assert response.status_code == 200 and response.content == b'{"fixture":true}'
    assert seen[0]['capability'] == capability and seen[0]['path'] == '/v1/'+path
    assert seen[0]['method'] == method and seen[0]['body_sha256'] == hashlib.sha256(b'{"fixture":"exact"}').hexdigest()


@pytest.mark.parametrize('path,limit', [('food',router.FOOD_REQUEST_LIMIT), ('chat',router.DEFAULT_REQUEST_LIMIT)])
def test_declared_and_streamed_oversize_are_rejected_without_upstream(upstreams, path, limit):
    client, seen, _ = upstreams
    assert client.post('/v1/'+path, content=b'',headers=dict(HEADERS, **{'Content-Length':str(limit+1)})).status_code==413
    def chunks():
        yield b'a'*limit
        yield b'b'
    assert client.post('/v1/'+path, content=chunks(),headers=HEADERS).status_code==413
    assert seen == []


def test_upstream_food_error_is_passed_without_chat_fallback(upstreams):
    client, seen, servers = upstreams
    servers['food'].food_status=503
    response=client.post('/v1/food',json=wrapper(),headers=HEADERS)
    assert response.status_code==503 and [s['capability'] for s in seen]==['food']


def test_unavailable_food_is_explicit_503_and_never_routed_to_llm(upstreams, monkeypatch):
    client, seen, servers = upstreams
    server=servers['food']
    server.shutdown(); server.server_close()
    response=client.post('/v1/food',json=wrapper(),headers=HEADERS)
    assert response.status_code==503 and response.json()['detail']=='The selected real capability is unavailable'
    assert seen == []


def test_authentication_unknown_path_and_invalid_length_do_not_call_any_upstream(upstreams):
    client, seen, _ = upstreams
    assert client.post('/v1/food',json=wrapper()).status_code==401
    assert client.post('/v1/not-configured',json={},headers=HEADERS).status_code==404
    assert client.post('/v1/food',content=b'',headers=dict(HEADERS, **{'Content-Length':'invalid'})).status_code==400
    assert client.post('/v1/food',content=b'',headers=dict(HEADERS, **{'Content-Length':'-1'})).status_code==400
    assert seen == []


def test_default_food_origin_and_health_describe_configuration_only(tmp_path):
    assert router.CAPABILITY_ORIGINS == {'chat':'http://127.0.0.1:18091','embedding':'http://127.0.0.1:18091',
        'food':'http://127.0.0.1:18094','evolutions':'http://127.0.0.1:18093'}
    key=tmp_path/'private.json'; key.write_text(json.dumps({'server_token':TOKEN}))
    with TestClient(router.create_app(key)) as client:
        health=client.get('/health').json()
    assert health['automatic_fallback'] is False and health['food_json_request_limit_bytes']==17*1024*1024
    assert health['configured_capability_origins']['food']=='http://127.0.0.1:18094'
    assert 'ready' not in health


def test_live_services_require_auth_and_distinguish_loading_generation_and_stopping(upstreams, tmp_path, monkeypatch):
    import time
    from Server.local_probe import local_services
    state_path, stop_path = tmp_path / 'status.json', tmp_path / 'stop'
    monkeypatch.setattr(local_services, 'STATUS', state_path)
    monkeypatch.setattr(local_services, 'STOP', stop_path)
    client, seen, servers = upstreams
    assert client.get('/health/services').status_code == 401
    assert not seen
    assert client.get('/health/services', headers=HEADERS).json()['status'] == 'ready'
    servers['chat'].ready = False
    state_path.write_text(json.dumps({'phase': 'starting', 'updated_at': time.time()}))
    body = client.get('/health/services', headers=HEADERS).json()
    assert body['status'] == 'loading' and body['services']['chat']['available'] is False
    assert body['services']['vision']['available'] is True
    state_path.write_text(json.dumps({'phase': 'generating_3d', 'updated_at': time.time()}))
    body = client.get('/health/services', headers=HEADERS).json()
    assert body['status'] == 'generating_3d' and body['services']['chat']['status'] == 'generating_3d'
    stop_path.touch()
    assert client.get('/health/services', headers=HEADERS).json()['status'] == 'stopping'
    # The router's own readiness must not depend on downstream model warmup.
    assert client.get('/health').json()['status'] == 'ok'


@pytest.mark.parametrize('failed,code,status', [(False,501,'not_installed'),(True,503,'error')])
def test_uninstalled_or_failed_capability_is_isolated(upstreams,tmp_path,monkeypatch,failed,code,status):
    import time
    from Server.local_probe import local_services
    state=tmp_path/'status.json';stop=tmp_path/'stop'
    monkeypatch.setattr(local_services,'STATUS',state)
    monkeypatch.setattr(local_services,'STOP',stop)
    state.write_text(json.dumps({'phase':'ready','updated_at':time.time(),
        'failed' if failed else 'skipped':{'llm':'controlled fixture'}}))
    client,seen,_=upstreams
    assert client.post('/v1/chat',json={},headers=HEADERS).status_code==code
    assert seen==[]
    response=client.post('/v1/food',json=wrapper(),headers=HEADERS)
    assert response.status_code==200 and [x['capability'] for x in seen]==['food']
    response=client.get('/health/services',headers=HEADERS).json()
    assert response['services']['chat']['status']==status
    assert response['services']['vision']['available'] is True
    assert response['status']==('error' if failed else 'ready')
