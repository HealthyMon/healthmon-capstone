"""Source erasure with immutable game aggregates and no raw-data resurrection.

After the 24h score revision window, erasing private input freezes its *game
contribution*, not its health data: retained rows contain numeric game deltas
and anonymous game-order/body-score metadata. Meal interactions already applied
are frozen as a delta offset; erased ingredients are never reconstructed.
"""
from datetime import timedelta
import uuid

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from . import rules


def _owner_lock(c, p):
    row = c.execute('SELECT * FROM pets WHERE id=%s AND owner_id=%s FOR UPDATE', (p['id'], p['owner_id'])).fetchone()
    if row is None:
        raise HTTPException(404, 'Pet not found')
    return row


def load_retained(c, pet):
    retained = {'daily': {}, 'weekly': {}}
    for row in c.execute('SELECT period,period_start,adjustment FROM game_retained_scores WHERE pet_id=%s', (pet,)):
        retained[row['period']][row['period_start'].isoformat()] = row['adjustment']
    return retained


def _retain(c, pet, period, day, adjustment):
    c.execute('INSERT INTO game_retained_scores(pet_id,period,period_start,adjustment,rule_version) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(pet_id,period,period_start) DO UPDATE SET adjustment=excluded.adjustment,rule_version=excluded.rule_version',
              (pet, period, day, Jsonb(adjustment), rules.RULE_VERSION))


def invalidate_dependencies(c, pet, source_ids=(), memory_ids=()):
    """Invalidate only caches that actually depended on erased private inputs."""
    source_ids, memory_ids = list(source_ids), list(memory_ids)
    affected = {row['request_id'] for row in c.execute('SELECT request_id FROM exchanges WHERE pet_id=%s AND (source_id=ANY(%s::text[]) OR memory_ids ?| %s::text[])', (pet, source_ids, memory_ids))}
    affected.update(row['id'] for row in c.execute('SELECT id FROM requests WHERE pet_id=%s AND (dependency_source_ids ?| %s::text[] OR dependency_memory_ids ?| %s::text[])', (pet, source_ids, memory_ids)))
    direct_requests = [ident[len('message:'):] for ident in source_ids if ident.startswith('message:')]
    affected.update(row['id'] for row in c.execute('SELECT id FROM requests WHERE pet_id=%s AND id=ANY(%s::text[])', (pet, direct_requests)))
    if affected:
        identifiers = list(affected)
        c.execute("UPDATE requests SET status='invalidated',result=NULL,ai_input=NULL,lease_until=NULL,lease_token=NULL,dependency_source_ids='[]',dependency_memory_ids='[]' WHERE pet_id=%s AND id=ANY(%s::text[])", (pet, identifiers))
        c.execute("UPDATE exchanges SET valid=false,speech='',memory_ids='[]',state_used='{}',state_after='{}' WHERE pet_id=%s AND request_id=ANY(%s::text[])", (pet, identifiers))
    return len(affected)


def delete_source(c, p, source_id, expected_revision, now, settings):
    """Erase any-age source, preserving paid rewards and old game contribution.

    The caller owns the transaction. ``expected_revision`` prevents erasing a
    concurrently edited source based on a stale UI. The source ID remains only
    as an empty technical tombstone so the same upload ID cannot resurrect it.
    """
    from . import service
    from .quests import proposals, sync_quests
    now = rules._instant(now)
    p = _owner_lock(c, p)
    pet = p['id']
    row = c.execute('SELECT * FROM sources WHERE pet_id=%s AND id=%s FOR UPDATE', (pet, source_id)).fetchone()
    if row is None:
        raise HTTPException(404, 'Source not found')
    if row['revision'] != expected_revision:
        raise HTTPException(409, 'Source revision changed')
    if row['payload'].get('_privacy_erased'):
        state, _ = service.refresh(c, p, now, settings.chat_available(p['owner_id']))
        return {'source_id': source_id, 'deleted': True, 'duplicate': True, 'state': state,
                'state_version': state['state_version'], 'score_recalculated': False}
    before, original = service.refresh(c, p, now, settings.chat_available(p['owner_id']))
    retained = load_retained(c, pet)
    occurred = row['occurred_at']
    old_score = now - occurred > timedelta(hours=24)
    kind = row['payload'].get('_game_kind')
    data = row['payload'].get('data', {})
    memory_ids = [item['id'] for item in c.execute('SELECT id FROM memories WHERE pet_id=%s AND source_id=%s', (pet, source_id))]
    invalidated = invalidate_dependencies(c, pet, [source_id], memory_ids)
    c.execute('DELETE FROM memories WHERE pet_id=%s AND source_id=%s', (pet, source_id))
    c.execute('DELETE FROM source_revisions WHERE pet_id=%s AND source_id=%s', (pet, source_id))
    c.execute('DELETE FROM suggestion_jobs WHERE pet_id=%s AND source_id=%s', (pet, source_id))
    c.execute('DELETE FROM outbox WHERE pet_id=%s AND source_id=%s', (pet, source_id))
    analysis_ids = [data['analysis_id']] if isinstance(data, dict) and data.get('analysis_id') else []
    if source_id.startswith('food-'):
        analysis_ids.append(source_id[5:])
    c.execute("UPDATE food_analyses SET result=%s,confirmation=NULL,erased_at=%s WHERE pet_id=%s AND (id=ANY(%s::text[]) OR confirmation->>'source_id'=%s)",
              (Jsonb({'_privacy_erased': True}), now, pet, analysis_ids, source_id))
    # Erase original times and fingerprint, not only payload. The game date lives
    # in aggregate rows if a frozen contribution is required.
    evaluation = original['evaluations'].get(source_id, {})
    body_key = uuid.uuid4().hex if old_score and kind == 'workout' and evaluation.get('evaluation_status') == 'evaluated' else None
    tombstone = {'_privacy_erased': True, 'data': {'_game_anchor_key': body_key} if body_key else {}}
    if kind is not None:
        tombstone['_game_kind'] = kind
    c.execute("UPDATE sources SET valid=false,payload=%s,fingerprint=NULL,evaluation_status='erased',occurred_at=%s,received_at=%s,session_id=NULL WHERE pet_id=%s AND id=%s",
              (Jsonb(tombstone), now, now, pet, source_id))
    remaining = service.events(c, pet)
    sync_quests(c, pet, remaining, now, settings.chat_available(p['owner_id']))
    if old_score:
        day = rules._day(occurred).isoformat()
        if body_key:
            adjustment = dict(retained['daily'].get(day, {}))
            body_events = list(adjustment.get('body_events', []))
            body_events.append({'key': body_key, 'at': rules._instant(occurred).isoformat(),
                                'score': evaluation['score'], 'body_part': evaluation['body_part'],
                                'performed': evaluation['actual_workout'],
                                'missed': evaluation['confirmed_nonperformance']})
            adjustment['body_events'] = body_events
            _retain(c, pet, 'daily', day, adjustment)
            retained['daily'][day] = adjustment
        erased = rules.replay(remaining, now, proposals(c, pet), retained=retained)
        original_day = next((entry for entry in original['daily'] if entry['date'] == day), {})
        erased_day = next((entry for entry in erased['daily'] if entry['date'] == day), {})
        axes = ('upper_body', 'lower_body', 'nutrition', 'energy_balance')
        change = {axis: original_day.get('raw_deltas', {}).get(axis, 0) - erased_day.get('raw_deltas', {}).get(axis, 0) for axis in axes}
        if any(change.values()):
            adjustment = dict(retained['daily'].get(day, {}))
            adjustment.update({axis: adjustment.get(axis, 0) + change[axis] for axis in axes})
            _retain(c, pet, 'daily', day, adjustment)
            retained['daily'][day] = adjustment
        # Only weeks already applied at the deletion instant are frozen. The
        # current unfinished week no longer derives future personality from data
        # which the user erased before that weekly calculation.
        erased = rules.replay(remaining, now, proposals(c, pet), retained=retained)
        previous_weeks = {entry['week_start']: entry for entry in erased['weekly']}
        axes = ('activity', 'affinity', 'initiative')
        for week in original['weekly']:
            key = week['week_start']
            new = previous_weeks.get(key, {})
            change = {axis: week['deltas'].get(axis, 0) - new.get('deltas', {}).get(axis, 0) for axis in axes}
            if any(change.values()):
                adjustment = {axis: retained['weekly'].get(key, {}).get(axis, 0) + change[axis] for axis in axes}
                _retain(c, pet, 'weekly', key, adjustment)
                retained['weekly'][key] = adjustment
    # Purge old aggregates carrying derived dietary totals/classifier counts;
    # refresh writes only fresh aggregates plus retained game contribution data.
    c.execute('DELETE FROM game_daily WHERE pet_id=%s', (pet,))
    c.execute('DELETE FROM game_weekly WHERE pet_id=%s', (pet,))
    state, _ = service.refresh(c, p, now, settings.chat_available(p['owner_id']), True, 'privacy_erasure')
    return {'source_id': source_id, 'deleted': True, 'duplicate': False,
            'score_recalculated': not old_score, 'retained_game_contribution': old_score,
            'invalidated_requests': invalidated, 'state': state, 'state_version': state['state_version']}


def delete_memory(c, p, memory_id, now=None):
    p = _owner_lock(c, p)
    row = c.execute('SELECT id FROM memories WHERE pet_id=%s AND id=%s FOR UPDATE', (p['id'], memory_id)).fetchone()
    if row is None:
        raise HTTPException(404, 'Memory not found')
    invalidated = invalidate_dependencies(c, p['id'], memory_ids=[memory_id])
    c.execute('DELETE FROM memories WHERE pet_id=%s AND id=%s', (p['id'], memory_id))
    return {'memory_id': memory_id, 'deleted': True, 'invalidated_requests': invalidated}


def delete_pet(c, p, now=None):
    """Permanently purge all data for this authenticated owner's pet."""
    p = _owner_lock(c, p)
    pet = p['id']
    # Fixed server-owned table names; FK-dependent legacy rows go first.
    tables = ('model_assets', 'ai_jobs', 'food_analyses', 'exchanges', 'memories', 'suggestion_jobs',
              'outbox', 'source_revisions', 'sources', 'reward_ledger', 'quest_offers',
              'requests', 'state_snapshots', 'workout_goals', 'game_ledger', 'game_daily',
              'game_weekly', 'game_states', 'common_chat_sessions', 'game_proposal_controls',
              'game_rest_days', 'game_retained_scores')
    for table in tables:
        c.execute(f'DELETE FROM {table} WHERE pet_id=%s', (pet,))
    c.execute('DELETE FROM pets WHERE id=%s AND owner_id=%s', (pet, p['owner_id']))
    return {'pet_id': pet, 'deleted': True}
