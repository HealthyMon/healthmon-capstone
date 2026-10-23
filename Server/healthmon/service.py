"""Atomic event processing using the existing pets/sources/snapshot ownership model."""
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from . import rules
from .quests import proposals, sync_quests


def utcnow():
    return datetime.now(timezone.utc)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(',', ':')).encode()).hexdigest()


def owned(c, owner, pet, lock=False):
    row = c.execute('SELECT * FROM pets WHERE id=%s AND owner_id=%s' + (' FOR UPDATE' if lock else ''), (pet, owner)).fetchone()
    if not row:
        raise HTTPException(404, 'Pet not found')
    return row


def ensure_state(c, pet):
    c.execute('INSERT INTO game_states(pet_id,state,rule_version) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',
              (pet, Jsonb(rules.initial_state()), rules.RULE_VERSION))


def events(c, pet):
    rows = c.execute("SELECT * FROM sources WHERE pet_id=%s AND payload ? '_game_kind' ORDER BY occurred_at,id", (pet,)).fetchall()
    return [{'event_id': r['id'], 'kind': r['payload']['_game_kind'], 'payload': r['payload']['data'],
             'occurred_at': r['occurred_at'], 'received_at': r['received_at'], 'valid': r['valid']} for r in rows]


def seed_goals(c, pet, timestamp):
    for exercise, goal in rules.DEFAULT_GOALS.items():
        c.execute('INSERT INTO workout_goals(pet_id,id,exercise_type,target,unit,body_part,effective_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                  (pet, uuid.uuid4().hex, exercise, goal['target'], goal['unit'], goal['body_part'], timestamp))


def normalized_exercise(name):
    return {'walk': 'walking', 'run': 'running', 'push_up': 'pushup', 'squats': 'squat', 'lunges': 'lunge', 'cycling': 'cycle', 'stretching': 'stretch'}.get(name.lower(), name.lower())


def normalize_workout(c, pet, raw):
    payload = dict(raw)
    exercise = normalized_exercise(raw['workout_type'])
    instant = raw.get('started_at') or raw['occurred_at']
    if raw.get('goal_id'):
        goal = c.execute('SELECT * FROM workout_goals WHERE pet_id=%s AND id=%s AND effective_at<=%s AND exercise_type=%s',
                         (pet, raw['goal_id'], instant, exercise)).fetchone()
    else:
        goal = c.execute('SELECT * FROM workout_goals WHERE pet_id=%s AND exercise_type=%s AND effective_at<=%s ORDER BY effective_at DESC,id DESC LIMIT 1',
                         (pet, exercise, instant)).fetchone()
    payload['exercise_type'] = exercise
    payload['goal_snapshot'] = dict(goal) if goal else None
    if goal:
        if raw.get('target') is not None and raw['target'] != goal['target']:
            raise HTTPException(409, 'Submitted target differs from the saved goal effective at exercise start')
        payload['target'], payload['body_part'] = goal['target'], goal['body_part']
        payload['goal_confirmed_before_start'] = exercise in rules.DEFAULT_GOALS or exercise == 'full_body'
        # Preserve missing/wrong measured units for recorded_unscored evaluation.
    else:
        payload['target'] = None
    if raw.get('confirmed_nonperformance'):
        payload['nonperformance_confirmed'] = True
    # Claims identify reporting provenance, not cryptographic sensor verification.
    payload['provenance'] = {'reported_source': raw['source'], 'verification': 'user_confirmed' if raw['source'] == 'user' else 'device_reported', 'sensor_integrity_verified': False}
    if payload['goal_snapshot']:
        payload['goal_snapshot']['effective_at'] = payload['goal_snapshot']['effective_at'].isoformat()
        payload['goal_snapshot']['created_at'] = payload['goal_snapshot']['created_at'].isoformat()
    return payload


def refresh(c, p, timestamp, ai_available=False, force=False, reason='period_reconciliation'):
    pet = p['id']
    ensure_state(c, pet)
    stored = c.execute('SELECT * FROM game_states WHERE pet_id=%s', (pet,)).fetchone()
    data = events(c, pet)
    eligible = [e for e in data if e['valid'] and rules.eligibility(e['occurred_at'], e['received_at']) == 'eligible']
    sync_quests(c, pet, eligible, timestamp, ai_available)
    from .privacy import load_retained
    projection = rules.replay(data, timestamp, proposals(c, pet), retained=load_retained(c, pet))
    for reward in projection['reward_candidates']:
        c.execute('INSERT INTO game_ledger(pet_id,reward_key,exp,coin,reason,source_id) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                  (pet, reward['reward_key'], reward['exp'], reward.get('coin', 0), reward['reason'], reward.get('event_id')))
    total = c.execute('SELECT coalesce(sum(exp),0) AS exp,coalesce(sum(coin),0) AS coin FROM game_ledger WHERE pet_id=%s', (pet,)).fetchone()
    state = dict(projection['state'], **rules.exp_progress(total['exp']))
    state.update(pet_id=pet, coin=total['coin'], rule_version=rules.RULE_VERSION, settings=p['settings'])
    test_controls = stored['state'].get('_test_controls')
    if test_controls and c.execute('SELECT environment FROM common_server_metadata WHERE singleton').fetchone()['environment'] == 'test':
        for axis, offset in test_controls['offsets'].items():
            if axis in ('upper_body', 'lower_body', 'nutrition', 'energy_balance', 'activity', 'affinity', 'initiative'):
                state[axis] = max(-100 if axis == 'energy_balance' else 0, min(100, state[axis] + offset))
        state.update(rules.exp_progress(max(0, total['exp'] + test_controls['exp_offset'])))
        state['coin'] = max(0, total['coin'] + test_controls['coin_offset'])
        state['_test_controls'] = test_controls
        state['synthetic_test_state'] = True
    for key, default in [('published_model_stage', 0), ('model_reference', None), ('asset_status', 'unavailable'), ('previous_evolution', None)]:
        state[key] = stored['state'].get(key, default)
    state['evolution_target_stage'] = rules.evolution_profile(state)['stage']
    state['evolution_profile'] = rules.evolution_profile(state, state.get('previous_evolution'))
    state['trend'] = projection['trend']
    key = fingerprint(state)
    version = p['version']
    if force or key != stored['projection_hash']:
        version = c.execute('UPDATE pets SET version=version+1 WHERE id=%s RETURNING version', (pet,)).fetchone()['version']
        c.execute('UPDATE game_states SET state=%s,projection_hash=%s,rule_version=%s,updated_at=%s WHERE pet_id=%s', (Jsonb(state), key, rules.RULE_VERSION, timestamp, pet))
        c.execute('INSERT INTO state_snapshots(pet_id,version,state) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING', (pet, version, Jsonb(dict(state, reason=reason))))
    for day in projection['daily']:
        c.execute('INSERT INTO game_daily(pet_id,day,summary,rule_version) VALUES(%s,%s,%s,%s) ON CONFLICT(pet_id,day) DO UPDATE SET summary=excluded.summary,rule_version=excluded.rule_version',
                  (pet, day['date'], Jsonb(day), rules.RULE_VERSION))
    for week in projection['weekly']:
        c.execute('INSERT INTO game_weekly(pet_id,week_start,summary,rule_version) VALUES(%s,%s,%s,%s) ON CONFLICT(pet_id,week_start) DO UPDATE SET summary=excluded.summary,rule_version=excluded.rule_version',
                  (pet, week['week_start'], Jsonb(week), rules.RULE_VERSION))
    return dict(state, state_version=version), projection


def store_event(c, p, kind, raw, payload, timestamp, settings):
    pet, ident = p['id'], raw['event_id']
    if raw.get('synthetic') and not (settings.environment == 'test' and p['owner_id'] in settings.test_owners):
        raise HTTPException(403, 'Synthetic events require a test owner and test database')
    if raw['occurred_at'] > timestamp:
        raise HTTPException(422, 'Future event cannot be applied')
    old = c.execute('SELECT * FROM sources WHERE pet_id=%s AND id=%s', (pet, ident)).fetchone()
    key = fingerprint(raw)
    if old:
        if old['payload'].get('_privacy_erased'):
            raise HTTPException(410, 'Event was erased and cannot be resurrected')
        if raw.get('synthetic', False) != old['synthetic']:
            raise HTTPException(409, 'Event synthetic provenance is fixed by its first record')
        if raw['revision'] == old['revision'] and key == old['fingerprint']:
            if not old['valid']:
                raise HTTPException(410, 'Event was deleted')
            state, _ = refresh(c, p, timestamp, settings.chat_available(p['owner_id']))
            return dict(event_id=ident, revision=old['revision'], duplicate=True, stored=True, evaluation_status=old['evaluation_status'], state_version=state['state_version'], state=state)
        if raw['revision'] != old['revision'] + 1:
            raise HTTPException(409, 'Event ID content conflict; increment revision explicitly')
        if timestamp - old['occurred_at'] > timedelta(hours=24) or raw['occurred_at'] != old['occurred_at']:
            raise HTTPException(409, 'Ordinary score revisions are limited to 24 hours and the original event time')
        previous_kind = old['payload'].get('_game_kind') or ('chat' if old['kind'] == 'message' else None)
        if previous_kind != kind:
            raise HTTPException(409, 'Event kind cannot change')
    elif raw['revision'] != 1:
        raise HTTPException(409, 'New events must begin at revision 1')
    received = old['received_at'] if old else timestamp
    wrapper = {'_game_kind': kind, 'data': payload, '_raw': raw}
    c.execute("INSERT INTO sources(pet_id,id,kind,revision,occurred_at,received_at,payload,valid,fingerprint,synthetic) VALUES(%s,%s,%s,%s,%s,%s,%s,true,%s,%s) ON CONFLICT(pet_id,id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload,valid=true,fingerprint=excluded.fingerprint",
              (pet, ident, 'message' if kind == 'chat' else 'activity', raw['revision'], raw['occurred_at'], received, Jsonb(json.loads(json.dumps(wrapper, default=str))), key, raw.get('synthetic', False)))
    c.execute('INSERT INTO source_revisions(pet_id,source_id,revision,raw_payload,changed_at) VALUES(%s,%s,%s,%s,%s)',
              (pet, ident, raw['revision'], Jsonb(json.loads(json.dumps(raw, default=str))), timestamp))
    if old:
        memory_ids = [r['id'] for r in c.execute('SELECT id FROM memories WHERE pet_id=%s AND source_id=%s', (pet, ident))]
        c.execute("UPDATE memories SET valid=false,content='[invalidated]',embedding=NULL WHERE pet_id=%s AND source_id=%s", (pet, ident))
        from .privacy import invalidate_dependencies
        invalidate_dependencies(c, pet, [ident], memory_ids)
    state, projection = refresh(c, p, timestamp, settings.chat_available(p['owner_id']), True, kind + ':' + ident)
    evaluation = projection['evaluations'].get(ident, {})
    status = evaluation.get('evaluation_status', evaluation.get('status', rules.eligibility(raw['occurred_at'], received)))
    c.execute('UPDATE sources SET evaluation_status=%s WHERE pet_id=%s AND id=%s', (status, pet, ident))
    return dict(event_id=ident, revision=raw['revision'], duplicate=False, stored=True, evaluation_status=status, evaluation=evaluation, state_version=state['state_version'], state=state)
