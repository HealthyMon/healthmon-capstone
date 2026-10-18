"""Local browser security and canonical history against the real test DB; no model inference."""
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from src import app as module
from src import beta
from src.db import connect

ORIGIN = 'http://127.0.0.1:8000'
TOKEN_A = 'beta-test-secret-a'
TOKEN_B = 'beta-test-secret-b'


@pytest.fixture
def client(monkeypatch):
    owners = ['beta-test-' + uuid.uuid4().hex, 'beta-test-' + uuid.uuid4().hex]
    monkeypatch.setenv('DEV_TOKENS', json.dumps({TOKEN_A: owners[0], TOKEN_B: owners[1]}))
    monkeypatch.delenv('BETA_SESSION_SECRET', raising=False)
    with TestClient(module.app, base_url=ORIGIN, client=('127.0.0.1', 43210)) as instance:
        yield instance
    # Only fixtures under this invocation's unique owners are removed.
    with connect() as c:
        ids = [row['id'] for row in c.execute('SELECT id FROM pets WHERE owner_id=ANY(%s)', (owners,))]
        for table in ('outbox', 'state_snapshots', 'suggestion_jobs', 'reward_ledger',
                      'quest_offers', 'exchanges', 'memories', 'requests', 'sources'):
            c.execute(f'DELETE FROM {table} WHERE pet_id=ANY(%s)', (ids,))
        c.execute('DELETE FROM pets WHERE id=ANY(%s)', (ids,))


def session(client):
    result = client.post('/beta/session', headers={'Origin': ORIGIN})
    assert result.status_code == 200, result.text
    return result


def pet(client, token=TOKEN_A):
    result = client.post('/pets', json={}, headers={'Authorization': 'Bearer ' + token})
    assert result.status_code == 200, result.text
    return result.json()['pet_id']


def seed_message(pet_id, text='산책하고 돌아왔어.', *, age=0):
    request_id = uuid.uuid4().hex
    source_id = 'message:' + request_id
    response = {'speech': '잘 돌아왔어.', 'emotion': 'happy', 'animation': 'wave',
                'action': {'type': 'none', 'target_id': None}, 'memory_ids': [],
                'personality_update': None}
    result = {'source_id': source_id, 'source_revision': 1, 'response': response,
              'execution': {}, 'metrics': {'fallback': False}, 'state_version': 1}
    with connect() as c:
        c.execute("INSERT INTO sources(pet_id,id,kind,revision,occurred_at,payload) VALUES(%s,%s,'message',1,%s,%s)",
                  (pet_id, source_id, datetime.now(timezone.utc) - timedelta(seconds=age), Jsonb({'text': text})))
        c.execute("INSERT INTO requests(pet_id,id,fingerprint,status,result) VALUES(%s,%s,%s,'done',%s)",
                  (pet_id, request_id, hashlib.sha256(text.encode()).hexdigest(), Jsonb(result)))
        c.execute('INSERT INTO exchanges(pet_id,request_id,source_id,speech,memory_ids,state_used,state_after) '
                  "VALUES(%s,%s,%s,%s,'[]','{}','{}')", (pet_id, request_id, source_id, response['speech']))
    return source_id


def test_session_cookie_does_not_expose_server_tokens(client):
    response = session(client)
    assert response.json()['account_scope'] == 'shared_local_development'
    cookie = response.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'SameSite=strict' in cookie and 'Path=/' in cookie
    assert TOKEN_A not in response.text + cookie and TOKEN_B not in response.text + cookie
    assert client.get('/beta/session').json()['authenticated'] is True
    assert 'no-store' in response.headers['cache-control']


@pytest.mark.parametrize('headers', [
    {}, {'Origin': 'https://attacker.example'}, {'Origin': 'null'},
    {'Origin': ORIGIN, 'Host': 'attacker.example'},
    {'Origin': ORIGIN, 'Sec-Fetch-Site': 'cross-site'},
    {'Origin': 'http://localhost:8000'},
])
def test_bootstrap_rejects_missing_cross_origin_or_rebinding_host(client, headers):
    response = client.post('/beta/session', headers=headers)
    assert response.status_code == 403
    assert beta.COOKIE not in response.cookies


def test_bootstrap_rejects_non_loopback_peer(client):
    with TestClient(module.app, base_url=ORIGIN, client=('192.168.1.24', 43210)) as remote:
        assert remote.post('/beta/session', headers={'Origin': ORIGIN}).status_code == 403


def test_cookie_mutation_requires_origin_but_bearer_api_is_unchanged(client):
    session(client)
    assert client.post('/pets', json={}).status_code == 403
    assert client.post('/pets', json={}, headers={'Origin': 'https://attacker.example'}).status_code == 403
    own = client.post('/pets', json={}, headers={'Origin': ORIGIN})
    assert own.status_code == 200
    # Unity sends a Bearer token, not browser session cookies or Origin.
    second = pet(client, TOKEN_B)
    assert client.get(f'/pets/{second}/state').status_code == 404
    assert client.get(f'/pets/{second}/messages').status_code == 404
    listed = client.get('/pets').json()['pets']
    assert [item['pet_id'] for item in listed] == [own.json()['pet_id']]
    assert client.get('/pets', headers={'Authorization': 'Bearer invalid'}).status_code == 401


def test_tampered_expired_and_unconfigured_owner_sessions_rejected(client):
    session(client)
    valid = client.cookies[beta.COOKIE]
    client.cookies.clear()
    assert client.get('/pets', headers={'Cookie': beta.COOKIE + '=' + valid + 'x'}).status_code == 401
    owner = next(iter(json.loads(os.environ['DEV_TOKENS']).values()))
    expired = beta._encode_session(owner, int(time.time()) - 1)
    assert client.get('/pets', headers={'Cookie': beta.COOKIE + '=' + expired}).status_code == 401
    unknown = beta._encode_session('removed-owner', int(time.time()) + 30)
    assert client.get('/pets', headers={'Cookie': beta.COOKIE + '=' + unknown}).status_code == 401


def test_history_is_chronological_and_correction_or_deletion_does_not_resurrect_reply(client):
    ident = pet(client)
    older = seed_message(ident, '저녁 산책을 좋아해.', age=20)
    newer = seed_message(ident, '다녀왔어.', age=10)
    session(client)
    url = f'/pets/{ident}/messages'
    history = client.get(url).json()
    assert [row['source_id'] for row in history['messages']] == [older, newer]
    assert all(row['assistant'] == '잘 돌아왔어.' for row in history['messages'])
    limited = client.get(url, params={'limit': 1}).json()
    assert limited['has_more'] and [row['source_id'] for row in limited['messages']] == [newer]
    assert client.get(url, params={'limit': 101}).status_code == 422
    corrected = client.patch(f'/pets/{ident}/sources/{older}',
                             json={'expected_revision': 1, 'text': '아침 산책을 좋아해.'},
                             headers={'Origin': ORIGIN})
    assert corrected.status_code == 200, corrected.text
    history = client.get(url).json()['messages']
    assert history[0]['user'] == '아침 산책을 좋아해.' and history[0]['source_revision'] == 2
    assert all(row['assistant'] is None and row['response'] is None for row in history)
    deleted = client.delete(f'/pets/{ident}/sources/{older}', params={'expected_revision': 2},
                            headers={'Origin': ORIGIN})
    assert deleted.status_code == 200
    assert [row['source_id'] for row in client.get(url).json()['messages']] == [newer]


def test_history_checks_revision_even_when_stale_exchange_remains_valid(client):
    ident = pet(client)
    source_id = seed_message(ident)
    with connect() as c:
        # Simulate an older writer leaving an exchange marked valid at revision 2.
        c.execute("UPDATE sources SET revision=2,payload=%s WHERE pet_id=%s AND id=%s",
                  (Jsonb({'text': '정정한 내용이야.'}), ident, source_id))
    response = client.get(f'/pets/{ident}/messages', headers={'Authorization': 'Bearer ' + TOKEN_A})
    turn = response.json()['messages'][0]
    assert turn['user'] == '정정한 내용이야.' and turn['assistant'] is None


def test_history_excludes_reply_with_invalidated_cited_memory(client):
    ident = pet(client)
    source_id = seed_message(ident)
    with connect() as c:
        c.execute("INSERT INTO memories(pet_id,id,source_id,source_revision,slot,content,valid) "
                  "VALUES(%s,'stale-citation',%s,1,'preference','예전 취향',false)", (ident, source_id))
        c.execute('UPDATE exchanges SET memory_ids=%s WHERE pet_id=%s',
                  (Jsonb(['stale-citation']), ident))
    response = client.get(f'/pets/{ident}/messages', headers={'Authorization': 'Bearer ' + TOKEN_A})
    assert response.json()['messages'][0]['assistant'] is None
