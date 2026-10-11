"""API contracts and isolation, using explicitly dummy speech, never GPU quality scores."""
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from src.persona_lab import create_app
from src.persona_lifestyle import LIFESTYLE_PRESETS
from src.persona_runtime import PersonaRuntime
from src.persona_store import LabStore

ORIGIN = 'http://127.0.0.1:8001'
HEADERS = {'Origin': ORIGIN, 'X-Persona-Lab': '1'}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('PERSONA_LAB_ENABLED', '1')
    for key in ('ENVIRONMENT', 'NODE_ENV'):
        monkeypatch.delenv(key, raising=False)
    runtime = PersonaRuntime()
    monkeypatch.setattr(runtime, '_load', lambda: pytest.fail('No real model in dummy tests'))
    import src.db
    monkeypatch.setattr(src.db, 'connect', lambda: pytest.fail('No legacy database access'))
    store = LabStore(tmp_path / 'separate.sqlite3')
    app = create_app(runtime, store)
    with TestClient(app, base_url=ORIGIN, client=('127.0.0.1', 30000)) as c:
        yield c, store


def post(c, path, body):
    result = c.post(path, json=body, headers=HEADERS)
    assert result.status_code == 200, result.text
    return result.json()


@pytest.mark.parametrize('preset', list(LIFESTYLE_PRESETS))
def test_all_presets_deterministic_reconciled_capped_and_no_store(client, preset):
    c, store = client
    body = {'records': LIFESTYLE_PRESETS[preset]['input']}
    first = post(c, '/api/lifestyle/simulate', body)
    second = post(c, '/api/lifestyle/simulate', body)
    assert first == second
    assert not store.path.exists()
    assert first['dry_run'] and not first['database_write']
    assert len(first['timeline']) == first['days'] + 1
    assert not first['unapplied_events']
    for axis in first['ledger_summary']:
        assert axis['before'] + axis['total_delta'] == pytest.approx(axis['after'])
        assert axis['total_delta'] == pytest.approx(sum(row['final_delta'] for row in axis['reasons']))
    for row in first['caps']['daily_and_rolling_week']:
        assert row['positive'] <= 1.000001 and row['negative'] <= .500001
        assert row['rolling_7day_positive'] <= 3.000001 and row['rolling_7day_negative'] <= 1.000001


def test_compare_same_controls_memory_clock_and_dummy_provenance(client):
    c, store = client
    body = {'records': LIFESTYLE_PRESETS['steady_30']['input'], 'mode': 'dummy',
            'text': '오늘은 뭘 해볼까?', 'generation': {'seed': 729, 'temperature': .4},
            'memories': [{'id': 'm1', 'content': '짧은 스트레칭을 좋아해.', 'source_id': 'test-source'}]}
    result = post(c, '/api/lifestyle/compare', body)
    a, b = result['contexts']['a'], result['contexts']['b']
    assert a['memories'] == b['memories']
    assert a['as_of'] == b['as_of']
    assert a['personality'] != b['personality']
    assert result['results'][0]['seed'] == 729
    assert result['generation']['temperature'] == .4
    assert all(result['results'][0][side]['output_origin'] == 'dummy' for side in ('a','b'))
    assert json.loads(result['prompts']['a'][1]['content'])['user_text'] == body['text']
    assert json.loads(result['prompts']['b'][1]['content'])['user_text'] == body['text']
    assert result['comparison_observations']['requires_human_review']
    assert not store.path.exists()


def test_duplicates_unknown_unverified_visible_without_growth(client):
    c, _ = client
    basic = {'days': 7, 'exercise_sessions': 3, 'exercise_minutes': 30}
    first = post(c, '/api/lifestyle/simulate', {'records': basic})
    extra = dict(basic, duplicate_events=2, unverified_events=2, food_records=1, food_days=1, unknown_foods=1)
    after = post(c, '/api/lifestyle/simulate', {'records': extra})
    assert after['final']['personality'] == first['final']['personality']
    assert len(after['ignored_duplicates']) == 2
    assert len(after['unapplied_events']) == 3
    assert after['compiled']['nutrition'] == {'calories': 'unknown', 'nutrients': 'unknown'}


def test_existing_database_hash_preserved_and_commit_refused(client):
    c, store = client
    post(c, '/api/characters', {})
    before = hashlib.sha256(store.path.read_bytes()).hexdigest()
    post(c, '/api/lifestyle/simulate', {'records': LIFESTYLE_PRESETS['quest_success']['input']})
    post(c, '/api/lifestyle/compare', {'mode': 'dummy'})
    assert hashlib.sha256(store.path.read_bytes()).hexdigest() == before
    for extra in ({'commit': True}, {'character_id':'lab-existing'}):
        r = c.post('/api/lifestyle/simulate', json=extra, headers=HEADERS)
        assert r.status_code == 422


def test_invalid_calendar_counts_and_origin_rejected(client):
    c, store = client
    for body in ({'records': {'exercise_sessions': -1}}, {'start':'2026-10-01T12:00:00+09:00'},
                 {'start':'2026-10-01T00:00:00+00:00'}, {'records':{'calories':123}}):
        assert c.post('/api/lifestyle/simulate', json=body, headers=HEADERS).status_code == 422
    assert c.post('/api/lifestyle/simulate', json={}).status_code == 403
    assert not store.path.exists()


@pytest.mark.parametrize('path', ['/api/lifestyle/simulate', '/api/lifestyle/compare'])
def test_historical_initial_stages_are_rejected_instead_of_silently_reset(client, path):
    c, store = client
    body = {'initial': {'personality': {'activity': 58}, 'stages': {'activity': 'high'}}}
    if path.endswith('/compare'):
        body['mode'] = 'dummy'
    rejected = c.post(path, json=body, headers=HEADERS)
    assert rejected.status_code == 422
    assert 'initial.stages' in rejected.text
    body['initial']['stages'] = None
    accepted = post(c, path, body)
    state = accepted['initial'] if path.endswith('/simulate') else accepted['contexts']['a']
    assert state['personality']['activity'] == 58
    assert state['stages']['activity'] == 'medium'
    assert not store.path.exists()


@pytest.mark.parametrize('records', [
    {},
    {'days': 7, 'exercise_sessions': 3, 'exercise_minutes': 30, 'cardio_sessions': 3},
    {'days': 7, 'food_records': 3, 'food_days': 3},
])
def test_missing_pedometer_data_is_unknown_in_both_contexts_and_model_prompts(client, records):
    c, store = client
    result = post(c, '/api/lifestyle/compare', {'records': records, 'mode': 'dummy'})
    for side in ('a', 'b'):
        context = result['contexts'][side]
        prompt_context = json.loads(result['prompts'][side][1]['content'])['context']
        for period in ('requested_period', 'last_7_days'):
            summary = context['activity_summary'][period]
            assert summary['confirmed_steps'] == 'unknown'
            assert summary['step_measurement'] == 'not_provided'
            assert prompt_context['activity_summary'][period] == summary
        assert all('steps' not in row['payload'] for row in context['activities'])
    assert not store.path.exists()


def test_model_context_explicitly_distinguishes_assumed_dates_and_representative_activity_names(client):
    c, _ = client
    result = post(c, '/api/lifestyle/compare', {
        'records': {'days': 7, 'exercise_sessions': 3, 'exercise_minutes': 30, 'cardio_sessions': 3,
                    'food_records': 3, 'food_days': 3},
        'mode': 'dummy',
    })
    for side in ('a', 'b'):
        scope = result['contexts'][side]['record_scope']
        assert scope['kind'] == 'synthetic_lifestyle_dry_run'
        assert '가상' in scope['date_allocation'] and '단정하지' in scope['date_allocation']
        assert 'unknown' in scope['exercise_identity'] and '단정하지' in scope['exercise_identity']
        assert '가상' in scope['food_identity'] and 'unknown' in scope['food_identity']
        assert json.loads(result['prompts'][side][1]['content'])['context']['record_scope'] == scope
    exercises = [row for row in result['contexts']['b']['activities'] if row['event_type'] == 'exercise_recorded']
    assert exercises
    assert all(row['payload']['exercise_type'] == 'cycle' and row['payload']['actual_exercise_type'] == 'unknown'
               and row['source'] == 'simulation' for row in exercises)
