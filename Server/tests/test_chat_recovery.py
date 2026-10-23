"""PostgreSQL retry/context leases and privacy dependency acceptance tests.

Gateway calls are controlled test fixtures. No real AI inference or personal user data.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from threading import Event

import pytest

from Server.healthmon.gateway import AIUnavailable


def request(ident, text='isolated synthetic chat fixture'):
    return {'request_id': ident, 'text': text}


def rows(db, query, params):
    with db.connect() as c:
        return c.execute(query, params).fetchall()


@pytest.mark.parametrize('recovery_state', ['failed', 'expired_running'])
def test_retry_uses_original_persisted_context_after_growth_changes(client, settings, db, pet, monkeypatch, recovery_state):
    settings.ai_mode = 'mock'
    initial_time = client.app.state.clock()
    original = client.app.state.gateway.call
    calls = []

    def timeout_then_succeed(capability, ident, pet_id, payload, *args, **kwargs):
        if capability == 'chat':
            calls.append((ident, deepcopy(payload)))
            if len(calls) == 1:
                raise AIUnavailable('ai_timeout', retryable=True)
        return original(capability, ident, pet_id, payload, *args, **kwargs)

    monkeypatch.setattr(client.app.state.gateway, 'call', timeout_then_succeed)
    body = request('frozen-context-retry-' + recovery_state)
    first = client.post(f'/pets/{pet}/chat', json=body)
    assert first.status_code == 503
    saved = rows(db, 'SELECT ai_input,status,lease_token FROM requests WHERE pet_id=%s AND id=%s', (pet, body['request_id']))[0]
    assert saved['status'] == 'failed' and saved['ai_input'] == calls[0][1]
    assert saved['ai_input']['context']['state']['lower_body'] == 50
    client.app.state.clock = lambda: initial_time + timedelta(minutes=2)
    workout = {'event_id': 'during-frozen-retry', 'occurred_at': client.app.state.clock().isoformat(),
               'started_at': client.app.state.clock().isoformat(), 'source': 'user', 'synthetic': True,
               'workout_type': 'running', 'actual': 30, 'unit': 'minutes'}
    changed = client.post(f'/pets/{pet}/workouts', json=workout)
    assert changed.status_code == 200 and changed.json()['state']['lower_body'] == 52
    if recovery_state == 'expired_running':
        with db.connect() as c:
            c.execute("UPDATE requests SET status='running',lease_until=%s WHERE pet_id=%s AND id=%s",
                      (initial_time - timedelta(seconds=1), pet, body['request_id']))
    # Polling/rebasing transport state must not silently change an already dispatched AI input.
    retried = client.post(f'/pets/{pet}/chat', json={**body, 'state_version': changed.json()['state_version']})
    assert retried.status_code == 200, retried.text
    assert calls[0] == calls[1]
    assert retried.json()['state_used'] == saved['ai_input']['context']['state']
    assert retried.json()['state_after']['lower_body'] == 52
    after = rows(db, 'SELECT status,lease_token FROM requests WHERE pet_id=%s AND id=%s', (pet, body['request_id']))[0]
    assert after['status'] == 'done' and after['lease_token'] != saved['lease_token']
    assert len(rows(db, 'SELECT id FROM sources WHERE pet_id=%s AND id=%s', (pet, 'message:' + body['request_id']))) == 1


def test_active_chat_lease_rejects_concurrent_duplicate_then_expired_claim_completes_once(client, settings, db, pet, monkeypatch):
    settings.ai_mode = 'mock'
    original = client.app.state.gateway.call
    entered, release = Event(), Event()
    calls = []

    def first_call_waits(capability, ident, pet_id, payload, *args, **kwargs):
        if capability == 'chat':
            calls.append(deepcopy(payload))
            if len(calls) == 1:
                entered.set()
                assert release.wait(10), 'test did not release the first AI transport'
        return original(capability, ident, pet_id, payload, *args, **kwargs)

    monkeypatch.setattr(client.app.state.gateway, 'call', first_call_waits)
    body = request('concurrent-chat-lease-fixture')
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.post, f'/pets/{pet}/chat', json=body)
        try:
            assert entered.wait(5)
            assert client.post(f'/pets/{pet}/chat', json=body).status_code == 409
            assert len(calls) == 1
            with db.connect() as c:
                c.execute('UPDATE requests SET lease_until=%s WHERE pet_id=%s AND id=%s',
                          (client.app.state.clock() - timedelta(seconds=1), pet, body['request_id']))
            new_claim = client.post(f'/pets/{pet}/chat', json=body)
            assert new_claim.status_code == 200, new_claim.text
        finally:
            release.set()
        old_claim = pending.result(timeout=10)
    assert old_claim.status_code == 200 and old_claim.json() == new_claim.json()
    assert calls[0] == calls[1]
    assert len(rows(db, 'SELECT id FROM sources WHERE pet_id=%s AND id=%s', (pet, 'message:' + body['request_id']))) == 1
    assert len(rows(db, 'SELECT request_id FROM exchanges WHERE pet_id=%s AND request_id=%s', (pet, body['request_id']))) == 1


def test_erasing_recent_source_invalidates_direct_and_transitive_cached_replies(client, settings, db, pet, monkeypatch):
    settings.ai_mode = 'mock'
    original = client.app.state.gateway.call

    def quote_recent(capability, ident, pet_id, payload, *args, **kwargs):
        result, provenance = original(capability, ident, pet_id, payload, *args, **kwargs)
        if capability == 'chat':
            recent = payload['context']['recent']
            result['speech'] = 'private-synthetic-fixture' if not recent else recent[0]['speech'] + ' / quoted'
        return result, provenance

    monkeypatch.setattr(client.app.state.gateway, 'call', quote_recent)
    initial_time = client.app.state.clock()
    first = request('recent-source-root-fixture', 'private-synthetic-fixture')
    assert client.post(f'/pets/{pet}/chat', json=first).status_code == 200
    following = []
    for index in range(8):
        client.app.state.clock = lambda i=index: initial_time + timedelta(minutes=i + 1)
        body = request('recent-derived-fixture-' + str(index), 'an independent acknowledgement')
        response = client.post(f'/pets/{pet}/chat', json=body)
        assert response.status_code == 200 and 'private-synthetic-fixture' in response.json()['response']['speech']
        following.append(body)
    last = rows(db, 'SELECT dependency_source_ids,ai_input FROM requests WHERE pet_id=%s AND id=%s', (pet, following[-1]['request_id']))[0]
    assert 'message:' + first['request_id'] in last['dependency_source_ids']
    assert 'message:' + first['request_id'] not in {r['source_id'] for r in last['ai_input']['context']['recent']}
    erased = client.delete(f'/pets/{pet}/sources/message:{first["request_id"]}', params={'expected_revision': 1})
    assert erased.status_code == 200, erased.text
    for body in following:
        saved = rows(db, 'SELECT status,ai_input,result FROM requests WHERE pet_id=%s AND id=%s', (pet, body['request_id']))[0]
        assert saved == {'status': 'invalidated', 'ai_input': None, 'result': None}
        exchange = rows(db, 'SELECT valid,speech FROM exchanges WHERE pet_id=%s AND request_id=%s', (pet, body['request_id']))[0]
        assert exchange == {'valid': False, 'speech': ''}
        assert client.post(f'/pets/{pet}/chat', json=body).status_code == 410


def test_erasing_source_while_derived_reply_is_running_prevents_cached_resurrection(client, settings, db, pet, monkeypatch):
    settings.ai_mode = 'mock'
    first = request('privacy-pending-original', 'private fixture for an in-flight context')
    assert client.post(f'/pets/{pet}/chat', json=first).status_code == 200
    entered, release = Event(), Event()
    original = client.app.state.gateway.call

    def hold_derived(capability, *args, **kwargs):
        if capability == 'chat':
            entered.set()
            assert release.wait(10), 'test did not release the AI transport'
        return original(capability, *args, **kwargs)

    monkeypatch.setattr(client.app.state.gateway, 'call', hold_derived)
    body = request('privacy-pending-derived')
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.post, f'/pets/{pet}/chat', json=body)
        try:
            assert entered.wait(5)
            erased = client.delete(f'/pets/{pet}/sources/message:{first["request_id"]}', params={'expected_revision': 1})
            assert erased.status_code == 200, erased.text
        finally:
            release.set()
        rejected = pending.result(timeout=10)
    assert rejected.status_code == 410
    saved = rows(db, 'SELECT status,ai_input,result FROM requests WHERE pet_id=%s AND id=%s', (pet, body['request_id']))[0]
    assert saved == {'status': 'invalidated', 'ai_input': None, 'result': None}
    assert not rows(db, 'SELECT id FROM sources WHERE pet_id=%s AND id=%s', (pet, 'message:' + body['request_id']))
    assert not rows(db, 'SELECT request_id FROM exchanges WHERE pet_id=%s AND request_id=%s', (pet, body['request_id']))
