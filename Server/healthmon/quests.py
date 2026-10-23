"""Persisted v2.2 quest slots and real, optional character proposals.

No recommendation AI is introduced: basic candidate selection is a stable hash.
Caller transactions provide ownership validation; these functions lock the pet
row, never commit, and use unique reward keys to make retries atomic. A proposal
is an opportunity only after the client acknowledges an actual display.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timedelta

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from . import rules

_SPECS = {
    "easy": {"candidates": ("meal1", "workout1", "chat1"), "exp": 30, "coin": 10},
    "medium": {"candidates": ("meal2", "workout70", "meal_workout"), "exp": 50, "coin": 20},
    "weekly": {"candidates": ("workout_days3", "meal_days5", "daily6"), "exp": 160, "coin": 60},
}
_TARGETS = {"meal1": 1, "workout1": 1, "chat1": 1, "meal2": 2, "workout70": 1,
            "meal_workout": 2, "workout_days3": 3, "meal_days5": 5, "daily6": 6}
_WORKOUT_CANDIDATES = {"workout1", "workout70", "meal_workout"}


def _lock(c, pet):
    row = c.execute('SELECT id,created_at FROM pets WHERE id=%s FOR UPDATE', (pet,)).fetchone()
    if row is None:
        raise HTTPException(404, 'Pet not found')
    return row


def _eligible(events, now):
    now = rules._instant(now)
    result = []
    seen = set()
    for event in events:
        ident = str(event['event_id'])
        if ident in seen:
            continue
        seen.add(ident)
        if event.get('valid', True) is not True or event.get('deleted'):
            continue
        occurred, received = rules._instant(event['occurred_at']), rules._instant(event['received_at'])
        if occurred <= now and received <= now and rules.eligibility(occurred, received) == 'eligible':
            result.append(event)
    return sorted(result, key=lambda e: (rules._instant(e['occurred_at']), str(e['event_id'])))


def candidate_progress(candidate, events, completed_daily=0):
    """Return progress and real evidence. Call with eligible, period-scoped events.

    Main meal constituents share a day/slot; snacks only earn record EXP. Missing
    workout measurements never satisfy a quest simply because actual was set.
    """
    if candidate not in _TARGETS:
        raise ValueError('Unknown v2.2 quest candidate')
    workouts, meals, chats = [], {}, []
    for event in events:
        payload = event['payload']
        if event['kind'] == 'workout' and rules.workout_delta(payload)['actual_workout']:
            workouts.append(event)
        elif event['kind'] == 'meal':
            evaluated = rules.meal_delta(payload)
            if evaluated['reward_eligible'] and evaluated['meal_type'] in {'breakfast', 'lunch', 'dinner'}:
                meals.setdefault((rules._day(event['occurred_at']), evaluated['meal_type']), event)
        elif event['kind'] == 'chat' and payload.get('normal') is True and isinstance(payload.get('text'), str) and payload['text'].strip():
            chats.append(event)
    meal_events = list(meals.values())
    chosen = []
    if candidate == 'meal1':
        chosen = meal_events[:1]
        progress = len(chosen)
    elif candidate == 'workout1':
        chosen = workouts[:1]
        progress = len(chosen)
    elif candidate == 'chat1':
        chosen = chats[:1]
        progress = len(chosen)
    elif candidate == 'meal2':
        chosen = meal_events[:2]
        progress = len(chosen)
    elif candidate == 'workout70':
        chosen = [e for e in workouts if rules.workout_delta(e['payload'])['achievement_rate'] >= 70][:1]
        progress = len(chosen)
    elif candidate == 'meal_workout':
        chosen = meal_events[:1] + workouts[:1]
        progress = len(chosen)
    elif candidate in {'workout_days3', 'meal_days5'}:
        by_day = {}
        for event in workouts if candidate == 'workout_days3' else meal_events:
            by_day.setdefault(rules._day(event['occurred_at']), event)
        chosen = list(by_day.values())[:_TARGETS[candidate]]
        progress = len(chosen)
    else:
        progress = min(6, max(0, int(completed_daily)))
    chosen = sorted(chosen, key=lambda e: (rules._instant(e['occurred_at']), str(e['event_id'])))
    return {'progress': progress, 'target': _TARGETS[candidate],
            'complete': progress >= _TARGETS[candidate],
            'event_ids': [str(e['event_id']) for e in chosen],
            'completed_at': rules._instant(chosen[-1]['occurred_at']) if chosen and progress >= _TARGETS[candidate] else None}


def _available(slot, ai_available, rest_day=False):
    return [candidate for candidate in _SPECS[slot]['candidates']
            if (ai_available or candidate != 'chat1') and (not rest_day or candidate not in _WORKOUT_CANDIDATES)]


def _choose(pet, start, slot, candidates, replacement=0):
    if not candidates:
        return None
    value = hashlib.sha256(f'{pet}:{start}:{slot}:{replacement}'.encode()).hexdigest()
    return candidates[int(value, 16) % len(candidates)]


def _template(pet, start, slot, ai_available, rest_day=False):
    candidate = _choose(pet, start, slot, _available(slot, ai_available, rest_day))
    if candidate is None:
        return None
    return {'candidate': candidate, 'target': _TARGETS[candidate],
            'exp': _SPECS[slot]['exp'], 'coin': _SPECS[slot]['coin'],
            'policy': 'deterministic.v2.2', 'basic_quest': True,
            'selection_note': 'Stable hash is a technical selection policy, not an AI recommendation.',
            'history': []}


def proposals(c, pet):
    """Return authoritative proposal evidence for personality replay.

    Rejected offers remain opportunities. Basic quest slots are never included.
    The shown-at timestamp, rather than generation time, starts the real 24h.
    """
    rows = c.execute('SELECT * FROM quest_offers WHERE pet_id=%s AND is_proposal ORDER BY created_at,id', (pet,)).fetchall()
    return [dict(row, proposal_id=row['id'], shown=row['shown_at'] is not None,
                 created_at=row['shown_at'] or row['created_at'], deadline=row['expires_at'],
                 valid=not row['excluded'], cancelled=row.get('cancelled_at') is not None,
                 rest=row['template'].get('rest', False), unavailable=row['template'].get('unavailable', False),
                 acceptance_supported=True) for row in rows]


def _replace_unavailable(c, row, now, ai_available, rest_day):
    slot, original = row['slot'], row['template']
    available = _available(slot, ai_available, rest_day)
    if (row['status'] in {'completed', 'rejected'} or row['replacement_count'] >= 1
            or original.get('candidate') in available or now >= row['expires_at'] + timedelta(hours=24)):
        return row
    chosen = _choose(row['pet_id'], row['period_start'], slot, available, replacement=1)
    if chosen is None:
        return row
    history = list(original.get('history', []))
    history.append({'candidate': original['candidate'], 'replaced_at': now.isoformat(),
                    'reason': 'rest_day' if rest_day else 'dependency_unavailable'})
    updated = dict(original, candidate=chosen, target=_TARGETS[chosen], history=history)
    c.execute('UPDATE quest_offers SET template=%s,replacement_count=replacement_count+1,progress=0 WHERE pet_id=%s AND id=%s',
              (Jsonb(updated), row['pet_id'], row['id']))
    return dict(row, template=updated, replacement_count=row['replacement_count'] + 1, progress=0)


def sync_quests(c, pet, valid_events, timestamp, ai_available):
    """Reconcile basic slots and accepted real proposals in one caller transaction.

    A day/week owns one immutable instance per difficulty. Late arrivals may
    complete their occurrence period during the 24h grace; a later restart still
    recovers events first received in time. Expiration creates no score penalty.
    """
    timestamp = rules._instant(timestamp)
    _lock(c, pet)
    events = _eligible(valid_events, timestamp)
    today = rules._day(timestamp)
    rest_days = {row['day'] for row in c.execute('SELECT day FROM game_rest_days WHERE pet_id=%s', (pet,)).fetchall()}
    # Existing legacy pets do not accumulate years of invented retroactive slots.
    # Earliest persisted common-server slot anchors subsequent downtime recovery.
    # A weekly slot starts on Monday even if the first server visit is later.
    # It cannot anchor daily downtime recovery before that first visit.
    anchor = c.execute("SELECT min(period_start) AS day FROM quest_offers WHERE pet_id=%s AND slot IN ('easy','medium')", (pet,)).fetchone()['day']
    first = min([today] + ([anchor] if anchor is not None else []) + [rules._day(e['occurred_at']) for e in events])
    day = first
    while day <= today:
        for slot in _SPECS:
            start = rules._monday(day) if slot == 'weekly' else day
            deadline = rules._midnight(start + timedelta(days=7 if slot == 'weekly' else 1))
            template = _template(pet, start, slot, ai_available, day in rest_days and slot != 'weekly')
            if template is None:
                continue
            ident = 'basic:' + hashlib.sha256(f'{pet}:{start}:{slot}'.encode()).hexdigest()[:40]
            c.execute("INSERT INTO quest_offers(pet_id,id,template,status,state_version,created_at,expires_at,slot,period_start,is_proposal) VALUES(%s,%s,%s,'active',0,%s,%s,%s,%s,false) ON CONFLICT DO NOTHING",
                      (pet, ident, Jsonb(template), timestamp, deadline, slot, start))
        day += timedelta(days=1)
    rows = c.execute("SELECT * FROM quest_offers WHERE pet_id=%s AND slot IS NOT NULL ORDER BY CASE WHEN slot='weekly' THEN 1 ELSE 0 END,period_start,id FOR UPDATE", (pet,)).fetchall()
    for row in rows:
        if row['status'] in {'completed', 'rejected'}:
            continue
        row = _replace_unavailable(c, row, timestamp, ai_available, row['period_start'] in rest_days and row['slot'] != 'weekly')
        start = rules._midnight(row['period_start'])
        end = row['expires_at']
        scoped = [e for e in events if start <= rules._instant(e['occurred_at']) < end
                  and rules._instant(e['received_at']) < end + timedelta(hours=24)]
        completed_daily = c.execute("SELECT count(*) AS n FROM quest_offers WHERE pet_id=%s AND slot IN ('easy','medium') AND status='completed' AND period_start>=%s AND period_start<%s",
                                    (pet, row['period_start'], rules._day(end))).fetchone()['n']
        progress = candidate_progress(row['template']['candidate'], scoped, completed_daily)
        done = progress['complete']
        status = 'completed' if done else 'expired' if timestamp >= end + timedelta(hours=24) else 'active'
        c.execute('UPDATE quest_offers SET progress=%s,status=%s,completed_at=%s,completion_verified=%s,completion_event_id=%s WHERE pet_id=%s AND id=%s',
                  (progress['progress'], status, progress['completed_at'] or (timestamp if done else None), done,
                   progress['event_ids'][-1] if progress['event_ids'] else None, pet, row['id']))
        if done:
            spec = _SPECS[row['slot']]
            c.execute('INSERT INTO game_ledger(pet_id,reward_key,exp,coin,reason,source_id) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                      (pet, 'quest:' + row['id'], spec['exp'], spec['coin'], row['slot'] + '_quest',
                       progress['event_ids'][-1] if progress['event_ids'] else None))
    # Only actual accepted, displayed proposals use the acceptance completion path.
    actual = c.execute("SELECT * FROM quest_offers WHERE pet_id=%s AND is_proposal AND status IN ('accepted','completed') FOR UPDATE", (pet,)).fetchall()
    for row in actual:
        if row['excluded'] or row['shown_at'] is None or row['accepted_at'] is None or row.get('cancelled_at') is not None:
            continue
        scoped = [e for e in events if row['accepted_at'] <= rules._instant(e['occurred_at']) < row['expires_at']
                  and rules._instant(e['received_at']) < row['expires_at'] + timedelta(hours=24)]
        candidate = row['template'].get('candidate')
        if candidate not in _TARGETS or candidate == 'daily6':
            continue
        progress = candidate_progress(candidate, scoped)
        if progress['complete']:
            c.execute("UPDATE quest_offers SET status='completed',progress=%s,completed_at=%s,completion_verified=true,completion_event_id=%s WHERE pet_id=%s AND id=%s",
                      (progress['progress'], progress['completed_at'], progress['event_ids'][-1], pet, row['id']))
        else:
            # Preserve acceptance after expiry so a delayed event can reconcile.
            c.execute("UPDATE quest_offers SET status='accepted',progress=%s,completed_at=NULL,completion_verified=false,completion_event_id=NULL WHERE pet_id=%s AND id=%s",
                      (progress['progress'], pet, row['id']))
    if not ai_available:
        # Complete verified prior events first; only currently actionable chat
        # opportunities lose availability. History/rejections/other activities
        # keep their original evidence. A later recovery never revives this row.
        c.execute("""UPDATE quest_offers SET excluded=true,cancelled_at=%s,
                     template=jsonb_set(template,'{unavailable}','true'::jsonb)
                     WHERE pet_id=%s AND is_proposal AND template->>'candidate'='chat1'
                     AND status IN ('offered','active','accepted') AND completed_at IS NULL
                     AND NOT completion_verified AND NOT excluded AND cancelled_at IS NULL
                     AND created_at<=%s AND (shown_at IS NULL OR shown_at<=%s)
                     AND expires_at>%s""", (timestamp, pet, timestamp, timestamp, timestamp))


def proposal_availability(state, visible_proposals, now, rest_until=None, stopped_until=None):
    """Pure display gate. Only real visible, non-excluded opportunities count."""
    now = rules._instant(now)
    if rest_until is not None and now < rules._instant(rest_until):
        return {'allowed': False, 'reason': 'rest_requested', 'next_at': rules._instant(rest_until).isoformat()}
    if stopped_until is not None and now < rules._instant(stopped_until):
        return {'allowed': False, 'reason': 'proposals_stopped', 'next_at': rules._instant(stopped_until).isoformat()}
    policy = rules.proposal_policy(state['initiative'])
    day = rules._day(now)
    period_start = rules._midnight(rules._monday(day) if policy['period'] == 'week' else day)
    shown = sorted(rules._instant(item['shown_at']) for item in visible_proposals
                   if item.get('shown_at') is not None and item.get('is_proposal', True)
                   and not item.get('excluded', False) and item.get('cancelled_at') is None
                   and rules._instant(item['shown_at']) <= now)
    if shown:
        minimum = shown[-1] + timedelta(hours=policy['minimum_hours'])
        if now < minimum:
            return {'allowed': False, 'reason': 'minimum_interval', 'next_at': minimum.isoformat()}
    if sum(instant >= period_start for instant in shown) >= policy['limit']:
        next_day = rules._monday(day) + timedelta(days=7) if policy['period'] == 'week' else day + timedelta(days=1)
        return {'allowed': False, 'reason': 'period_limit', 'next_at': rules._midnight(next_day).isoformat()}
    return {'allowed': True, 'reason': 'available', 'next_at': now.isoformat(), 'policy': policy}


def _gate(c, pet, state, now):
    controls = c.execute('SELECT * FROM game_proposal_controls WHERE pet_id=%s', (pet,)).fetchone() or {}
    rows = c.execute('SELECT shown_at,is_proposal,excluded,cancelled_at FROM quest_offers WHERE pet_id=%s AND is_proposal AND shown_at IS NOT NULL', (pet,)).fetchall()
    return proposal_availability(state, rows, now, controls.get('rest_until'), controls.get('stopped_until'))


def create_proposal(c, p, template, now, state=None, shown=False):
    """Create a deterministic/manual proposal; show explicitly after UI delivery.

    Proposal completion changes personality evidence, with no additional reward
    category invented beyond the specified basic quest rewards.
    """
    now, pet = rules._instant(now), p['id']
    _lock(c, pet)
    candidate = template.get('candidate')
    if candidate not in _TARGETS or candidate == 'daily6':
        raise HTTPException(422, 'Unsupported proposal candidate')
    request_id = template.get('request_id')
    ident = 'proposal:' + hashlib.sha256(str(request_id).encode()).hexdigest()[:40] if request_id else uuid.uuid4().hex
    existing = c.execute('SELECT * FROM quest_offers WHERE pet_id=%s AND id=%s', (pet, ident)).fetchone()
    if existing:
        if existing['template']['candidate'] != candidate:
            raise HTTPException(409, 'Proposal request ID content conflict')
        if shown and existing['shown_at'] is None:
            return mark_proposal_shown(c, p, ident, now, state)
        return dict(existing, duplicate=True)
    stored = c.execute('SELECT state FROM game_states WHERE pet_id=%s', (pet,)).fetchone()
    state = state or (stored['state'] if stored else rules.initial_state())
    gate = _gate(c, pet, state, now)
    if not gate['allowed']:
        raise HTTPException(409, gate)
    safe = {'candidate': candidate, 'target': _TARGETS[candidate], 'basic_quest': False,
            'policy': 'optional-proposal.v2.2', 'request_id': request_id, 'generated_at': now.isoformat(),
            'exp': 0, 'coin': 0}
    c.execute("INSERT INTO quest_offers(pet_id,id,template,status,state_version,created_at,expires_at,is_proposal) VALUES(%s,%s,%s,'offered',%s,%s,%s,true)",
              (pet, ident, Jsonb(safe), p.get('version', 0), now, now + timedelta(hours=24)))
    return mark_proposal_shown(c, p, ident, now, state) if shown else c.execute('SELECT * FROM quest_offers WHERE pet_id=%s AND id=%s', (pet, ident)).fetchone()


def mark_proposal_shown(c, p, offer_id, now, state=None):
    now, pet = rules._instant(now), p['id']
    _lock(c, pet)
    row = c.execute('SELECT * FROM quest_offers WHERE pet_id=%s AND id=%s FOR UPDATE', (pet, offer_id)).fetchone()
    if row is None:
        raise HTTPException(404, 'Proposal not found')
    if not row['is_proposal'] or row['excluded'] or row.get('cancelled_at') is not None:
        raise HTTPException(409, 'Offer is not an available character proposal')
    if row['shown_at'] is not None:
        return dict(row, duplicate=True)
    stored = c.execute('SELECT state FROM game_states WHERE pet_id=%s', (pet,)).fetchone()
    state = state or (stored['state'] if stored else rules.initial_state())
    gate = _gate(c, pet, state, now)
    if not gate['allowed']:
        raise HTTPException(409, gate)
    return c.execute("UPDATE quest_offers SET shown_at=%s,expires_at=%s,status='active' WHERE pet_id=%s AND id=%s RETURNING *",
                     (now, now + timedelta(hours=24), pet, offer_id)).fetchone()


def quest_decision(c, p, offer_id, decision, now):
    now, pet = rules._instant(now), p['id']
    if decision not in {'accept', 'reject'}:
        raise HTTPException(422, 'Decision must be accept or reject')
    _lock(c, pet)
    row = c.execute('SELECT * FROM quest_offers WHERE pet_id=%s AND id=%s FOR UPDATE', (pet, offer_id)).fetchone()
    if row is None:
        raise HTTPException(404, 'Quest not found')
    timestamp = row['accepted_at'] if decision == 'accept' else row.get('rejected_at')
    if timestamp is not None:
        return dict(row, duplicate=True)
    if row['excluded'] or row.get('cancelled_at') is not None or now >= row['expires_at']:
        raise HTTPException(409, 'Quest is unavailable or its decision window has expired')
    if row['status'] in {'completed', 'rejected'} or row['accepted_at'] is not None:
        raise HTTPException(409, 'Quest already has a different final decision')
    if row['is_proposal'] and row['shown_at'] is None:
        raise HTTPException(409, 'Proposal must actually be shown before a decision')
    status, column = ('accepted', 'accepted_at') if decision == 'accept' else ('rejected', 'rejected_at')
    # column is selected from the two fixed server constants above.
    return c.execute(f'UPDATE quest_offers SET status=%s,{column}=%s WHERE pet_id=%s AND id=%s RETURNING *',
                     (status, now, pet, offer_id)).fetchone()


def set_proposal_control(c, pet, action, now):
    now = rules._instant(now)
    _lock(c, pet)
    if action not in {'rest_today', 'stop_7_days', 'resume'}:
        raise HTTPException(422, 'Unknown proposal control')
    c.execute('INSERT INTO game_proposal_controls(pet_id) VALUES(%s) ON CONFLICT DO NOTHING', (pet,))
    if action == 'rest_today':
        until = rules._midnight(rules._day(now) + timedelta(days=1))
        c.execute('UPDATE game_proposal_controls SET rest_until=%s,updated_at=%s WHERE pet_id=%s', (until, now, pet))
        c.execute('INSERT INTO game_rest_days(pet_id,day) VALUES(%s,%s) ON CONFLICT DO NOTHING', (pet, rules._day(now)))
        # Rest interrupts only the remaining, live workout opportunity. Preserve
        # completed/expired decisions and their historical personality evidence;
        # the existing cancelled/rest exclusions handle future O/A/C replay.
        c.execute("""UPDATE quest_offers
                     SET excluded=true,cancelled_at=%s,
                         template=jsonb_set(template,'{rest}','true'::jsonb,true)
                     WHERE pet_id=%s AND is_proposal
                       AND template->>'candidate'=ANY(%s::text[])
                       AND status IN ('offered','active','accepted')
                       AND NOT excluded AND cancelled_at IS NULL
                       AND completed_at IS NULL AND NOT completion_verified
                       AND created_at<=%s AND (shown_at IS NULL OR shown_at<=%s)
                       AND expires_at>%s""",
                  (now, pet, sorted(_WORKOUT_CANDIDATES), now, now, now))
    elif action == 'stop_7_days':
        c.execute('UPDATE game_proposal_controls SET stopped_until=%s,updated_at=%s WHERE pet_id=%s', (now + timedelta(days=7), now, pet))
    else:
        c.execute('UPDATE game_proposal_controls SET stopped_until=NULL,updated_at=%s WHERE pet_id=%s', (now, pet))
    return c.execute('SELECT * FROM game_proposal_controls WHERE pet_id=%s', (pet,)).fetchone()
