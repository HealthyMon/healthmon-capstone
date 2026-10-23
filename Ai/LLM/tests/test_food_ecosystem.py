"""Real PostgreSQL with controlled Vision/LLM failures; real model checks are separate."""
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from src import app as module
from src import food
from src.db import connect


def auth(index=0):
    return {'Authorization': 'Bearer ' + list(json.loads(os.environ['DEV_TOKENS']))[index]}


@pytest.fixture
def client(monkeypatch):
    def analyze(path):
        assert path.is_file()
        return {'backend': 'controlled-vision', 'candidates': [
            {'food': '검증용 음식', 'confidence': .8, 'per_100g': {'energy_kcal': 200, 'protein_g': None}, 'estimated_grams': 150}]}
    monkeypatch.setattr(food.vision_service, 'analyze', analyze)
    return TestClient(module.app)


def pet(client):
    return client.post('/pets', json={}, headers=auth()).json()['pet_id']


def analyze(client, ident):
    return client.post(f'/pets/{ident}/food/analyze', content=b'\xff\xd8\xffexample', headers=auth())


def confirm(client, ident, analysis, **kwargs):
    return client.post(f'/pets/{ident}/food/confirm', json={'analysis_id': analysis, 'candidate_id': 0, **kwargs}, headers=auth())


def test_photo_is_not_consumption(client):
    ident = pet(client)
    result = analyze(client, ident)
    assert result.status_code == 200, result.text
    assert not result.json()['consumption_confirmed']
    assert client.get(f'/pets/{ident}/food/records', headers=auth()).json()['records'] == []
    assert client.get(f'/pets/{ident}/state', headers=auth()).json()['state_version'] == 0


def test_confirmation_idempotent_and_nutrients_not_invented(client):
    ident = pet(client); scan = analyze(client, ident).json()['analysis_id']
    first = confirm(client, ident, scan, grams=150)
    assert first.status_code == 200, first.text
    result = first.json()
    assert result['record']['nutrition']['energy_kcal'] == {'available': True, 'value': 300}
    assert result['record']['nutrition']['protein_g'] == {'available': False, 'value': 0}
    second = confirm(client, ident, scan, grams=150).json()
    assert second['duplicate'] and second['state_version'] == result['state_version'] == 1
    assert len(client.get(f'/pets/{ident}/food/records', headers=auth()).json()['records']) == 1
    with connect() as c:
        source = c.execute('SELECT payload FROM sources WHERE pet_id=%s', (ident,)).fetchone()['payload']
    assert source['source'] == 'user' and source['confirmed'] and source['kind'] == 'food'


def test_quantity_unknown_keeps_portion_unknown(client):
    ident = pet(client); scan = analyze(client, ident).json()['analysis_id']
    result = confirm(client, ident, scan).json()['record']
    assert result['grams'] is None and not result['nutrition']['energy_kcal']['available']


def test_no_cross_account_or_cross_pet_access(client):
    ident = pet(client); other = pet(client); scan = analyze(client, ident).json()['analysis_id']
    assert client.post(f'/pets/{ident}/food/analyze', content=b'\xff\xd8\xff', headers=auth(1)).status_code == 404
    assert client.get(f'/pets/{ident}/food/records', headers=auth(1)).status_code == 404
    assert confirm(client, other, scan).status_code == 404
    assert client.post(f'/pets/{ident}/food/confirm', json={'analysis_id':scan,'candidate_id':0}, headers=auth(1)).status_code == 404
    assert client.get('/ecosystem/health').status_code == 401


def test_changed_confirmation_rejected(client):
    ident = pet(client); scan = analyze(client, ident).json()['analysis_id']
    assert confirm(client, ident, scan, grams=100).status_code == 200
    assert confirm(client, ident, scan, grams=200).status_code == 409


def test_parallel_confirmation_creates_one_record(client):
    ident = pet(client); scan = analyze(client, ident).json()['analysis_id']
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: confirm(client, ident, scan, grams=100), range(2)))
    assert all(result.status_code == 200 for result in results)
    assert sorted(result.json()['duplicate'] for result in results) == [False, True]


@pytest.mark.parametrize('quantity', [0, -1, 10001])
def test_invalid_quantity(client, quantity):
    ident = pet(client); scan = analyze(client, ident).json()['analysis_id']
    assert confirm(client, ident, scan, grams=quantity).status_code == 422


def test_invalid_image_and_large_image(client):
    ident = pet(client)
    assert client.post(f'/pets/{ident}/food/analyze', content=b'bad', headers=auth()).status_code == 422
    assert client.post(f'/pets/{ident}/food/analyze', content=b'\xff\xd8\xff' + b'0' * food.MAX_IMAGE_BYTES, headers=auth()).status_code == 413


def test_model_failure_does_not_create_activity(client, monkeypatch):
    def fail(path):
        raise RuntimeError('Controlled model unavailable')
    monkeypatch.setattr(food.vision_service, 'analyze', fail)
    ident = pet(client)
    assert analyze(client, ident).status_code == 503
    assert client.get(f'/pets/{ident}/state', headers=auth()).json()['state_version'] == 0


def test_deleted_record_cannot_be_resurrected_by_retry(client):
    ident = pet(client); scan = analyze(client, ident).json()['analysis_id']
    saved = confirm(client, ident, scan).json()
    assert client.delete(f'/pets/{ident}/sources/{saved["source_id"]}', params={'expected_revision':1}, headers=auth()).status_code == 200
    assert confirm(client, ident, scan).status_code == 410
    assert client.get(f'/pets/{ident}/food/records', headers=auth()).json()['records'] == []


def test_food_enters_same_llm_context_and_updates_shared_version(client, monkeypatch):
    contexts = []
    class Model:
        def generate(self, context, text, repair=None):
            contexts.append(context)
            return json.dumps({'speech':'음식 기록을 봤어. 잘 먹었다니 좋네.','emotion':'happy','animation':'cheer',
                               'action':{'type':'none','target_id':None},'memory_ids':[],'personality_update':None})
    monkeypatch.setattr(module, 'backend', Model())
    def unnecessary_embedding(text):
        pytest.fail('Food facts are already in context; BGE must not load')
    monkeypatch.setattr(module, 'vectorize', unnecessary_embedding)
    ident = pet(client); scan = analyze(client, ident).json()['analysis_id']
    saved = confirm(client, ident, scan, grams=100).json()
    response = client.post(f'/pets/{ident}/chat', json={'request_id':uuid.uuid4().hex,'text':'음식 기록 봤어?', 'state_version': saved['state_version']}, headers=auth())
    assert response.status_code == 200, response.text
    assert not response.json()['metrics']['fallback']
    assert contexts[0]['activities'][-1]['food_record']['food'] == '검증용 음식'
    assert response.json()['state_version'] > saved['state_version']
