"""Immutable source provenance across revisions, using fresh isolated PG fixtures."""
import pytest


def snapshot(db, pet, ident):
    with db.connect() as connection:
        source = connection.execute('SELECT * FROM sources WHERE pet_id=%s AND id=%s', (pet, ident)).fetchone()
        revisions = connection.execute('SELECT * FROM source_revisions WHERE pet_id=%s AND source_id=%s ORDER BY revision', (pet, ident)).fetchall()
    return source, revisions


def assert_provenance(saved, expected, revision):
    source, revisions = saved
    assert source['synthetic'] is expected
    assert source['payload']['data']['synthetic'] is expected
    assert source['payload']['_raw']['synthetic'] is expected
    assert source['revision'] == revision
    assert len(revisions) == revision
    assert all(row['raw_payload']['synthetic'] is expected for row in revisions)


def workout(synthetic, revision=1):
    return {'event_id': 'immutable-workout-provenance', 'revision': revision,
            'occurred_at': '2026-10-22T03:00:00Z', 'workout_type': 'run',
            'actual': 30. + revision, 'unit': 'minutes', 'synthetic': synthetic}


@pytest.mark.parametrize('initial', [False, True])
def test_workout_revision_cannot_change_provenance_and_rolls_back_every_source_field(client, pet, db, initial):
    first = client.post(f'/pets/{pet}/workouts', json=workout(initial))
    assert first.status_code == 200, first.text
    before = snapshot(db, pet, workout(initial)['event_id'])
    assert_provenance(before, initial, 1)

    response = client.post(f'/pets/{pet}/workouts', json=workout(not initial, revision=2))
    assert response.status_code == 409, response.text
    assert 'provenance' in response.json()['detail']
    assert snapshot(db, pet, workout(initial)['event_id']) == before
    records = client.get(f'/pets/{pet}/workouts').json()['records']
    assert len(records) == 1 and records[0]['synthetic'] is initial


@pytest.mark.parametrize('synthetic', [False, True])
def test_workout_same_provenance_revision_and_retry_are_preserved(client, pet, db, synthetic):
    assert client.post(f'/pets/{pet}/workouts', json=workout(synthetic)).status_code == 200
    body = workout(synthetic, revision=2)
    revised = client.post(f'/pets/{pet}/workouts', json=body)
    assert revised.status_code == 200 and revised.json()['revision'] == 2, revised.text
    saved = snapshot(db, pet, body['event_id'])
    assert_provenance(saved, synthetic, 2)
    repeated = client.post(f'/pets/{pet}/workouts', json=body)
    assert repeated.status_code == 200 and repeated.json()['duplicate'] is True
    assert snapshot(db, pet, body['event_id']) == saved


def food_analysis(client, pet, settings, monkeypatch, ident):
    # Controlled real-provenance envelope for API semantics, no Vision inference.
    settings.ai_mode = 'remote'
    result = {'candidates': [{'food': 'controlled provenance meal fixture', 'confidence': .9,
        'per_100g': {'energy_kcal': 150., 'carbohydrate_g': 30., 'protein_g': 3.,
                     'fat_g': 2., 'vegetable_fruit_g': None}, 'estimated_grams': None}]}
    monkeypatch.setattr('Server.healthmon.app.Gateway.call', lambda *args, **kwargs: (result, 'real'))
    response = client.post(f'/pets/{pet}/food/analyze', content=b'\x89PNG\r\n\x1a\ncontrolled-provenance-image-fixture',
                           headers={'X-Request-Id': ident, 'Content-Type': 'image/png'})
    assert response.status_code == 200, response.text
    return response.json()['analysis_id']


def confirmation(analysis, synthetic, revision=1):
    return {'analysis_id': analysis, 'candidate_id': 0, 'revision': revision,
            'grams': 100. * revision, 'vegetable_fruit_g': 80.,
            'meal_type': 'breakfast', 'synthetic': synthetic}


@pytest.mark.parametrize('initial', [False, True])
def test_food_reanalysis_revision_cannot_change_provenance_or_commit_confirmation(client, pet, settings, db, monkeypatch, initial):
    first_id = food_analysis(client, pet, settings, monkeypatch, 'first-provenance-analysis')
    first = client.post(f'/pets/{pet}/food/confirm', json=confirmation(first_id, initial))
    assert first.status_code == 200, first.text
    source_id = first.json()['source_id']
    before = snapshot(db, pet, source_id)
    assert_provenance(before, initial, 1)
    second_id = food_analysis(client, pet, settings, monkeypatch, 'second-provenance-analysis')

    response = client.post(f'/pets/{pet}/food/confirm', json=confirmation(second_id, not initial, revision=2))
    assert response.status_code == 409, response.text
    assert 'provenance' in response.json()['detail']
    assert snapshot(db, pet, source_id) == before
    with db.connect() as connection:
        stored = connection.execute('SELECT confirmation FROM food_analyses WHERE id=%s', (second_id,)).fetchone()
        assert stored['confirmation'] is None
        original = connection.execute('SELECT confirmation FROM food_analyses WHERE id=%s', (first_id,)).fetchone()
        assert original['confirmation'] == first.json()
    records = client.get(f'/pets/{pet}/meals').json()['records']
    assert len(records) == 1 and records[0]['synthetic'] is initial


@pytest.mark.parametrize('synthetic', [False, True])
def test_food_same_provenance_reanalysis_revision_and_retry_are_preserved(client, pet, settings, db, monkeypatch, synthetic):
    first_id = food_analysis(client, pet, settings, monkeypatch, 'first-consistent-provenance-analysis')
    first = client.post(f'/pets/{pet}/food/confirm', json=confirmation(first_id, synthetic))
    assert first.status_code == 200, first.text
    second_id = food_analysis(client, pet, settings, monkeypatch, 'second-consistent-provenance-analysis')
    body = confirmation(second_id, synthetic, revision=2)
    revised = client.post(f'/pets/{pet}/food/confirm', json=body)
    assert revised.status_code == 200 and revised.json()['revision'] == 2, revised.text
    assert revised.json()['source_id'] == first.json()['source_id']
    saved = snapshot(db, pet, revised.json()['source_id'])
    assert_provenance(saved, synthetic, 2)
    repeated = client.post(f'/pets/{pet}/food/confirm', json=body)
    assert repeated.status_code == 200 and repeated.json()['duplicate'] is True
    assert snapshot(db, pet, revised.json()['source_id']) == saved
