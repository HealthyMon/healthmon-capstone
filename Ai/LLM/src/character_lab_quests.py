"""Deterministic daily quests and catalog-backed mini quests for the sandbox.

Helpers have no model, database, clock, or network dependency. The caller owns
transactions and authentication. Synchronization creates or expires quest
instances; it never accepts/completes a quest or awards EXP.
"""
from __future__ import annotations

import copy
import json
import math
from datetime import date
from pathlib import Path

from .persona_quests import catalog_by_id, validate_quest_evidence


POLICY = json.loads((Path(__file__).resolve().parents[1] /
                     'config/character_quest_policy.json').read_text(encoding='utf-8'))
QUEST_POLICY = POLICY
OPEN_STATUSES = {'created', 'accepted', 'in_progress'}
UNITS = {'steps': 'step', 'minutes': 'minute', 'records': 'record',
         'foods': 'record', 'groups': 'record'}


def _day(value):
    if isinstance(value, date):
        return value.isoformat()
    return date.fromisoformat(value).isoformat()


def daily_quest_id(on_date):
    return f'daily:walk_6000:{_day(on_date)}'


def mini_quest_id(catalog_id, on_date):
    if catalog_id not in catalog_by_id():
        raise ValueError('Unknown catalog mini quest')
    return f'mini:{catalog_id}:{_day(on_date)}'


def daily_quest_payload(on_date):
    day, cfg = _day(on_date), POLICY['daily']
    return {'action': 'create', 'quest_id': daily_quest_id(day),
            'quest_scope': 'daily', 'catalog_id': cfg['catalog_id'],
            'quest_type': 'exercise', 'title': cfg['title'],
            'target': cfg['target'], 'target_value': cfg['target_value'],
            'unit': cfg['unit'], 'reward_exp': cfg['reward_exp'],
            'start_date': day, 'due_date': day,
            'verification_method': 'exercise_record', 'character_proposal': False}


def catalog_candidate_to_payload(candidate, quest_id, on_date):
    """Convert an already selected fixed catalog goal into a real create payload.

    The caller must select again from current state/history before calling this
    function. A supplied model/browser goal cannot replace the catalog goal.
    Novel food metrics remain catalog-backed and are never reduced to row counts.
    """
    catalog_id = candidate.get('quest_id')
    known = catalog_by_id().get(catalog_id)
    if not known or any(candidate.get(key) != known[key] for key in
                        ('title', 'category', 'activity', 'goal', 'verification_method', 'reward_id')):
        raise ValueError('Unknown or modified catalog quest candidate')
    if not isinstance(quest_id, str) or not 1 <= len(quest_id) <= 100:
        raise ValueError('Quest instance ID must be a bounded string')
    day = _day(on_date)
    return {'action': 'create', 'quest_id': quest_id, 'quest_scope': 'mini',
            'catalog_id': catalog_id, 'quest_type': known['category'],
            'title': known['title'], 'target': known['activity'],
            'target_value': known['goal']['target'], 'unit': UNITS[known['goal']['unit']],
            'reward_exp': POLICY['mini_reward_exp'][catalog_id],
            'start_date': day, 'due_date': day,
            'verification_method': 'exercise_record' if known['category'] == 'exercise' else 'food_record',
            'character_proposal': True}


def validate_generated_quest_payload(payload):
    """Reject forged generated goals/rewards before the engine creates them."""
    scope = payload.get('quest_scope', 'custom')
    if scope == 'custom':
        if payload['quest_id'].startswith(('daily:', 'mini:')):
            raise ValueError('Generated quest instance prefixes are reserved')
        return
    if not payload.get('start_date'):
        raise ValueError('Generated quests require an explicit start date')
    if scope == 'daily':
        expected = daily_quest_payload(payload['start_date'])
    elif scope == 'mini':
        catalog_id = payload.get('catalog_id')
        known = catalog_by_id().get(catalog_id)
        if not known:
            raise ValueError('Unknown catalog mini quest')
        expected = catalog_candidate_to_payload(known, mini_quest_id(catalog_id, payload['start_date']),
                                                payload['start_date'])
    else:
        raise ValueError('Unknown generated quest scope')
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError('Generated quest payload does not match authoritative policy')


def sync_quests(lab, on_date=None):
    """Create today's daily quest once and expire overdue open instances.

    Operates on the caller's isolated session copy. Returns auditable changes;
    Created quests expire; accepted quests fail. Helpers pay no reward or Mood
    change; the engine may apply its existing failure Mood rule once.
    Rejected/completed/failed quests are preserved. Calling twice is a no-op.
    """
    day = _day(on_date or lab['state']['virtual_test_date'])
    payload = daily_quest_payload(day)
    quests = lab['quests']
    existing = quests.get(payload['quest_id'])
    if existing and any(existing.get(key) != payload[key] for key in
                        ('quest_scope', 'catalog_id', 'quest_type', 'title', 'target', 'target_value',
                         'unit', 'reward_exp', 'start_date', 'due_date',
                         'verification_method', 'character_proposal')):
        raise ValueError('Reserved daily quest ID conflicts with a different quest')
    audit = []
    for qid, quest in quests.items():
        if quest['status'] in OPEN_STATUSES and quest['due_date'] < day:
            previous = quest['status']
            current = 'expired' if previous == 'created' else 'failed'
            quest.update(status=current, resolved_date=day)
            audit.append({'quest_id': qid, 'action': 'expire', 'before_status': previous,
                          'after_status': current, 'previous_status': previous, 'current_status': current,
                          'on_date': day, 'quest': copy.deepcopy(quest), 'reward_paid': False,
                          'applied_rule': 'provisional:quest_expiry',
                          'reason': 'Due date passed; unaccepted expires, accepted fails; no reward',
                          'policy_version': POLICY['version']})
    if not existing:
        quest = dict(payload, status='created', created_date=day, progress_value=0,
                     reward_paid=False, accepted_date=None, resolved_date=None,
                     accepted_event_index=None)
        quests[payload['quest_id']] = quest
        audit.append({'quest_id': payload['quest_id'], 'action': 'create',
                      'before_status': None, 'after_status': 'created', 'on_date': day,
                      'previous_status': None, 'current_status': 'created',
                      'quest': copy.deepcopy(quest), 'reward_paid': False,
                      'applied_rule': 'daily:user_requested_6000_steps',
                      'reason': 'Create one user-requested 6000-step daily quest for this virtual date',
                      'policy_version': POLICY['version']})
    return audit


def _unique_records(lab):
    seen = set()
    for index, event in enumerate(lab['events']):
        ident = event.get('event_id')
        if not isinstance(ident, str) or not ident or ident in seen:
            continue
        seen.add(ident)
        yield index, event


def _amount(payload):
    amount = payload.get('actual', 0)
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount):
        return 0
    return max(0, amount)


def _walking(name):
    return name in {'walk', 'walking', '걷기'}


def _catalog_records(lab, q):
    """Map test evidence into the existing trusted synthetic catalog contract."""
    records, earlier = [], []
    accepted_index = q.get('accepted_event_index')
    if accepted_index is None or q.get('accepted_date') is None:
        return records, earlier
    for index, event in _unique_records(lab):
        p, kind = event['payload'], event['kind']
        day = event['virtual_test_date']
        if day > min(q['due_date'], lab['state']['virtual_test_date']):
            continue
        if kind == 'exercise' and p.get('verification_status') == 'verified':
            payload = {'exercise_type': p['exercise_type'], 'amount': _amount(p),
                       'unit': {'step': 'steps', 'minute': 'minutes', 'count': 'counts'}.get(p['unit'])}
            event_type = 'exercise_recorded'
        elif kind == 'food' and event.get('result', {}).get('review_required', True) is False:
            # Unknown food groups are deliberately not fabricated from nutrition labels.
            payload = {'food_name': p.get('raw_text', ''), 'food_group': 'unknown'}
            event_type = 'food_recorded'
        else:
            continue
        row = {'event_id': event['event_id'], 'idempotency_key': event['event_id'],
               'event_type': event_type, 'source': 'simulation',
               'verification_status': 'verified', 'confidence': 1, 'payload': payload}
        if index < accepted_index:
            earlier.append(row)
        elif index > accepted_index and q['accepted_date'] <= day and (
                kind == 'exercise' and p.get('quest_id') == q['quest_id'] or
                kind == 'food' and event.get('result', {}).get('quest_evidence_used') in (None, q['quest_id'])):
            records.append(row)
    return records, earlier


def verified_progress(lab, q):
    """Return verified incremental quantity, with catalog novelty checks intact.

    Daily steps include pre-acceptance records on that date. Exercise mini quests
    require the exact instance link and records after acceptance. This helper
    cannot complete a quest or award rewards; transition validation remains in
    the engine. Quantities can exceed a target so the UI can show true totals.
    """
    scope = q.get('quest_scope', 'custom')
    if scope == 'daily':
        expected = daily_quest_payload(q['start_date'])
        if any(q.get(key) != expected[key] for key in
               ('quest_id', 'catalog_id', 'quest_type', 'target', 'target_value', 'unit',
                'reward_exp', 'due_date', 'verification_method', 'character_proposal')):
            raise ValueError('Modified daily quest goal')
        return sum(_amount(event['payload']) for _, event in _unique_records(lab)
                   if event['kind'] == 'exercise' and event['virtual_test_date'] == q['start_date']
                   and event['virtual_test_date'] <= lab['state']['virtual_test_date']
                   and event['payload'].get('verification_status') == 'verified'
                   and _walking(event['payload'].get('exercise_type'))
                   and event['payload'].get('unit') == 'step')
    if scope == 'mini':
        known = catalog_by_id().get(q.get('catalog_id'))
        if not known:
            raise ValueError('Unknown catalog mini quest')
        expected = catalog_candidate_to_payload(known, q['quest_id'], q['start_date'])
        if any(q.get(key) != expected[key] for key in
               ('quest_type', 'target', 'target_value', 'unit', 'due_date',
                'verification_method', 'reward_exp', 'character_proposal')):
            raise ValueError('Modified catalog mini quest goal')
        records, earlier = _catalog_records(lab, q)
        metric = known['goal']['metric']
        if metric in {'steps', 'minutes'}:
            unit = known['goal']['unit']
            total = sum(row['payload']['amount'] for row in records
                        if row['event_type'] == 'exercise_recorded'
                        and row['payload']['exercise_type'] == known['activity']
                        and row['payload']['unit'] == unit)
        elif metric == 'records':
            total = sum(bool(row['payload'].get('food_name', '').strip()) for row in records
                        if row['event_type'] == 'food_recorded')
        elif metric == 'new_foods':
            names = {row['payload'].get('food_name', '').strip().casefold() for row in records
                     if row['event_type'] == 'food_recorded'} - {''}
            prior = {row['payload'].get('food_name', '').strip().casefold() for row in earlier
                     if row['event_type'] == 'food_recorded'}
            total = len(names - prior)
        else:
            # No food group field exists in this Lab evidence contract yet.
            total = 0
        if total and validate_quest_evidence(known, records, earlier,
                                           min(total / known['goal']['target'], 1)):
            return total
        return 0
    # Custom quests retain the original explicit/admin progress engine.
    return q.get('progress_value', 0) * q['target_value']


def quest_view(lab):
    """Stable game-facing quest data; a model's offer is never completion."""
    result = []
    for qid, q in sorted(lab['quests'].items()):
        actual = verified_progress(lab, q)
        result.append({'quest_id': qid, 'catalog_id': q.get('catalog_id'),
                       'quest_scope': q.get('quest_scope', 'custom'),
                       'title': q['title'], 'quest_type': q['quest_type'],
                       'status': q['status'], 'goal': {'activity': q['target'],
                       'target': q['target_value'], 'unit': q['unit']},
                       'progress': {'verified_value': actual, 'target_value': q['target_value'],
                                    'ratio': min(1, actual / q['target_value'])},
                       'start_date': q['start_date'], 'due_date': q['due_date'],
                       'reward': {'exp': q['reward_exp'], 'paid': q['reward_paid']},
                       'character_proposal': q['character_proposal'],
                       'can_accept': q['status'] == 'created' and
                           q['start_date'] <= lab['state']['virtual_test_date'] <= q['due_date'],
                       'can_complete': q['status'] in {'accepted', 'in_progress'} and
                           lab['state']['virtual_test_date'] <= q['due_date'] and actual >= q['target_value'],
                       'policy_version': POLICY['version']})
    return result
