"""Signed quest execution contract with controlled fixtures, never Qwen/GPU.

The qwen origin in mocked responses exercises the execution gate only. These
fixtures do not establish actual model quality or create training examples.
"""
import copy
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from src.character_lab_api import session_digest, validate_offer_goal_numbers
from src.character_lab_engine import fresh
from src.character_lab_models import PersonaResponder, RESPONDER_VERSION, response_context
from src.character_lab_schema import canonical_json
from src.contracts import ModelOutput
from src.persona_lab import create_app
from src.persona_runtime import PersonaRuntime, persona_messages
from src.persona_store import LabStore


ORIGIN = 'http://127.0.0.1:8001'
HEADERS = {'Origin': ORIGIN, 'X-Persona-Lab': '1'}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('PERSONA_LAB_ENABLED', '1')
    monkeypatch.delenv('ENVIRONMENT', raising=False)
    monkeypatch.delenv('NODE_ENV', raising=False)
    import src.db
    monkeypatch.setattr(src.db, 'connect', lambda: pytest.fail('No production PostgreSQL access'))
    runtime = PersonaRuntime()
    monkeypatch.setattr(runtime, '_load', lambda: pytest.fail('No model/GPU loading'))
    flags = {'action': 'offer_quest', 'origin': 'qwen', 'fallback': False, 'candidate': 'walk_100', 'speech': None}

    def controlled_compare(self, session, a, b, text, memory, generation, mode, speech_level):
        contexts = {side: response_context(session, state, text, memory, speech_level)
                    for side, state in (('a', a), ('b', b))}
        row = {'index': 0, 'seed': generation['seed']}
        for side, context in contexts.items():
            candidate = next((q for q in context['candidates'] if q['quest_id'] == flags['candidate']), None)
            action = flags['action'] if candidate else 'none'
            speech = flags['speech'] or ('가볍게 100걸음 걸어볼까?' if speech_level == 'casual' else '가볍게 100걸음 걸어볼까요?')
            contract = ModelOutput(speech=speech, emotion='encouraging', animation='encourage',
                                   action={'type': action, 'target_id': candidate['id'] if action == 'offer_quest' else None},
                                   memory_ids=[]).model_dump()
            row[side] = {'output': contract, 'output_origin': 'dummy' if mode == 'dummy' else flags['origin'],
                         'metrics': {'fallback': flags['fallback']},
                         'raw_attempts': [{'raw': json.dumps(contract, ensure_ascii=False), 'fixture': True}]}
        return {'mode': mode, 'adapter': 'CONTROLLED-UNIT-FIXTURE-NOT-QWEN', 'contexts': contexts,
                'results': [row], 'prompts': {side: persona_messages(context, text) for side, context in contexts.items()},
                'generation': generation, 'prompt_version': RESPONDER_VERSION}

    monkeypatch.setattr(PersonaResponder, 'compare', controlled_compare)
    app = create_app(runtime, LabStore(tmp_path / 'only-test.sqlite3'))
    with TestClient(app, base_url=ORIGIN, client=('127.0.0.1', 30000)) as c:
        yield c, app.state.character_lab_store, flags


def post(c, path, body, expected=200):
    r = c.post('/dev/character-lab' + path, json=body, headers=HEADERS)
    assert r.status_code == expected, r.text
    return r.json()


def state(c):
    session = c.get('/dev/character-lab/state').json()['session']
    # The existing selector prefers the together walking candidate at this
    # explicitly synthetic Affinity, without modifying the original catalog.
    session['state']['affection'] = 80
    return session


def bundle(c, session, **extra):
    r = post(c, '/conversation/respond', {'text': '오늘 걷기 퀘스트를 제안해 줘',
                                         'session': session, 'mode': 'qwen', **extra})
    return r['reviews']['a']


def test_signed_offer_creates_exact_catalog_quest_without_acceptance_or_reward(client):
    c, store, _ = client
    initial = state(c)
    offer = json.loads(canonical_json(bundle(c, initial)))  # Browser numeric round-trip.
    r = post(c, '/quest/offer', {**offer, 'event_id': 'offer-100', 'session': initial})
    ident = 'mini:walk_100:2026-10-04'
    q = r['session']['quests'][ident]
    assert r['execution'] == {'quest_instance_id': ident, 'catalog_id': 'walk_100', 'status': 'created'}
    assert r['command']['event_id'] == 'offer-100'
    assert r['command']['payload']['quest_id'] == ident
    assert (q['target'], q['target_value'], q['unit']) == ('walk', 100, 'step')
    assert q['status'] == 'created' and not q['reward_paid']
    assert r['after']['exp'] == initial['state']['exp']
    view = next(x for x in r['quests'] if x['quest_id'] == ident)
    assert view['can_accept'] and not view['can_complete']
    assert not store.path.exists()
    # Replaying a bundle against changed state/history cannot create a second quest.
    post(c, '/quest/offer', {**offer, 'event_id': 'offer-again', 'session': r['session']}, 409)


@pytest.mark.parametrize('action,origin,fallback', [
    ('none', 'qwen', False), ('offer_quest', 'dummy', False),
    ('offer_quest', 'fallback', True), ('offer_quest', 'invalid', False),
])
def test_only_valid_structured_real_model_offer_executes(client, action, origin, fallback):
    c, store, flags = client
    flags.update(action=action, origin=origin, fallback=fallback)
    initial = state(c)
    offer = bundle(c, initial)
    post(c, '/quest/offer', {**offer, 'event_id': 'blocked', 'session': initial}, 422)
    assert not store.path.exists()


@pytest.mark.parametrize('speech,expected', [
    ('가볍게 100걸음 걸어볼까?', 200), ('같이 100보 걸어볼래?', 200),
    ('가볍게 100.0걸음 걸어볼까?', 200),
    ('가볍게 산책부터 시작해 볼까?', 200),
    ('가볍게 500걸음 걸어볼까?', 422), ('함께 2분 스트레칭 해볼까?', 422),
    ('오늘 2000보를 걸었다면 이제 100걸음 걸어보자.', 422),
    ('100걸음 또는 500걸음 산책은 어때?', 422),
    ('함께 1,000보 산책은 어때?', 422),
])
def test_spoken_recommendation_quantities_must_match_authorized_goal(client, speech, expected):
    c, store, flags = client
    flags['speech'] = speech
    initial = state(c)
    offer = bundle(c, initial)
    r = post(c, '/quest/offer', {**offer, 'event_id': 'numbers', 'session': initial}, expected)
    if expected == 422:
        assert '대사의 걸음 수·시간' in r['detail']
        assert not store.path.exists()
    else:
        assert r['session']['quests']['mini:walk_100:2026-10-04']['target_value'] == 100


def test_step_prose_cannot_promote_authorized_stretch_action(client):
    c, store, flags = client
    initial = c.get('/dev/character-lab/state').json()['session']
    # Default Affinity deterministically selects the original stretch_2 goal.
    flags.update(candidate='stretch_2', speech='같이 100걸음 걸어볼까?')
    offer = bundle(c, initial)
    assert offer['draft']['response_contract']['action']['target_id'] == 'stretch_2'
    r = post(c, '/quest/offer', {**offer, 'event_id': 'wrong-unit', 'session': initial}, 422)
    assert '대사의 걸음 수·시간' in r['detail'] and not store.path.exists()
    flags['speech'] = '함께 2분 스트레칭 해볼까?'
    offer = bundle(c, initial)
    r = post(c, '/quest/offer', {**offer, 'event_id': 'right-unit', 'session': initial})
    assert r['session']['quests']['mini:stretch_2:2026-10-04']['target_value'] == 2


def test_numeric_guard_does_not_interpret_status_text_as_a_recommendation():
    # A quantity appearing in a status sentence is not sufficient to infer a
    # proposed quest. Action authorization remains a separate mandatory gate.
    candidate = {'goal': {'target': 100, 'unit': 'steps'}}
    assert validate_offer_goal_numbers('현재 기록은 500보야.', candidate) is None


@pytest.mark.parametrize('changed', ['target', 'goal', 'state', 'version', 'signature'])
def test_tampered_offer_metadata_fails_signature(client, changed):
    c, store, _ = client
    initial = state(c)
    offer = copy.deepcopy(bundle(c, initial))
    if changed == 'target':
        offer['draft']['response_contract']['action']['target_id'] = 'invented_999'
    elif changed == 'goal':
        offer['draft']['quest_context']['candidates'][0]['goal']['target'] = 999
    elif changed == 'state':
        offer['draft']['state']['activity'] = 99
    elif changed == 'version':
        offer['draft']['rule_version'] = 'other'
    else:
        offer['signature'] = '0' * 64
    post(c, '/quest/offer', {**offer, 'event_id': 'tampered', 'session': initial}, 422)
    assert not store.path.exists()


def test_offer_bound_to_state_date_and_complete_evidence(client):
    c, store, _ = client
    initial = state(c)
    offer = bundle(c, initial)
    for field in ('state', 'date', 'history'):
        altered = copy.deepcopy(initial)
        if field == 'state':
            altered['state']['activity'] += 1
        elif field == 'date':
            altered['state']['virtual_test_date'] = '2026-10-05'
        else:
            # Attack keeps processed fingerprints unchanged while forging history.
            altered['events'].append({'event_id': 'forged', 'kind': 'exercise',
                                      'virtual_test_date': '2026-10-04',
                                      'payload': {'actual': 100}, 'result': {'verified_behavior': True}})
        post(c, '/quest/offer', {**offer, 'event_id': field, 'session': altered}, 409)
    assert not store.path.exists()


def test_hypothetical_ab_state_must_be_applied_first(client):
    c, store, _ = client
    initial = state(c)
    offer = bundle(c, initial, a={**initial['state'], 'activity': 85, 'initiative': 80})
    post(c, '/quest/offer', {**offer, 'event_id': 'hypothetical', 'session': initial}, 409)
    assert not store.path.exists()


def test_offer_commit_requires_test_namespace_current_revision_and_no_posted_snapshot(client):
    c, store, _ = client
    saved = post(c, '/sessions', {'affection': 80})
    initial = saved['session']
    offer = bundle(c, initial)
    digest = hashlib.sha256(store.path.read_bytes()).hexdigest()
    preview = post(c, '/quest/offer', {**offer, 'event_id': 'saved-offer', 'session_id': saved['session_id']})
    assert preview['dry_run'] and hashlib.sha256(store.path.read_bytes()).hexdigest() == digest
    post(c, '/quest/offer', {**offer, 'event_id': 'saved-offer', 'session_id': saved['session_id'],
                           'expected_revision': 99, 'dry_run': False}, 409)
    post(c, '/quest/offer', {**offer, 'event_id': 'saved-offer', 'session_id': saved['session_id'],
                           'dry_run': False}, 422)
    post(c, '/quest/offer', {**offer, 'event_id': 'saved-offer', 'session_id': saved['session_id'],
                           'session': initial, 'expected_revision': 0, 'dry_run': False}, 422)
    post(c, '/quest/offer', {**offer, 'event_id': 'saved-offer', 'session_id': 'real-character',
                           'expected_revision': 0, 'dry_run': False}, 422)
    r = post(c, '/quest/offer', {**offer, 'event_id': 'saved-offer', 'session_id': saved['session_id'],
                               'expected_revision': 0, 'dry_run': False})
    assert not r['dry_run'] and r['revision'] == 1
    persisted = store.read(saved['session_id'])['session']
    assert persisted['quests']['mini:walk_100:2026-10-04']['status'] == 'created'
    post(c, '/quest/offer', {**offer, 'event_id': 'saved-offer', 'session_id': saved['session_id'],
                           'expected_revision': 0, 'dry_run': False}, 409)
    assert store.read(saved['session_id'])['revision'] == 1


def test_session_digest_excludes_audit_logs_but_includes_evidence():
    initial = fresh()
    altered = copy.deepcopy(initial)
    altered['logs'].append({'timestamp': 'different', 'dry_run': False})
    assert session_digest(initial) == session_digest(altered)
    altered['events'].append({'event_id': 'different'})
    assert session_digest(initial) != session_digest(altered)


def test_quest_tick_route_preserves_preview_isolation_and_command_type(client):
    c, store, _ = client
    initial = state(c)
    r = post(c, '/quest/tick', {'session': initial, 'commands': [
        {'kind': 'quest_tick', 'event_id': 'daily-tick', 'payload': {}}]})
    assert 'daily:walk_6000:2026-10-04' in r['session']['quests']
    assert not store.path.exists()
    post(c, '/quest/tick', {'session': initial, 'commands': [
        {'kind': 'exercise', 'event_id': 'wrong-route', 'payload': {'actual': 50, 'target': 50}}]}, 422)
