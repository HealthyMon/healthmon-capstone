"""Daily/mini quest contracts use finite synthetic evidence and no GPU or DB."""
import copy
import json
from pathlib import Path

import pytest

from src.character_lab_schema import Session
from src.character_lab_quests import (
    POLICY, catalog_candidate_to_payload, daily_quest_id, daily_quest_payload,
    mini_quest_id, quest_view, sync_quests, validate_generated_quest_payload,
    verified_progress,
)
from src.persona_quests import catalog_by_id

DAY = '2026-10-04'


def lab():
    return Session().model_dump(mode='json')


def mini(catalog_id='walk_100'):
    candidate = catalog_by_id()[catalog_id]
    return dict(catalog_candidate_to_payload(candidate, mini_quest_id(catalog_id, DAY), DAY),
                status='accepted', created_date=DAY, accepted_date=DAY,
                accepted_event_index=0, resolved_date=None, progress_value=0,
                reward_paid=False)


def exercise(ident, amount=100, quest_id=None, **changes):
    p = {'exercise_type': 'walk', 'actual': amount, 'target': 100,
         'unit': 'step', 'verification_status': 'verified', 'quest_id': quest_id, **changes}
    return {'event_id': ident, 'kind': 'exercise', 'virtual_test_date': DAY,
            'payload': p, 'result': {'verified_behavior': p['verification_status'] == 'verified'}}


def food(ident, name, **result):
    return {'event_id': ident, 'kind': 'food', 'virtual_test_date': DAY,
            'payload': {'raw_text': name}, 'result': {'review_required': False, **result}}


def accept_record(quest):
    return {'event_id': 'accept', 'kind': 'quest', 'virtual_test_date': DAY,
            'payload': {'quest_id': quest['quest_id'], 'action': 'accept'}, 'result': {}}


def test_daily_6000_created_once_without_acceptance_or_reward():
    session = lab()
    before = copy.deepcopy(session['state'])
    audit = sync_quests(session)
    q = session['quests'][daily_quest_id(DAY)]
    assert len(audit) == 1 and audit[0]['action'] == 'create'
    assert q['target_value'] == 6000 and q['unit'] == 'step'
    assert q['status'] == 'created' and q['character_proposal'] is False
    assert q['accepted_date'] is None and not q['reward_paid']
    assert session['state'] == before
    snapshot = copy.deepcopy(session)
    assert sync_quests(session) == [] and session == snapshot


@pytest.mark.parametrize('status', ['created', 'accepted', 'in_progress'])
def test_next_day_expires_unresolved_and_creates_new_daily(status):
    session = lab()
    sync_quests(session)
    old = session['quests'][daily_quest_id(DAY)]
    old['status'] = status
    session['state']['virtual_test_date'] = '2026-10-05'
    audit = sync_quests(session)
    assert [x['action'] for x in audit] == ['expire', 'create']
    assert old['status'] == ('expired' if status == 'created' else 'failed')
    assert old['resolved_date'] == '2026-10-05'
    assert not old['reward_paid'] and session['state']['mood'] == 0
    assert session['quests'][daily_quest_id('2026-10-05')]['status'] == 'created'


@pytest.mark.parametrize('status', ['rejected', 'completed', 'failed', 'expired'])
def test_terminal_quest_preserved_on_next_day(status):
    session = lab()
    sync_quests(session)
    old = session['quests'][daily_quest_id(DAY)]
    old['status'] = status
    snapshot = copy.deepcopy(old)
    session['state']['virtual_test_date'] = '2026-10-05'
    sync_quests(session)
    assert old == snapshot


def test_reserved_daily_id_conflict_fails_without_mutating():
    session = lab()
    sync_quests(session)
    session['quests'][daily_quest_id(DAY)]['target_value'] = 100
    before = copy.deepcopy(session)
    with pytest.raises(ValueError, match='Reserved'):
        sync_quests(session)
    assert session == before


def test_daily_and_mini_walk_goals_are_independent():
    session = lab()
    sync_quests(session)
    q = mini()
    session['quests'][q['quest_id']] = q
    session['events'] = [accept_record(q), exercise('e', 100, q['quest_id'])]
    rows = {x['quest_scope']: x for x in quest_view(session)}
    assert rows['mini']['goal']['target'] == 100 and rows['mini']['can_complete']
    assert rows['daily']['goal']['target'] == 6000 and not rows['daily']['can_complete']
    assert rows['daily']['progress']['verified_value'] == 100


def test_daily_uses_full_day_records_including_before_acceptance():
    session = lab()
    sync_quests(session)
    q = session['quests'][daily_quest_id(DAY)]
    q.update(status='accepted', accepted_date=DAY, accepted_event_index=1)
    session['events'] = [exercise('before', 5000), accept_record(q), exercise('after', 1000)]
    assert verified_progress(session, q) == 6000
    assert quest_view(session)[0]['can_complete']
    assert not q['reward_paid']


def test_daily_ignores_unverified_wrongunit_wrongactivity_otherdate_duplicates():
    session = lab()
    sync_quests(session)
    q = session['quests'][daily_quest_id(DAY)]
    valid = exercise('valid', 100)
    wrong_date = exercise('other_day', 1000)
    wrong_date['virtual_test_date'] = '2026-10-03'
    session['events'] = [valid, copy.deepcopy(valid), wrong_date,
                         exercise('unverified', 1000, verification_status='user_reported'),
                         exercise('minutes', 1000, unit='minute'),
                         exercise('squat', 1000, exercise_type='squat')]
    assert verified_progress(session, q) == 100


def test_mini_counts_only_linked_evidence_after_acceptance():
    session, q = lab(), mini()
    q['accepted_event_index'] = 1
    session['events'] = [exercise('before', 500, q['quest_id']), accept_record(q),
                         exercise('unlinked', 300), exercise('linked', 50, q['quest_id']),
                         exercise('other', 500, 'another-quest')]
    assert verified_progress(session, q) == 50


def test_mini_completion_needs_acceptance_and_duplicates_do_not_count():
    session, q = lab(), mini()
    row = exercise('e', 50, q['quest_id'])
    session['events'] = [accept_record(q), row, copy.deepcopy(row)]
    assert verified_progress(session, q) == 50
    q['accepted_event_index'] = None
    assert verified_progress(session, q) == 0


@pytest.mark.parametrize('catalog_id', list(catalog_by_id()))
def test_catalog_payload_preserves_exact_goal_unit_and_provisional_reward(catalog_id):
    known = catalog_by_id()[catalog_id]
    payload = catalog_candidate_to_payload(known, mini_quest_id(catalog_id, DAY), DAY)
    assert payload['target_value'] == known['goal']['target']
    assert payload['reward_exp'] == POLICY['mini_reward_exp'][catalog_id]
    assert payload['quest_scope'] == 'mini'
    validate_generated_quest_payload(payload)


@pytest.mark.parametrize('field,value', [('target_value', 100), ('reward_exp', 999),
                                        ('unit', 'minute'), ('character_proposal', True),
                                        ('quest_id', 'custom')])
def test_generated_daily_goals_and_rewards_cannot_be_forged(field, value):
    payload = daily_quest_payload(DAY)
    payload[field] = value
    with pytest.raises(ValueError, match='authoritative'):
        validate_generated_quest_payload(payload)


def test_modified_model_candidate_goal_is_rejected():
    candidate = catalog_by_id()['walk_100']
    candidate['goal']['target'] = 6000
    with pytest.raises(ValueError, match='modified'):
        catalog_candidate_to_payload(candidate, mini_quest_id('walk_100', DAY), DAY)


def test_modified_mini_instance_goal_is_rejected():
    session, q = lab(), mini()
    q['target_value'] = 1
    with pytest.raises(ValueError, match='Modified'):
        verified_progress(session, q)


def test_new_food_requires_novelty_not_simple_count():
    session, q = lab(), mini('new_food_1')
    q['accepted_event_index'] = 1
    session['events'] = [food('prior', '사과'), accept_record(q), food('repeat', '사과')]
    assert verified_progress(session, q) == 0
    session['events'].append(food('new', '샐러드'))
    assert verified_progress(session, q) == 1


def test_food_groups_are_not_inferred_from_nutrition_or_plain_food_counts():
    session, q = lab(), mini('food_groups_2')
    session['events'] = [accept_record(q), food('f1', '닭가슴살'), food('f2', '샐러드')]
    assert verified_progress(session, q) == 0


def test_food_record_requires_approved_analysis_and_unused_evidence():
    session, q = lab(), mini('food_record_1')
    session['events'] = [accept_record(q), food('unknown', '사과', review_required=True),
                         food('used', '닭가슴살', quest_evidence_used='another-quest')]
    assert verified_progress(session, q) == 0
    session['events'].append(food('ok', '샐러드'))
    assert verified_progress(session, q) == 1


def test_custom_reserved_id_rejected_and_regular_custom_preserved():
    with pytest.raises(ValueError, match='reserved'):
        validate_generated_quest_payload({'quest_id': 'mini:walk_100:2026-10-04'})
    validate_generated_quest_payload({'quest_id': 'custom-exercise'})
    session = lab()
    quest = {'target_value': 50, 'progress_value': .5}
    assert verified_progress(session, quest) == 25


def test_quest_view_is_json_compatible_and_does_not_mutate():
    session = lab()
    sync_quests(session)
    before = copy.deepcopy(session)
    rows = quest_view(session)
    assert json.loads(json.dumps(rows, allow_nan=False)) == rows
    assert session == before and rows[0]['reward']['paid'] is False
    assert rows[0]['can_accept'] and not rows[0]['can_complete']


def test_existing_catalog_remains_unchanged():
    catalog = json.loads((Path(__file__).resolve().parents[1] /
                         'config/quest_catalog.json').read_text(encoding='utf-8'))
    assert catalog['version'] == 'persona-quests.v1'
    assert 'daily_walk_6000' not in catalog_by_id(catalog)
    assert catalog_by_id(catalog)['walk_100']['goal']['target'] == 100
