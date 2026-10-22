"""PostgreSQL outbox leases; a restarted worker reuses the same remote job ID."""
import json
import struct
import uuid
from datetime import timedelta
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from .gateway import AIUnavailable
from . import rules, service


def enqueue_evolution(c, pet, state, request_id, timestamp):
    existing_request = c.execute("SELECT * FROM ai_jobs WHERE pet_id=%s AND kind='evolution' AND request_id=%s", (pet['id'], request_id)).fetchone()
    if existing_request:
        return existing_request
    stage = state['evolution_target_stage']
    if stage <= state['published_model_stage']:
        raise HTTPException(409, 'No new evolution stage is pending')
    prior = c.execute("SELECT * FROM ai_jobs WHERE pet_id=%s AND kind='evolution' AND input->>'stage'=%s", (pet['id'], str(stage))).fetchone()
    if prior:
        if prior['request_id'] == request_id and prior['input']['stage'] != stage:
            # A repeated request returns its original frozen target, never creates a new paid job.
            return prior
        return prior
    ident = uuid.uuid4().hex
    payload = {'stage': stage, 'state': state, 'profile': rules.evolution_profile(state, state.get('previous_evolution')),
               'rule_version': rules.RULE_VERSION, 'adapter_version': 'healthmon.evolution.v2.2',
               'source_contract': 'new_common_gateway_contract', 'legacy_compatibility': {'energy_balance_normalized': state['energy_balance'] / 100,
               'original_energy_balance': state['energy_balance'], 'mood': None, 'stage_skip_requires_explicit_support': True}}
    if state['published_model_stage']==0 and (state.get('model_reference') or '').split('/')[-1].startswith('starter-'):
        from .starters import parent_asset
        payload['parent_asset']=parent_asset(c,pet['id'])
    return c.execute("INSERT INTO ai_jobs(id,pet_id,kind,request_id,fingerprint,input,created_at,updated_at) VALUES(%s,%s,'evolution',%s,%s,%s,%s,%s) RETURNING *",
                     (ident, pet['id'], request_id, service.fingerprint(payload), Jsonb(payload), timestamp, timestamp)).fetchone()


def job_view(job, state_version):
    result = job['result'] or {}
    reference = '/pets/' + job['pet_id'] + '/assets/' + job['id'] if job['status'] == 'succeeded' else None
    return {'job_id': job['id'], 'request_id': job['request_id'], 'stage': job['input']['stage'], 'status': job['status'],
            'model_reference': reference, 'model_url': reference, 'model_sha256': result.get('model_sha256'),
            'error': job['error'], 'state_version': state_version}


def validate_glb(data):
    if len(data) < 20:
        raise AIUnavailable('invalid_glb')
    magic, version, length, chunk_size, chunk_type = struct.unpack('<4sIIII', data[:20])
    if magic != b'glTF' or version != 2 or length != len(data) or chunk_type != 0x4E4F534A or chunk_size > length - 20:
        raise AIUnavailable('invalid_glb')
    try:
        doc = json.loads(data[20:20 + chunk_size])
    except (ValueError, UnicodeError) as exc:
        raise AIUnavailable('invalid_glb_json') from exc
    if not isinstance(doc, dict):
        raise AIUnavailable('invalid_glb_json')
    for key in ('skins', 'meshes', 'nodes', 'images', 'buffers'):
        if key in doc and (not isinstance(doc[key], list) or not all(isinstance(item, dict) for item in doc[key])):
            raise AIUnavailable('invalid_glb_structure')
    if not doc.get('skins') or not doc.get('meshes') or not doc.get('nodes') or not doc.get('images'):
        raise AIUnavailable('glb_requires_textured_rigged_mesh')
    if any('uri' in item for key in ('images', 'buffers') for item in doc.get(key, [])):
        raise AIUnavailable('glb_external_resources_rejected')
    if not any('skin' in node and 'mesh' in node for node in doc['nodes']):
        raise AIUnavailable('glb_missing_skinned_node')
    for mesh in doc['meshes']:
        primitives = mesh.get('primitives', [])
        if not isinstance(primitives, list) or not all(isinstance(item, dict) and isinstance(item.get('attributes', {}), dict) for item in primitives):
            raise AIUnavailable('invalid_glb_structure')
        if not any('JOINTS_0' in primitive.get('attributes', {}) and 'WEIGHTS_0' in primitive.get('attributes', {}) for primitive in mesh.get('primitives', [])):
            raise AIUnavailable('glb_missing_skin_weights')
    return doc


def run_once(db, settings, gateway):
    timestamp = service.utcnow()
    with db.connect() as c:
        job = c.execute("SELECT j.*,p.owner_id FROM ai_jobs j JOIN pets p ON p.id=j.pet_id WHERE j.kind='evolution' AND j.status IN ('queued','dispatching','running') AND (lease_until IS NULL OR lease_until<%s) ORDER BY j.created_at,j.id FOR UPDATE OF j SKIP LOCKED LIMIT 1", (timestamp,)).fetchone()
        if not job:
            # Read-triggered reconciliation also works without this scheduler. Here it catches downtime for idle pets.
            pets = c.execute('SELECT * FROM pets ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 100').fetchall()
            for p in pets:
                service.refresh(c, p, timestamp, settings.chat_available(p['owner_id']))
            return False
        c.execute("UPDATE ai_jobs SET status=CASE WHEN status='queued' THEN 'dispatching' ELSE status END,lease_until=%s,attempts=attempts+1,updated_at=%s WHERE id=%s",
                  (timestamp + timedelta(seconds=max(60, settings.ai_timeout * 3)), timestamp, job['id']))
    # The claim transaction has committed before network requests and downloads start.
    try:
        is_test = db.ready()['environment'] == 'test'
        method = 'GET' if job['status'] in ('running', 'dispatching') else 'PUT'
        result, provenance = gateway.call('evolutions', job['id'], job['pet_id'], job['input'], job['owner_id'], is_test, method=method)
        asset = None
        if result['status'] == 'succeeded':
            if provenance == 'synthetic':
                raise AIUnavailable('synthetic_completed_asset_rejected')
            asset = gateway.asset(result['model_url'], result['model_sha256'], result['size_bytes'])
            validate_glb(asset)
        with db.connect() as c:
            p = c.execute('SELECT * FROM pets WHERE id=%s AND owner_id=%s FOR UPDATE', (job['pet_id'], job['owner_id'])).fetchone()
            if not p:
                return True  # Privacy deletion wins over a late remote result.
            current = c.execute('SELECT * FROM ai_jobs WHERE id=%s FOR UPDATE', (job['id'],)).fetchone()
            if not current:
                return True
            if current['status'] in ('succeeded', 'failed', 'unsupported'):
                return True
            c.execute('UPDATE ai_jobs SET status=%s,result=%s,error=%s,lease_until=%s,updated_at=%s WHERE id=%s',
                      (result['status'], Jsonb(result), result.get('error'), timestamp + timedelta(seconds=10), timestamp, job['id']))
            if asset is not None:
                c.execute('INSERT INTO model_assets(job_id,pet_id,stage,sha256,data) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                          (job['id'], job['pet_id'], result['stage'], result['model_sha256'], asset))
                saved = c.execute('SELECT state FROM game_states WHERE pet_id=%s', (job['pet_id'],)).fetchone()['state']
                latest = c.execute("SELECT max((input->>'stage')::int) AS stage FROM ai_jobs WHERE pet_id=%s AND kind='evolution'", (job['pet_id'],)).fetchone()['stage']
                if result['stage'] == latest and result['stage'] > saved.get('published_model_stage', 0):
                    saved.update(published_model_stage=result['stage'], model_reference=f"/pets/{job['pet_id']}/assets/{job['id']}", asset_status='ready', previous_evolution=job['input']['profile'])
                    c.execute('UPDATE game_states SET state=%s WHERE pet_id=%s', (Jsonb(saved), job['pet_id']))
                    service.refresh(c, p, timestamp, settings.chat_available(p['owner_id']), True, 'evolution_published')
        return True
    except AIUnavailable as exc:
        with db.connect() as c:
            # A timeout after dispatch is uncertain: poll the same ID instead of creating a second generation.
            c.execute('UPDATE ai_jobs SET status=%s,error=%s,lease_until=%s,updated_at=%s WHERE id=%s AND status NOT IN (\'succeeded\',\'failed\',\'unsupported\')',
                      ('running' if exc.retryable else 'failed', exc.code, timestamp + timedelta(seconds=30), timestamp, job['id']))
        return True
