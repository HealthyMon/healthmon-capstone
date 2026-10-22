"""Explicit fictional consumption remains distinct from a real Vision envelope.

The controlled gateway below does not execute a Vision model. Real CPU Vision
and native Unity evidence are recorded independently by acceptance tooling.
"""
import pytest
from psycopg.types.json import Jsonb


def prepare_analysis(client, pet, settings, monkeypatch, ident, provenance='real'):
    settings.ai_mode = 'remote'
    food = {'candidates': [{'food': 'controlled food fixture', 'confidence': .9,
        'per_100g': {'energy_kcal': 150., 'carbohydrate_g': 30., 'protein_g': 3.,
                     'fat_g': 2., 'vegetable_fruit_g': None}, 'estimated_grams': 75.}]}
    monkeypatch.setattr('Server.healthmon.app.Gateway.call', lambda *args, **kwargs: (food, provenance))
    response = client.post(f'/pets/{pet}/food/analyze', content=b'\x89PNG\r\n\x1a\ncontrolled-http-image-fixture',
        headers={'X-Request-Id': ident, 'Content-Type': 'image/png'})
    assert response.status_code == 200, response.text
    assert response.json()['synthetic'] is (provenance == 'synthetic')
    return {'analysis_id': ident, 'candidate_id': 0, 'grams': 100.,
            'meal_type': 'breakfast', 'vegetable_fruit_g': 80., 'kcal_reconfirmed': False}


def test_explicit_fictional_consumption_does_not_label_real_vision_as_real_food(client, pet, settings, db, monkeypatch):
    body = prepare_analysis(client, pet, settings, monkeypatch, 'real-vision-fixture-consumption')
    body['synthetic'] = True
    first = client.post(f'/pets/{pet}/food/confirm', json=body)
    assert first.status_code == 200, first.text
    result = first.json()
    assert result['record']['nutrition']['vegetable_fruit_g'] == {'available': True, 'value': 80.}
    records = client.get(f'/pets/{pet}/meals').json()['records']
    assert len(records) == 1 and records[0]['synthetic'] is True
    assert records[0]['record']['vegetable_fruit_g'] == 80
    assert records[0]['record']['quantity_confirmed'] is True
    assert records[0]['record']['kcal_reconfirmed'] is False
    duplicate = client.post(f'/pets/{pet}/food/confirm', json=body)
    assert duplicate.status_code == 200 and duplicate.json()['duplicate'] is True
    assert duplicate.json()['state']['total_exp'] == result['state']['total_exp']
    with db.connect() as c:
        analysis = c.execute('SELECT result FROM food_analyses WHERE id=%s', (body['analysis_id'],)).fetchone()['result']
        assert analysis['provenance'] == 'real' and analysis['synthetic'] is False


@pytest.mark.parametrize('boundary', ['environment', 'owner'])
def test_fictional_confirmation_requires_existing_test_event_boundary(client, pet, settings, db, monkeypatch, boundary):
    body = prepare_analysis(client, pet, settings, monkeypatch, 'fixture-consumption-guard-' + boundary)
    body['synthetic'] = True
    if boundary == 'environment':
        settings.environment = 'production'
    else:
        settings.test_owners = frozenset()
    response = client.post(f'/pets/{pet}/food/confirm', json=body)
    assert response.status_code == 403
    assert client.get(f'/pets/{pet}/meals').json()['records'] == []
    with db.connect() as c:
        assert c.execute('SELECT confirmation FROM food_analyses WHERE id=%s', (body['analysis_id'],)).fetchone()['confirmation'] is None


def test_synthetic_analysis_cannot_be_unmarked_by_confirmation(client, pet, settings, monkeypatch):
    body = prepare_analysis(client, pet, settings, monkeypatch, 'synthetic-analysis-stays-synthetic', provenance='synthetic')
    body['synthetic'] = False
    response = client.post(f'/pets/{pet}/food/confirm', json=body)
    assert response.status_code == 200, response.text
    assert client.get(f'/pets/{pet}/meals').json()['records'][0]['synthetic'] is True


def test_earlier_confirmation_without_optional_flag_retries_unchanged(client, pet, settings, db, monkeypatch):
    body = prepare_analysis(client, pet, settings, monkeypatch, 'legacy-confirmation-default-compatible')
    first = client.post(f'/pets/{pet}/food/confirm', json=body)
    assert first.status_code == 200, first.text
    with db.connect() as c:
        row = c.execute('SELECT confirmation FROM food_analyses WHERE id=%s', (body['analysis_id'],)).fetchone()
        confirmation = row['confirmation']
        assert confirmation['input'].pop('synthetic') is False
        c.execute('UPDATE food_analyses SET confirmation=%s WHERE id=%s', (Jsonb(confirmation), body['analysis_id']))
    repeated = client.post(f'/pets/{pet}/food/confirm', json=body)
    assert repeated.status_code == 200 and repeated.json()['duplicate'] is True
    assert repeated.json()['state']['total_exp'] == first.json()['state']['total_exp']
    assert client.get(f'/pets/{pet}/meals').json()['records'][0]['synthetic'] is False
    assert client.post(f'/pets/{pet}/food/confirm', json={**body, 'synthetic': True}).status_code == 409


@pytest.mark.parametrize('vegetable_fruit_g', [-1, 10000.01])
def test_confirmation_rejects_out_of_range_amount_before_meal_construction(client, pet, settings, monkeypatch, vegetable_fruit_g):
    body = prepare_analysis(client, pet, settings, monkeypatch, 'confirmed-vegetable-boundary')
    response = client.post(f'/pets/{pet}/food/confirm', json={**body, 'vegetable_fruit_g': vegetable_fruit_g})
    assert response.status_code == 422
    assert client.get(f'/pets/{pet}/meals').json()['records'] == []
