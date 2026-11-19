"""Live HTTP availability is independent from API/DB readiness and AI output."""
from dataclasses import replace
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

from fastapi.testclient import TestClient
import httpx
import pytest

from Server.healthmon.app import create_app
from Server.healthmon.config import Settings
from Server.healthmon.dependencies import AIDependencies


def settings(**kwargs):
    return Settings(database_url='postgresql://unused', environment='test', worker_enabled=False,
                    token_hashes={hashlib.sha256(b'fixture').hexdigest(): 'owner'},
                    test_owners=frozenset({'owner'}), **kwargs)


def test_offline_backend_is_ready_and_mock_availability_is_owner_scoped():
    class Database:
        def ready(self):
            return {'environment': 'test', 'instance_id': 'isolated-fixture'}
    config = settings()
    with TestClient(create_app(config, Database())) as client:
        assert client.get('/health/ready').json()['ready'] is True
        assert client.get('/health/dependencies').status_code == 401
        response = client.get('/health/dependencies', headers={'Authorization': 'Bearer fixture'}).json()
        assert response['ai'] == {'available': False, 'status': 'disabled'}
    monitor = AIDependencies(replace(config, ai_mode='mock'))
    assert monitor.snapshot('owner')['status'] == 'synthetic'
    assert monitor.snapshot('another-owner')['available'] is False


def test_same_backend_observes_ai_off_on_off_on_without_restart():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_GET(self):
            assert self.path == '/health/services'
            assert self.headers['Authorization'] == 'Bearer private-fixture'
            body = {'status': 'ready', 'services': {name: {'status': 'ready', 'available': True}
                    for name in ('chat', 'vision', 'evolution')}}
            content = json.dumps(body).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    # Bind a dedicated ephemeral port; never use the developer's actual AI port.
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    port = server.server_port
    server.server_close()
    monitor = AIDependencies(settings(ai_mode='remote', ai_base_url=f'http://127.0.0.1:{port}',
                                      ai_token='private-fixture', allow_http_ai=True))
    assert monitor.snapshot('owner')['status'] == 'off'
    for _ in range(2):
        server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        thread.start()
        try:
            monitor._expires = 0
            result = monitor.snapshot('owner')
            assert result['status'] == 'ready' and result['available'] is True
            assert 'private-fixture' not in json.dumps(result)
            assert monitor.settings._chat_evidence is None
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        # Cached readiness is bounded; a subsequent observation sees stopped AI.
        assert monitor.snapshot('owner') is result
        monitor._expires = 0
        assert monitor.snapshot('owner')['status'] == 'off'


@pytest.mark.parametrize('status,body,expected', [(404, {}, 'unknown'), (401, {}, 'error'),
    (200, {'status': 'ready', 'services': {}}, 'error'), (200, [], 'error')])
def test_unknown_or_invalid_health_cannot_report_ready(monkeypatch, status, body, expected):
    original = httpx.Client
    transport = httpx.MockTransport(lambda _: httpx.Response(status, json=body))
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: original(transport=transport, **kwargs))
    monitor = AIDependencies(settings(ai_mode='remote', ai_base_url='http://fixture.invalid',
                                      ai_token='private-fixture', allow_http_ai=True))
    result = monitor.snapshot('owner')
    assert result['status'] == expected and result['available'] is not True
