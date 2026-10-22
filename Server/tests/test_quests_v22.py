"""Pure policy plus opt-in real PostgreSQL transaction tests for v2.2 quests."""
from datetime import datetime, timedelta
import uuid

from fastapi import HTTPException
import pytest
from psycopg.types.json import Jsonb

from healthmon import quests as q, rules as r


def now(day=22, hour=12):
    return datetime(2026, 10, day, hour, tzinfo=r.KST)


def workout(actual=30, **extra):
    return {'exercise_type': 'running', 'actual': actual, 'target': 30,
            'unit': 'minutes', 'body_part': 'lower', **extra}


def meal(slot='breakfast', **extra):
    return {'food_name': 'confirmed meal', 'confirmed': True, 'quantity_confirmed': True,
            'meal_type': slot, 'carbohydrate_g': None, 'protein_g': None,
            'fat_g': None, 'vegetable_fruit_g': None, **extra}


def event(ident, kind='workout', payload=None, when=None, **extra):
    timestamp = when or now()
    return {'event_id': ident, 'kind': kind, 'payload': workout() if payload is None else payload,
            'occurred_at': timestamp, 'received_at': timestamp, 'valid': True, **extra}


def visible(timestamp, **extra):
    return {'shown_at': timestamp, 'is_proposal': True, 'excluded': False, 'cancelled_at': None, **extra}


def test_meal2_requires_two_distinct_main_meal_bundles():
    events = [event('a', 'meal', meal()), event('b', 'meal', meal())]
    assert q.candidate_progress('meal2', events)['progress'] == 1
    events.append(event('snack', 'meal', meal('snack')))
    assert q.candidate_progress('meal2', events)['progress'] == 1
    events.append(event('lunch', 'meal', meal('lunch')))
    assert q.candidate_progress('meal2', events)['complete'] is True


@pytest.mark.parametrize('payload', [workout(actual=None), workout(actual=0), workout(target=None),
    workout(unit='steps'), workout(exercise_type='cycle')])
def test_insufficient_or_zero_workout_never_completes_actual_workout_quest(payload):
    assert q.candidate_progress('workout1', [event('a', payload=payload)])['progress'] == 0


@pytest.mark.parametrize('amount,complete', [(20.999, False), (21, True), (30, True)])
def test_workout70_uses_valid_real_measurement(amount, complete):
    assert q.candidate_progress('workout70', [event('a', payload=workout(amount))])['complete'] is complete


def test_quest_evidence_and_completion_time_comes_from_actual_events():
    events = [event('meal', 'meal', meal(), now(hour=8)), event('workout', when=now(hour=10))]
    progress = q.candidate_progress('meal_workout', events)
    assert progress['event_ids'] == ['meal', 'workout']
    assert progress['completed_at'] == now(hour=10)


def test_weekly_candidates_count_days_and_daily6_counts_instances():
    events = [event('a'), event('b')]
    assert q.candidate_progress('workout_days3', events)['progress'] == 1
    events += [event('c', when=now(23)), event('d', when=now(24))]
    assert q.candidate_progress('workout_days3', events)['complete'] is True
    assert q.candidate_progress('daily6', events, 5)['complete'] is False
    assert q.candidate_progress('daily6', events, 6)['complete'] is True


def test_chat_requires_real_normal_text_and_not_just_classification():
    bad = [event('blank', 'chat', {'normal': True, 'text': '  '}),
           event('error', 'chat', {'normal': False, 'text': 'AI unavailable'})]
    assert q.candidate_progress('chat1', bad)['progress'] == 0
    assert q.candidate_progress('chat1', bad + [event('ok', 'chat', {'normal': True, 'text': 'hello'})])['complete'] is True


def test_eligible_filter_excludes_invalid_future_and_late_and_deduplicates():
    item = event('ok')
    events = [item, item, event('invalid', valid=False), event('future', when=now(23)),
              event('late', received_at=now() + timedelta(hours=24, microseconds=1))]
    assert [e['event_id'] for e in q._eligible(events, now(24))] == ['ok', 'future']
    assert [e['event_id'] for e in q._eligible(events, now())] == ['ok']


def test_candidate_assignment_is_deterministic_and_respects_availability_and_rest():
    first = q._template('pet', now().date(), 'easy', True)
    assert q._template('pet', now().date(), 'easy', True) == first
    assert q._template('pet', now().date(), 'easy', False)['candidate'] in {'meal1', 'workout1'}
    assert q._template('pet', now().date(), 'easy', False, rest_day=True)['candidate'] == 'meal1'
    assert q._template('pet', now().date(), 'medium', False, rest_day=True)['candidate'] == 'meal2'
    assert q._template('pet', now().date(), 'weekly', True)['exp'] == 160


@pytest.mark.parametrize('initiative,earlier,hours', [(39, now(21), 24), (40, now(hour=4), 8), (70, now(hour=8), 4)])
def test_proposal_interval_exact_boundary(initiative, earlier, hours):
    state = {**r.initial_state(), 'initiative': initiative}
    shown = [visible(earlier)]
    assert q.proposal_availability(state, shown, earlier + timedelta(hours=hours, microseconds=-1))['reason'] == 'minimum_interval'
    assert q.proposal_availability(state, shown, earlier + timedelta(hours=hours))['allowed'] is (initiative != 40)
    # Middle initiative has one per day; its exact interval may still hit quota.


def test_weekly_and_daily_quotas_are_kst_and_rejections_still_count():
    low = {**r.initial_state(), 'initiative': 39}
    shown = [visible(now(19), status='rejected'), visible(now(20)), visible(now(21))]
    assert q.proposal_availability(low, shown, now(22))['reason'] == 'period_limit'
    assert q.proposal_availability(low, shown, now(26))['allowed'] is True
    high = {**r.initial_state(), 'initiative': 70}
    shown = [visible(now(hour=0)), visible(now(hour=4))]
    assert q.proposal_availability(high, shown, now())['reason'] == 'period_limit'
    assert q.proposal_availability(high, shown, now(23, 0))['allowed'] is True


def test_hidden_cancelled_and_basic_quests_do_not_use_proposal_quota():
    state = {**r.initial_state(), 'initiative': 50}
    shown = [visible(None), visible(now(), excluded=True), visible(now(), cancelled_at=now()),
             visible(now(), is_proposal=False)]
    assert q.proposal_availability(state, shown, now())['allowed'] is True


def test_rest_until_midnight_and_stop_seven_day_boundaries():
    state = r.initial_state()
    assert q.proposal_availability(state, [], now(), rest_until=now(23, 0))['reason'] == 'rest_requested'
    assert q.proposal_availability(state, [], now(23, 0), rest_until=now(23, 0))['allowed'] is True
    until = now() + timedelta(days=7)
    assert q.proposal_availability(state, [], until - timedelta(microseconds=1), stopped_until=until)['reason'] == 'proposals_stopped'
    assert q.proposal_availability(state, [], until, stopped_until=until)['allowed'] is True


@pytest.fixture
def pg(db):
    """Real PostgreSQL only: never silently substitute SQLite or a fake DB."""
    with db.connect() as c:
        ident = 'quest-test-' + uuid.uuid4().hex
        p = {'id': ident, 'owner_id': 'quest-test-owner', 'version': 0, 'created_at': now()}
        c.execute('INSERT INTO pets(id,owner_id,settings,created_at) VALUES(%s,%s,%s,%s)', (ident, p['owner_id'], Jsonb({}), now()))
        try:
            yield c, p
        finally:
            c.rollback()


def test_pg_slots_ledger_are_unique_and_basic_quests_not_proposals(pg):
    c, p = pg
    events = [event('workout'), event('breakfast', 'meal', meal()),
              event('lunch', 'meal', meal('lunch')), event('chat', 'chat', {'normal': True, 'text': 'hello'})]
    q.sync_quests(c, p['id'], events, now(), True)
    rows = c.execute('SELECT * FROM quest_offers WHERE pet_id=%s', (p['id'],)).fetchall()
    assert len(rows) == 3 and all(row['is_proposal'] is False for row in rows)
    assert q.proposals(c, p['id']) == []
    rewards = c.execute('SELECT * FROM game_ledger WHERE pet_id=%s', (p['id'],)).fetchall()
    assert sorted((row['exp'], row['coin']) for row in rewards) == [(30, 10), (50, 20)]
    q.sync_quests(c, p['id'], list(reversed(events)), now(), True)
    assert c.execute('SELECT count(*) AS n FROM game_ledger WHERE pet_id=%s', (p['id'],)).fetchone()['n'] == 2


def test_pg_late_grace_and_downtime_completion_without_failure_penalty(pg):
    c, p = pg
    q.sync_quests(c, p['id'], [], now(), False)
    row = c.execute("SELECT * FROM quest_offers WHERE pet_id=%s AND slot='easy'", (p['id'],)).fetchone()
    c.execute("UPDATE quest_offers SET template=jsonb_set(template,'{candidate}','\"workout1\"') WHERE pet_id=%s AND id=%s", (p['id'], row['id']))
    delayed = event('late', when=now(22, 23), received_at=now(23, 22))
    q.sync_quests(c, p['id'], [delayed], now(25), False)
    completed = c.execute('SELECT * FROM quest_offers WHERE pet_id=%s AND id=%s', (p['id'], row['id'])).fetchone()
    assert completed['status'] == 'completed' and completed['completion_verified'] is True
    assert c.execute('SELECT sum(exp) AS exp FROM game_ledger WHERE pet_id=%s', (p['id'],)).fetchone()['exp'] >= 30
    # Expiration is a status only; no negative ledger or personality event exists.
    assert c.execute('SELECT count(*) AS n FROM game_ledger WHERE pet_id=%s AND (exp<0 OR coin<0)', (p['id'],)).fetchone()['n'] == 0


def test_pg_outage_replaces_same_slot_once_and_preserves_history(pg):
    c, p = pg
    q.sync_quests(c, p['id'], [], now(), True)
    row = c.execute("SELECT * FROM quest_offers WHERE pet_id=%s AND slot='easy'", (p['id'],)).fetchone()
    c.execute("UPDATE quest_offers SET template=jsonb_set(template,'{candidate}','\"chat1\"') WHERE pet_id=%s AND id=%s", (p['id'], row['id']))
    q.sync_quests(c, p['id'], [], now(), False)
    replaced = c.execute('SELECT * FROM quest_offers WHERE pet_id=%s AND id=%s', (p['id'], row['id'])).fetchone()
    assert replaced['replacement_count'] == 1
    assert replaced['template']['candidate'] in {'meal1', 'workout1'}
    assert replaced['template']['history'][0]['candidate'] == 'chat1'
    q.sync_quests(c, p['id'], [], now(), False)
    assert c.execute('SELECT replacement_count FROM quest_offers WHERE pet_id=%s AND id=%s', (p['id'], row['id'])).fetchone()['replacement_count'] == 1


def test_pg_real_shown_rejection_remains_opportunity_and_is_idempotent(pg):
    c, p = pg
    row = q.create_proposal(c, p, {'candidate': 'workout1', 'request_id': 'test-rejected'}, now())
    assert row['shown_at'] is None
    with pytest.raises(HTTPException, match='shown'):
        q.quest_decision(c, p, row['id'], 'reject', now())
    q.mark_proposal_shown(c, p, row['id'], now())
    rejected = q.quest_decision(c, p, row['id'], 'reject', now())
    assert rejected['rejected_at'] == now()
    assert q.quest_decision(c, p, row['id'], 'reject', now())['duplicate'] is True
    proposal = q.proposals(c, p['id'])[0]
    assert proposal['cancelled'] is False and proposal['valid'] is True
    assert r._proposal_counts([proposal], now(19).date(), now(26).date()) == (1, 0, 0, 1)


def test_pg_accepted_proposal_only_actual_post_acceptance_completion_and_no_extra_reward(pg):
    c, p = pg
    row = q.create_proposal(c, p, {'candidate': 'workout1', 'request_id': 'test-completion'}, now(), shown=True)
    q.quest_decision(c, p, row['id'], 'accept', now())
    before = event('before', when=now(hour=11))
    q.sync_quests(c, p['id'], [before], now(hour=13), False)
    proposal = q.proposals(c, p['id'])[0]
    assert proposal['completion_verified'] is False
    after = event('after', when=now(hour=14))
    q.sync_quests(c, p['id'], [before, after], now(hour=15), False)
    proposal = q.proposals(c, p['id'])[0]
    assert proposal['completion_verified'] is True and proposal['completed_at'] == now(hour=14)
    assert r._proposal_counts([proposal], now(19).date(), now(26).date()) == (1, 1, 1, 0)
    assert c.execute('SELECT count(*) AS n FROM game_ledger WHERE pet_id=%s AND reward_key=%s', (p['id'], 'quest:' + row['id'])).fetchone()['n'] == 0


def test_pg_rest_stop_controls_persist_and_resume_does_not_cancel_rest(pg):
    c, p = pg
    control = q.set_proposal_control(c, p['id'], 'rest_today', now())
    assert control['rest_until'] == now(23, 0)
    q.set_proposal_control(c, p['id'], 'stop_7_days', now())
    q.set_proposal_control(c, p['id'], 'resume', now())
    row = c.execute('SELECT * FROM game_proposal_controls WHERE pet_id=%s', (p['id'],)).fetchone()
    assert row['stopped_until'] is None and row['rest_until'] == now(23, 0)
    q.sync_quests(c, p['id'], [], now(), False)
    rows = c.execute("SELECT template FROM quest_offers WHERE pet_id=%s AND slot IN ('easy','medium')", (p['id'],)).fetchall()
    assert {row['template']['candidate'] for row in rows} == {'meal1', 'meal2'}
    with pytest.raises(HTTPException):
        q.create_proposal(c, p, {'candidate': 'workout1'}, now(), shown=True)
