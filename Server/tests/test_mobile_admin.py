from dataclasses import replace

from fastapi.testclient import TestClient

from Server.healthmon.app import create_app


def values(**changes):
    body = dict(level=10, coin=200, upper_body=75, lower_body=25, nutrition=65,
                energy_balance=-20, activity=80, affinity=20, initiative=70)
    return dict(body, **changes)


def test_test_state_persists_and_clear_restores_record_based_state(client, pet):
    before = client.get(f'/pets/{pet}/state').json()
    changed = client.put(f'/pets/{pet}/test-controls/state', json=values())
    assert changed.status_code == 200, changed.text
    state = changed.json()
    assert state['level'] == 10 and state['coin'] == 200 and state['evolution_target_stage'] == 1
    assert state['synthetic_test_state'] and state['affinity'] == 20
    assert state['model_reference'] == before['model_reference']
    refreshed = client.get(f'/pets/{pet}/state').json()
    assert refreshed['state_version'] == state['state_version']
    assert all(refreshed[key] == value for key, value in values().items())
    restored = client.delete(f'/pets/{pet}/test-controls/state')
    assert restored.status_code == 200
    assert restored.json()['total_exp'] == before['total_exp']
    assert restored.json()['affinity'] == before['affinity']
    assert '_test_controls' not in restored.json()


def test_controls_reject_non_test_environment_or_unprovisioned_owner(settings, db):
    for config in (replace(settings, environment='development'), replace(settings, test_owners=frozenset())):
        # Do not start a mismatched development database lifespan: permission is
        # rejected before the endpoint attempts a database operation.
        api = TestClient(create_app(config, db))
        api.headers['Authorization'] = 'Bearer test-owner-a-token'
        assert api.put('/pets/not-owned/test-controls/state', json=values()).status_code == 403
        assert api.post('/pets/not-owned/test-controls/workout', json={'request_id':'control-workout', 'exercise':'walking', 'actual':3000}).status_code == 403


def test_test_controls_enforce_ownership_and_bounded_values(client, pet):
    response = client.put(f'/pets/{pet}/test-controls/state', json=values(), headers={'Authorization':'Bearer test-owner-b-token'})
    assert response.status_code == 404
    for invalid in (values(level=0), values(affinity=101), values(energy_balance=-101)):
        assert client.put(f'/pets/{pet}/test-controls/state', json=invalid).status_code == 422
    assert client.get('/identity').json()['test_controls_available'] is True


def test_workout_and_quest_controls_use_real_reconciliation_without_duplicate_reward(client, pet, db):
    path = f'/pets/{pet}/test-controls'
    response = client.put(path + '/quests', json={'slot':'easy', 'candidate':'workout1'})
    assert response.status_code == 200, response.text
    body = {'request_id':'mobile-workout-once', 'exercise':'walking', 'actual':6000}
    first = client.post(path + '/workout', json=body)
    assert first.status_code == 200, first.text
    again = client.post(path + '/workout', json=body)
    assert again.status_code == 200 and again.json()['total_exp'] == first.json()['total_exp']
    assert client.put(path + '/quests', json={'slot':'easy', 'candidate':'workout1'}).status_code == 200
    assert client.get(f'/pets/{pet}/state').json()['total_exp'] == first.json()['total_exp']
    with db.connect() as c:
        rows = c.execute("SELECT synthetic FROM sources WHERE pet_id=%s AND id='admin-workout-mobile-workout-once'", (pet,)).fetchall()
        assert rows == [{'synthetic': True}]
    assert client.put(path + '/quests', json={'slot':'easy', 'candidate':'daily6'}).status_code == 422
