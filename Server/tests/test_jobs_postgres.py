"""Real PostgreSQL job/outbox/asset tests with controlled inference responses.

These fixtures exercise durable production tables and transactions, not GPU inference
or native Unity GLB rendering. Ledger seeds are isolated test setup, never an API bypass.
"""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
import struct

import pytest
from psycopg.types.json import Jsonb

from Server.healthmon import rules, service, worker
from Server.healthmon.db import Database
from Server.healthmon.gateway import AIUnavailable


def structural_glb():
    # Structural contract only, deliberately not presented as a renderable AI avatar.
    doc = {'asset': {'version': '2.0'}, 'skins': [{'joints': [0]}],
           'meshes': [{'primitives': [{'attributes': {'JOINTS_0': 0, 'WEIGHTS_0': 1}}]}],
           'nodes': [{'skin': 0, 'mesh': 0}], 'images': [{'bufferView': 0}],
           'buffers': [{'byteLength': 0}]}
    raw = json.dumps(doc).encode()
    raw += b' ' * ((-len(raw)) % 4)
    return struct.pack('<4sIIII', b'glTF', 2, 20 + len(raw), len(raw), 0x4E4F534A) + raw


class ControlledGateway:
    def __init__(self, outcome='succeeded', data=None, provenance='real', during_call=None):
        self.outcome = outcome
        self.data = structural_glb() if data is None else data
        self.provenance = provenance
        self.during_call = during_call
        self.calls = []
        self.downloads = []

    def call(self, capability, request_id, pet_id, payload, owner, database_is_test, method='POST'):
        self.calls.append((capability, request_id, pet_id, deepcopy(payload), owner, database_is_test, method))
        if self.during_call:
            self.during_call(request_id, pet_id)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        result = {'job_id': request_id, 'stage': payload['stage'], 'status': self.outcome}
        if self.outcome == 'succeeded':
            result.update(model_url='/fixture.glb', model_sha256=hashlib.sha256(self.data).hexdigest(), size_bytes=len(self.data))
        elif self.outcome in ('failed', 'unsupported'):
            result['error'] = 'controlled_inference_failure'
        return result, self.provenance

    def asset(self, url, expected_sha, expected_size):
        self.downloads.append((url, expected_sha, expected_size))
        assert hashlib.sha256(self.data).hexdigest() == expected_sha and len(self.data) == expected_size
        return self.data


@pytest.fixture(autouse=True)
def fixed_worker_clock(monkeypatch, client):
    monkeypatch.setattr(service, 'utcnow', client.app.state.clock)


def seed_level(db, client, pet, level):
    total = sum(rules.required_exp(value) for value in range(1, level))
    with db.connect() as c:
        c.execute("INSERT INTO game_ledger(pet_id,reward_key,exp,coin,reason) VALUES(%s,'isolated-job-test-seed',%s,0,'synthetic integration test setup') ON CONFLICT(pet_id,reward_key) DO UPDATE SET exp=excluded.exp", (pet, total))
    state = client.get(f'/pets/{pet}/state').json()
    assert state['level'] == level
    return state


def enqueue(client, pet, request='evolution-request-one'):
    response = client.post(f'/pets/{pet}/evolutions', json={'request_id': request})
    assert response.status_code == 200, response.text
    return response.json()


def job_row(db, ident):
    with db.connect() as c:
        return c.execute('SELECT * FROM ai_jobs WHERE id=%s', (ident,)).fetchone()


def expire_lease(db, ident):
    with db.connect() as c:
        c.execute("UPDATE ai_jobs SET lease_until=now()-interval '1 day' WHERE id=%s", (ident,))


def test_repeated_and_different_requests_share_one_frozen_stage_job(db, client, pet):
    seed_level(db, client, pet, 10)
    first = enqueue(client, pet)
    assert enqueue(client, pet)['job_id'] == first['job_id']
    assert enqueue(client, pet, 'another-request-for-same-stage')['job_id'] == first['job_id']
    with db.connect() as c:
        assert c.execute('SELECT count(*) AS n FROM ai_jobs WHERE pet_id=%s', (pet,)).fetchone()['n'] == 1
        frozen = c.execute('SELECT input FROM ai_jobs WHERE id=%s', (first['job_id'],)).fetchone()['input']
    assert frozen['stage'] == 1 and frozen['state']['level'] == 10
    assert frozen['rule_version'] == rules.RULE_VERSION
    assert frozen['legacy_compatibility']['mood'] is None
    assert frozen['legacy_compatibility']['original_energy_balance'] == 0


def test_request_identity_survives_later_stage_and_success(db, settings, client, pet):
    seed_level(db, client, pet, 10)
    first = enqueue(client, pet)
    assert worker.run_once(db, settings, ControlledGateway())
    # A retry after publication is the same completed job, not an eligibility error.
    assert enqueue(client, pet)['job_id'] == first['job_id']
    seed_level(db, client, pet, 20)
    second = enqueue(client, pet, 'evolution-request-two')
    assert second['stage'] == 2 and second['job_id'] != first['job_id']
    assert enqueue(client, pet)['job_id'] == first['job_id']
    assert job_row(db, first['job_id'])['input']['state']['level'] == 10


def test_uncertain_dispatch_restart_polls_same_id_and_publishes_once(db, settings, client, pet):
    seed_level(db, client, pet, 10)
    first = enqueue(client, pet)
    uncertain = ControlledGateway(AIUnavailable('ai_timeout', retryable=True))
    assert worker.run_once(db, settings, uncertain)
    assert uncertain.calls[0][-1] == 'PUT'
    assert job_row(db, first['job_id'])['status'] == 'running'
    assert not worker.run_once(db, settings, ControlledGateway())  # active retry lease
    expire_lease(db, first['job_id'])
    restarted_database = Database(settings)
    recovered = ControlledGateway()
    assert worker.run_once(restarted_database, settings, recovered)
    assert recovered.calls[0][-1] == 'GET'
    assert recovered.calls[0][1] == uncertain.calls[0][1] == first['job_id']
    assert recovered.calls[0][3] == uncertain.calls[0][3]
    assert job_row(db, first['job_id'])['attempts'] == 2
    state = client.get(f'/pets/{pet}/state').json()
    assert state['published_model_stage'] == 1 and state['model_reference'].endswith(first['job_id'])
    assert not worker.run_once(db, settings, ControlledGateway())
    with db.connect() as c:
        assert c.execute('SELECT count(*) AS n FROM model_assets WHERE pet_id=%s', (pet,)).fetchone()['n'] == 1


def test_claim_transaction_is_released_before_remote_call(db, settings, client, pet):
    seed_level(db, client, pet, 10)
    job = enqueue(client, pet)
    checked = []

    def inspect_unlocked(ident, pet_id):
        with db.connect() as c:
            c.execute('SELECT id FROM pets WHERE id=%s FOR UPDATE NOWAIT', (pet_id,))
            row = c.execute('SELECT id,status,lease_until FROM ai_jobs WHERE id=%s FOR UPDATE NOWAIT', (ident,)).fetchone()
            assert row['status'] == 'dispatching' and row['lease_until'] is not None
            checked.append(row['id'])

    assert worker.run_once(db, settings, ControlledGateway(during_call=inspect_unlocked))
    assert checked == [job['job_id']]


def test_failed_new_stage_preserves_last_published_asset(db, settings, client, pet):
    seed_level(db, client, pet, 10)
    first = enqueue(client, pet)
    good = ControlledGateway()
    worker.run_once(db, settings, good)
    original = client.get(f'/pets/{pet}/state').json()
    seed_level(db, client, pet, 20)
    second = enqueue(client, pet, 'second-stage-failure')
    worker.run_once(db, settings, ControlledGateway('failed'))
    state = client.get(f'/pets/{pet}/state').json()
    assert state['evolution_target_stage'] == 2 and state['published_model_stage'] == 1
    assert state['model_reference'] == original['model_reference']
    assert job_row(db, second['job_id'])['status'] == 'failed'
    asset = client.get(f'/pets/{pet}/assets/{first["job_id"]}')
    assert asset.status_code == 200 and asset.content == good.data


def test_older_completion_cannot_publish_after_newer_stage_is_requested(db, settings, client, pet):
    seed_level(db, client, pet, 10)
    first = enqueue(client, pet)
    seed_level(db, client, pet, 20)
    second = enqueue(client, pet, 'newer-frozen-stage-two')
    with db.connect() as c:
        c.execute('UPDATE ai_jobs SET created_at=%s WHERE id=%s', (service.utcnow() - timedelta(minutes=2), first['job_id']))
        c.execute('UPDATE ai_jobs SET created_at=%s WHERE id=%s', (service.utcnow() - timedelta(minutes=1), second['job_id']))
    assert worker.run_once(db, settings, ControlledGateway())
    stale_state = client.get(f'/pets/{pet}/state').json()
    assert job_row(db, first['job_id'])['status'] == 'succeeded'
    assert stale_state['published_model_stage'] == 0 and stale_state['model_reference'] is None
    assert worker.run_once(db, settings, ControlledGateway())
    current = client.get(f'/pets/{pet}/state').json()
    assert current['published_model_stage'] == 2 and current['model_reference'].endswith(second['job_id'])


@pytest.mark.parametrize('data,provenance,error', [
    (b'not a glb', 'real', 'invalid_glb'),
    (None, 'synthetic', 'synthetic_completed_asset_rejected'),
])
def test_invalid_or_synthetic_completed_asset_never_publishes(db, settings, client, pet, data, provenance, error):
    seed_level(db, client, pet, 10)
    job = enqueue(client, pet)
    assert worker.run_once(db, settings, ControlledGateway(data=data, provenance=provenance))
    saved = job_row(db, job['job_id'])
    assert saved['status'] == 'failed' and saved['error'] == error
    state = client.get(f'/pets/{pet}/state').json()
    assert state['published_model_stage'] == 0 and state['model_reference'] is None
    with db.connect() as c:
        assert c.execute('SELECT count(*) AS n FROM model_assets WHERE pet_id=%s', (pet,)).fetchone()['n'] == 0


def test_asset_and_job_are_private_to_authenticated_owner(db, settings, client, pet):
    seed_level(db, client, pet, 10)
    job = enqueue(client, pet)
    gateway = ControlledGateway()
    assert worker.run_once(db, settings, gateway)
    asset_path = f'/pets/{pet}/assets/{job["job_id"]}'
    result = client.get(asset_path)
    assert result.status_code == 200 and result.headers['content-type'] == 'model/gltf-binary'
    assert result.headers['etag'] == hashlib.sha256(gateway.data).hexdigest()
    assert result.headers['cache-control'] == 'private, no-cache'
    assert 'model_url' not in result.headers
    client.headers['Authorization'] = 'Bearer test-owner-b-token'
    assert client.get(asset_path).status_code in (403, 404)
    assert client.get(f'/pets/{pet}/evolutions/{job["job_id"]}').status_code in (403, 404)


def test_atomic_asset_completion_rolls_back_when_publication_transaction_fails(db, settings, client, pet, monkeypatch):
    seed_level(db, client, pet, 10)
    job = enqueue(client, pet)
    original = service.refresh

    def fail_publication(*args, **kwargs):
        if (len(args) > 5 and args[5] == 'evolution_published') or kwargs.get('reason') == 'evolution_published':
            raise RuntimeError('controlled transaction failure')
        return original(*args, **kwargs)

    monkeypatch.setattr(service, 'refresh', fail_publication)
    with pytest.raises(RuntimeError, match='controlled transaction failure'):
        worker.run_once(db, settings, ControlledGateway())
    saved = job_row(db, job['job_id'])
    assert saved['status'] == 'dispatching' and saved['result'] is None
    with db.connect() as c:
        assert c.execute('SELECT count(*) AS n FROM model_assets WHERE job_id=%s', (job['job_id'],)).fetchone()['n'] == 0
        assert c.execute('SELECT state FROM game_states WHERE pet_id=%s', (pet,)).fetchone()['state']['published_model_stage'] == 0
    monkeypatch.setattr(service, 'refresh', original)
    expire_lease(db, job['job_id'])
    recovered = ControlledGateway()
    assert worker.run_once(db, settings, recovered)
    assert recovered.calls[0][-1] == 'GET' and recovered.calls[0][1] == job['job_id']


def test_disabled_ai_records_job_failure_without_gpu_dependencies(db, settings, client, pet):
    from Server.healthmon.gateway import Gateway
    seed_level(db, client, pet, 10)
    job = enqueue(client, pet)
    assert worker.run_once(db, settings, Gateway(settings))
    assert job_row(db, job['job_id'])['status'] == 'failed'
    assert client.get(f'/pets/{pet}/state').json()['published_model_stage'] == 0


@pytest.mark.parametrize('changed', [
    {'images': [None]}, {'meshes': [None]}, {'nodes': [None]},
    {'meshes': 'not-an-array'}, {'meshes': [{'primitives': [None]}]},
])
def test_malformed_glb_shapes_fail_job_without_crashing_worker(db, settings, client, pet, changed):
    seed_level(db, client, pet, 10)
    job = enqueue(client, pet)
    doc = json.loads(structural_glb()[20:])
    doc.update(changed)
    raw = json.dumps(doc).encode()
    raw += b' ' * ((-len(raw)) % 4)
    model = struct.pack('<4sIIII', b'glTF', 2, 20 + len(raw), len(raw), 0x4E4F534A) + raw
    assert worker.run_once(db, settings, ControlledGateway(data=model))
    assert job_row(db, job['job_id'])['status'] == 'failed'
    assert client.get(f'/pets/{pet}/state').json()['published_model_stage'] == 0
    # The next scheduling iteration still works after rejecting this remote result.
    assert not worker.run_once(db, settings, ControlledGateway())


def test_pet_erasure_during_inference_discards_completion_without_stopping_worker(db, settings, client, pet):
    from Server.healthmon import privacy
    seed_level(db, client, pet, 10)
    enqueue(client, pet)

    def erase_during_inference(ident, pet_id):
        with db.connect() as c:
            p = service.owned(c, 'owner-a', pet_id, True)
            assert privacy.delete_pet(c, p)['deleted']

    assert worker.run_once(db, settings, ControlledGateway(during_call=erase_during_inference))
    with db.connect() as c:
        assert not c.execute('SELECT id FROM pets WHERE id=%s', (pet,)).fetchone()
        assert not c.execute('SELECT id FROM ai_jobs WHERE pet_id=%s', (pet,)).fetchone()
        assert not c.execute('SELECT job_id FROM model_assets WHERE pet_id=%s', (pet,)).fetchone()
    assert not worker.run_once(db, settings, ControlledGateway())
