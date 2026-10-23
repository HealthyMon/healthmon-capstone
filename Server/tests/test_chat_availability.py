"""Actual loopback HTTP evidence feeding PostgreSQL quest reconciliation.

These are controlled contract fixtures, not model/GPU inference. Each PostgreSQL
test uses the existing random isolated database fixture.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
import pytest

from Server.healthmon.app import create_app
from Server.healthmon.config import Settings
from Server.healthmon.contracts import PetSettings
from Server.healthmon.gateway import AIUnavailable, Gateway
from Server.healthmon import quests, rules, service, worker

BASE = datetime(2026, 10, 22, 3, tzinfo=timezone.utc)


@pytest.fixture
def controlled_ai():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            capability = self.path.split('/')[2]
            self.server.requests.append(capability)
            behavior = self.server.behavior.get(capability, 'success')
            status = 503 if behavior == '503' else 200
            if behavior == 'timeout':
                time.sleep(.15)
            result = {'speech': '실제 HTTP 계약 검증용 가명 대사입니다.', 'emotion': 'neutral', 'animation': 'idle',
                      'memory_ids': [], 'classification': {'target': 'other', 'sentiment': 'neutral',
                      'motivation': 'neutral', 'character_affection': 'neutral', 'acceptance': 'none', 'confidence': .8}}
            if capability == 'embedding':
                result = {'model_id': 'BAAI/bge-m3', 'model_version': '1', 'dimension': 1024, 'vector': [1.] + [0.] * 1023}
            elif capability == 'food':
                result = {'candidates': [{'food': '가명 음식', 'confidence': .8, 'per_100g': {}, 'estimated_grams': None}]}
            elif capability == 'evolutions':
                result = {'job_id': body['request_id'], 'stage': body['input']['stage'], 'status': 'queued'}
            if behavior == 'bad_result':
                result = {'speech': 'missing required fields'}
            elif behavior == 'bad_memory':
                result['memory_ids'] = ['not-in-authoritative-context']
            envelope = {'contract_version': 'wrong' if behavior == 'bad_contract' else 'healthmon.ai.v1',
                        'request_id': body['request_id'], 'provenance': 'synthetic' if behavior == 'synthetic' else 'real',
                        'result': result}
            raw = b'invalid JSON' if behavior == 'bad_json' else json.dumps(envelope).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        do_PUT = do_POST

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    server.behavior, server.requests = {}, []
    server.url = 'http://127.0.0.1:' + str(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def remote_settings(remote):
    return Settings(database_url='postgresql://unused/contract_fixture', environment='test', ai_mode='remote',
                    ai_base_url=remote.url, ai_token='isolated-contract-token', allow_http_ai=True,
                    test_owners=frozenset({'owner-a'}), ai_timeout=.5, worker_enabled=False)


def call(gateway, capability='chat', **kwargs):
    return gateway.call(capability, 'fixture-chat-request', 'fixture-pet', {'stage': 1},
                        'owner-a', True, **kwargs)


@pytest.mark.parametrize('behavior', ['503', 'timeout', 'bad_json', 'bad_contract', 'bad_result', 'bad_memory'])
def test_only_validated_real_chat_recovers_actual_chat_failure(controlled_ai, behavior):
    config = remote_settings(controlled_ai)
    gateway = Gateway(config)
    assert config.chat_available('owner-a') is True  # configured, not health-probed
    controlled_ai.behavior['chat'] = behavior
    if behavior == 'timeout':
        config.ai_timeout = .02
    with pytest.raises(AIUnavailable):
        call(gateway)
    assert config.chat_available('owner-a') is False
    assert Gateway(config).settings.chat_available('owner-a') is False
    # Successful other capabilities cannot erase chat-specific outage evidence.
    config.ai_timeout = .5
    call(gateway, 'embedding')
    assert config.chat_available('owner-a') is False
    controlled_ai.behavior['chat'] = 'success'
    result, provenance = call(gateway)
    assert result['speech'] and provenance == 'real'
    assert config.chat_available('owner-a') is True


@pytest.mark.parametrize('capability', ['food', 'embedding', 'evolutions'])
def test_other_capability_failure_never_marks_chat_unavailable(controlled_ai, capability):
    config = remote_settings(controlled_ai)
    controlled_ai.behavior[capability] = '503'
    with pytest.raises(AIUnavailable):
        call(Gateway(config), capability)
    assert config.chat_available('owner-a') is True
    assert controlled_ai.requests == [capability]


def test_disabled_and_isolated_mock_scope_are_preserved_without_remote_calls(controlled_ai):
    config = remote_settings(controlled_ai)
    config.ai_mode = 'disabled'
    assert config.chat_available('owner-a') is False
    with pytest.raises(AIUnavailable):
        call(Gateway(config))
    config.ai_mode = 'mock'
    assert config.chat_available('owner-a') is True
    assert config.chat_available('outside-owner') is False
    assert config.chat_available() is False
    assert call(Gateway(config))[1] == 'synthetic'
    with pytest.raises(AIUnavailable):
        Gateway(config).call('chat', 'fixture-request', 'fixture-pet', {}, 'outside-owner', True)
    assert controlled_ai.requests == []


def test_allowed_synthetic_remote_reply_does_not_prove_real_chat_recovery(controlled_ai):
    config = remote_settings(controlled_ai)
    controlled_ai.behavior['chat'] = '503'
    with pytest.raises(AIUnavailable):
        call(Gateway(config))
    controlled_ai.behavior['chat'] = 'synthetic'
    assert call(Gateway(config))[1] == 'synthetic'
    assert config.chat_available('owner-a') is False


def test_process_configuration_restart_resets_evidence_and_endpoint_change_does_not_inherit_failure(controlled_ai):
    config = remote_settings(controlled_ai)
    config.record_remote_chat(False, 'ai_timeout')
    assert config.chat_available('owner-a') is False
    assert replace(config).chat_available('owner-a') is True
    config.ai_base_url += '/new-origin-path'
    assert config.chat_available('owner-a') is True


@pytest.fixture
def availability_client(settings, db, controlled_ai):
    config = replace(settings, ai_mode='remote', ai_base_url=controlled_ai.url, ai_token='isolated-test-server-token',
                     allow_http_ai=True, ai_timeout=.5)
    application = create_app(config, db)
    application.state.clock = lambda: BASE
    with TestClient(application) as client:
        client.headers['Authorization'] = 'Bearer test-owner-a-token'
        yield client, config


def seeded_chat_pet(client, db):
    day = rules._day(BASE)
    ident = next('availability-pet-' + str(i) for i in range(100)
                 if quests._template('availability-pet-' + str(i), day, 'easy', True)['candidate'] == 'chat1')
    with db.connect() as c:
        c.execute('INSERT INTO pets(id,owner_id,settings,created_at) VALUES(%s,%s,%s,%s)',
                  (ident, 'owner-a', Jsonb(PetSettings(name='가명 테스트펫').model_dump()), BASE))
        service.seed_goals(c, ident, BASE)
    assert client.get('/pets/' + ident + '/state').status_code == 200
    return ident


def easy_row(db, pet):
    with db.connect() as c:
        return c.execute("SELECT * FROM quest_offers WHERE pet_id=%s AND slot='easy' AND period_start=%s",
                         (pet, rules._day(BASE))).fetchone()


@pytest.mark.parametrize('trigger', ['state', 'quests', 'workout', 'worker'])
def test_pg_actual_http_chat503_replaces_same_slot_once_and_valid_chat_recovers(availability_client, db, controlled_ai, trigger, monkeypatch):
    client, config = availability_client
    pet = seeded_chat_pet(client, db)
    before = easy_row(db, pet)
    assert before['template']['candidate'] == 'chat1'
    controlled_ai.behavior['chat'] = '503'
    failed = client.post('/pets/' + pet + '/chat', json={'request_id': 'outage-request-one', 'text': '가명 테스트 대화'})
    assert failed.status_code == 503
    assert config.chat_available('owner-a') is False
    if trigger in {'state', 'quests'}:
        assert client.get('/pets/' + pet + '/' + trigger).status_code == 200
    elif trigger == 'workout':
        response = client.post('/pets/' + pet + '/workouts', json={'event_id': 'fixture-during-outage', 'revision': 1,
            'occurred_at': BASE.isoformat(), 'workout_type': 'run', 'actual': None, 'unit': 'minutes', 'source': 'user'})
        assert response.status_code == 200, response.text
    else:
        monkeypatch.setattr(worker.service, 'utcnow', lambda: BASE)
        assert worker.run_once(db, config, client.app.state.gateway) is False
    after = easy_row(db, pet)
    assert after['id'] == before['id'] and after['slot'] == before['slot']
    assert after['replacement_count'] == 1
    assert after['template']['candidate'] in {'meal1', 'workout1'}
    assert after['template']['history'] == [{'candidate': 'chat1', 'reason': 'dependency_unavailable', 'replaced_at': BASE.isoformat()}]
    for _ in range(3):
        assert client.get('/pets/' + pet + '/state').status_code == 200
        assert client.get('/pets/' + pet + '/quests').status_code == 200
    assert controlled_ai.requests == ['chat']  # no new health/chat calls on reads
    assert easy_row(db, pet)['replacement_count'] == 1
    controlled_ai.behavior['chat'] = 'success'
    recovered = client.post('/pets/' + pet + '/chat', json={'request_id': 'recovered-request-two', 'text': '가명 다시 대화'})
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()['metrics']['fallback'] is False
    assert recovered.json()['provenance'] == 'real'
    assert config.chat_available('owner-a') is True
    assert easy_row(db, pet)['template'] == after['template']
    assert easy_row(db, pet)['replacement_count'] == 1
    assert controlled_ai.requests == ['chat', 'chat']


def test_pg_outage_excludes_only_current_unfinished_optional_chat_and_never_revives_it(availability_client, db, controlled_ai):
    client, config = availability_client
    pet = seeded_chat_pet(client, db)
    definitions = [('current-active', 'chat1', 'active', -1, 23), ('current-accepted', 'chat1', 'accepted', -1, 23),
                   ('current-offered', 'chat1', 'offered', -1, 23), ('completed-chat', 'chat1', 'completed', -4, 20),
                   ('expired-chat', 'chat1', 'active', -25, -1), ('rejected-chat', 'chat1', 'rejected', -4, 20),
                   ('active-workout', 'workout1', 'active', -1, 23), ('active-meal', 'meal1', 'active', -1, 23),
                   ('future-chat', 'chat1', 'offered', 1, 25)]
    completed_event = {'event_id': 'earlier-real-chat', 'kind': 'chat', 'valid': True,
                       'occurred_at': BASE - timedelta(hours=2), 'received_at': BASE - timedelta(hours=2),
                       'payload': {'normal': True, 'text': '실제 eligible 가명 대화'}}
    with db.connect() as c:
        for ident, candidate, status, start, end in definitions:
            created = BASE + timedelta(hours=start)
            c.execute("""INSERT INTO quest_offers(pet_id,id,template,status,state_version,created_at,expires_at,is_proposal,
                         shown_at,accepted_at,completed_at,completion_verified,rejected_at)
                         VALUES(%s,%s,%s,%s,0,%s,%s,true,%s,%s,%s,%s,%s)""",
                      (pet, ident, Jsonb({'candidate': candidate, 'target': 1}), status, created, BASE + timedelta(hours=end),
                       None if status == 'offered' else created,
                       BASE - timedelta(hours=3) if status == 'completed' else BASE - timedelta(minutes=30) if status == 'accepted' else None,
                       BASE - timedelta(hours=2) if status == 'completed' else None, status == 'completed',
                       BASE - timedelta(hours=3) if status == 'rejected' else None))
        before = quests.proposals(c, pet)
        quests.sync_quests(c, pet, [completed_event], BASE, False)
        rows = {r['id']: r for r in c.execute('SELECT * FROM quest_offers WHERE pet_id=%s AND is_proposal', (pet,))}
        cancelled = {'current-active', 'current-accepted', 'current-offered'}
        for ident, row in rows.items():
            assert row['excluded'] is (ident in cancelled)
            if ident in cancelled:
                assert row['cancelled_at'] == BASE
                assert row['template']['unavailable'] is True
            else:
                assert row['cancelled_at'] is None
                assert 'unavailable' not in row['template']
        week = rules._monday(rules._day(BASE))
        expected = [p for p in before if p['proposal_id'] not in cancelled]
        assert rules._proposal_counts(quests.proposals(c, pet), week, week + timedelta(days=7)) == rules._proposal_counts(expected, week, week + timedelta(days=7))
        quests.sync_quests(c, pet, [completed_event], BASE + timedelta(minutes=1), True)
        assert c.execute("SELECT count(*) AS n FROM quest_offers WHERE pet_id=%s AND id=ANY(%s) AND excluded AND cancelled_at=%s",
                         (pet, list(cancelled), BASE)).fetchone()['n'] == 3
