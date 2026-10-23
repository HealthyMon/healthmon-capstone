from datetime import timedelta
from fastapi.testclient import TestClient
from Server.healthmon.app import create_app


def test_postgres_smoke_duplicate_and_api_restart(client, pet, db, settings):
    initial = client.get(f'/pets/{pet}/state').json()
    assert initial['lower_body'] == 50
    start = client.app.state.clock()
    finish = start + timedelta(minutes=31)
    client.app.state.clock = lambda: finish
    event = {'event_id': 'synthetic-smoke-run', 'occurred_at': finish.isoformat(), 'started_at': start.isoformat(),
             'workout_type': 'running', 'actual': 30, 'unit': 'minutes', 'target': 30, 'synthetic': True}
    response = client.post(f'/pets/{pet}/workouts', json=event)
    assert response.status_code == 200, response.text
    first = response.json()
    assert first['state']['lower_body'] == 52
    duplicate = client.post(f'/pets/{pet}/workouts', json=event)
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()['duplicate'] is True
    assert duplicate.json()['state']['lower_body'] == 52
    assert duplicate.json()['state']['total_exp'] == first['state']['total_exp']
    application = create_app(settings, db)
    application.state.clock = lambda: finish
    with TestClient(application) as restarted:
        state = restarted.get(f'/pets/{pet}/state', headers={'Authorization': 'Bearer test-owner-a-token'}).json()
        assert state['lower_body'] == 52
        assert state['total_exp'] == first['state']['total_exp']
    assert len(client.get(f'/pets/{pet}/workouts').json()['records']) == 1
    db.migrate()
    assert db.ready()['environment'] == 'test'


def test_db_environment_and_ownership(client, pet, settings, db):
    from dataclasses import replace
    from Server.healthmon.db import Database
    import pytest
    with pytest.raises(RuntimeError):
        Database(replace(settings, environment='development')).ready()
    assert client.get(f'/pets/{pet}/state', headers={'Authorization': 'Bearer test-owner-b-token'}).status_code == 404
    assert client.get(f'/pets/{pet}/state', headers={'Authorization': ''}).status_code == 401


def test_disabled_ai_never_blocks_state(client, pet):
    assert client.post(f'/pets/{pet}/chat', json={'request_id': 'disabled-request', 'text': '안녕'}).status_code == 503
    assert client.get(f'/pets/{pet}/state').status_code == 200
    assert client.get('/health/live').status_code == 200
    assert client.get('/health/ready').json()['ready'] is True
