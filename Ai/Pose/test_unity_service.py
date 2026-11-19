import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from Ai.Pose.unity_service import create_app


class EmptyModels:
    fallback_generation = 0
    fallback_reason = None
    providers = {"pose": ["CPUExecutionProvider"], "detector": ["CPUExecutionProvider"]}
    calls = 0
    def detect(self, image):
        self.calls += 1
        return np.empty((0, 4), np.float32)
    def estimate(self, image, box):
        raise AssertionError('An empty scene must never request pose estimation')


@pytest.fixture
def fixture():
    models = EmptyModels()
    client = TestClient(create_app(models))
    sid = client.post('/sessions', json={'exercise': 'squat'}).json()['session_id']
    ok, jpeg = cv2.imencode('.jpg', np.zeros((120, 160, 3), np.uint8))
    assert ok
    return client, sid, jpeg.tobytes(), models


def send(client, sid, data, seq=1, timestamp=0):
    return client.post(f'/sessions/{sid}/frames?sequence={seq}&timestamp={timestamp}',
                       content=data, headers={'content-type': 'image/jpeg'})


def test_empty_scene_never_fabricates_count(fixture):
    client, sid, data, _ = fixture
    result = send(client, sid, data).json()
    assert result['count'] == 0 and not result['tracked']
    assert result['jpeg_base64'] and result['session_id'] == sid


def test_frame_retry_is_idempotent_and_stale_frame_rejected(fixture):
    client, sid, data, models = fixture
    first = send(client, sid, data)
    calls = models.calls
    assert send(client, sid, data).json() == first.json()
    assert models.calls == calls
    assert send(client, sid, data, 1, .1).status_code == 409
    assert send(client, sid, data, 2, 0).status_code == 409


def test_pause_resume_and_finish_release_session(fixture):
    client, sid, data, _ = fixture
    assert send(client, sid, data).status_code == 200
    pause = client.post(f'/sessions/{sid}/control', json={'command': 'pause', 'paused': True})
    assert pause.json()['paused']
    assert send(client, sid, data, 2, .2).json()['count'] == 0
    resume = client.post(f'/sessions/{sid}/control', json={'command': 'pause', 'paused': False})
    assert not resume.json()['paused']
    result = client.delete(f'/sessions/{sid}').json()
    assert client.delete(f'/sessions/{sid}').json() == result
    assert send(client, sid, data, 3, .3).status_code == 404
    assert client.get('/health').json()['active_sessions'] == 0


def test_invalid_frames_and_foreign_browser_origin(fixture):
    client, sid, data, _ = fixture
    assert send(client, sid, b'not jpeg').status_code == 422
    assert send(client, sid, data, 0).status_code == 422
    assert send(client, sid, data, 1, float('nan')).status_code == 422
    assert send(client, sid, b'a' * (2 * 1024 * 1024 + 1)).status_code == 413
    assert client.post('/sessions', json={'exercise': 'invented'}).status_code == 422
    assert client.post('/sessions', json={'exercise': 'curl'}, headers={'origin': 'https://example.com'}).status_code == 403
    assert client.get('/health', headers={'host': 'foreign.example'}).status_code == 403


def test_sessions_do_not_share_counters_and_capacity(fixture):
    client, sid, data, _ = fixture
    other = client.post('/sessions', json={'exercise': 'curl'}).json()
    assert other['session_id'] != sid and other['left_count'] == other['right_count'] == 0
    for _ in range(2): assert client.post('/sessions', json={'exercise': 'pushup'}).status_code == 200
    assert client.post('/sessions', json={'exercise': 'squat'}).status_code == 409
    client.delete(f'/sessions/{sid}')
    assert client.post('/sessions', json={'exercise': 'squat'}).status_code == 200
