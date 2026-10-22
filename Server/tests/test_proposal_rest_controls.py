"""Rest interrupts live optional workouts, without rewriting past opportunities.

All rows use the suite's new isolated PostgreSQL database and test owner. Direct
SQL below seeds synthetic proposal lifecycle fixtures, not health measurements.
"""
from datetime import datetime, timedelta, timezone

from psycopg.types.json import Jsonb
import pytest

from Server.healthmon import quests, rules


NOW = datetime(2026, 10, 22, 3, tzinfo=timezone.utc)


def row(db, pet, ident):
    with db.connect() as c:
        return c.execute('SELECT * FROM quest_offers WHERE pet_id=%s AND id=%s', (pet, ident)).fetchone()


@pytest.mark.parametrize('candidate,lifecycle', [
    ('workout1', 'offered'), ('workout70', 'active'), ('meal_workout', 'accepted'),
])
def test_rest_cancels_only_remaining_workout_opportunity_and_retry_is_stable(client, pet, db, candidate, lifecycle):
    created = client.post(f'/pets/{pet}/proposals', json={'request_id': 'rest-live-' + candidate, 'candidate': candidate})
    assert created.status_code == 200, created.text
    ident = created.json()['id']
    if lifecycle != 'offered':
        assert client.post(f'/pets/{pet}/proposals/{ident}/shown').status_code == 200
    if lifecycle == 'accepted':
        assert client.post(f'/pets/{pet}/quests/{ident}/decision', json={'decision': 'accept'}).status_code == 200
    before = row(db, pet, ident)
    before_state = client.get(f'/pets/{pet}/state').json()
    monday = rules._monday(rules._day(NOW))
    with db.connect() as c:
        counts_before = rules._proposal_counts(quests.proposals(c, pet), monday, monday + timedelta(days=7))
    assert counts_before[:3] == (0 if lifecycle == 'offered' else 1, 1 if lifecycle == 'accepted' else 0, 0)

    rest = client.post(f'/pets/{pet}/proposal-control', json={'action': 'rest'})
    assert rest.status_code == 200, rest.text
    cancelled = row(db, pet, ident)
    assert cancelled['excluded'] and cancelled['cancelled_at'] == NOW and cancelled['template']['rest'] is True
    assert cancelled['status'] == lifecycle
    assert cancelled['shown_at'] == before['shown_at'] and cancelled['expires_at'] == before['expires_at']
    assert cancelled['accepted_at'] == before['accepted_at']
    assert client.post(f'/pets/{pet}/proposals/{ident}/shown').status_code == 409
    decision = 'reject' if lifecycle == 'accepted' else 'accept'
    assert client.post(f'/pets/{pet}/quests/{ident}/decision', json={'decision': decision}).status_code == 409
    with db.connect() as c:
        assert rules._proposal_counts(quests.proposals(c, pet), monday, monday + timedelta(days=7)) == (0, 0, 0, 0)
    after_state = client.get(f'/pets/{pet}/state').json()
    for field in ('level', 'total_exp', 'coin', 'upper_body', 'lower_body', 'activity', 'affinity', 'initiative'):
        assert after_state[field] == before_state[field]

    client.app.state.clock = lambda: NOW + timedelta(minutes=5)
    assert client.post(f'/pets/{pet}/proposal-control', json={'action': 'rest'}).status_code == 200
    repeated = row(db, pet, ident)
    assert repeated == cancelled  # The first cancellation timestamp/evidence survives retries.
    assert client.post(f'/pets/{pet}/proposal-control', json={'action': 'resume'}).status_code == 200
    assert row(db, pet, ident) == cancelled  # Resume never resurrects a cancelled opportunity.


def seed(db, pet, ident, *, candidate='workout1', status='active', created=None,
         deadline=None, is_proposal=True, excluded=False, cancelled_at=None):
    created = created or NOW - timedelta(hours=1)
    deadline = deadline if deadline is not None else created + timedelta(hours=24)
    accepted = created + timedelta(minutes=1) if status in ('accepted', 'completed') else None
    completed = created + timedelta(minutes=2) if status == 'completed' else None
    with db.connect() as c:
        c.execute("""INSERT INTO quest_offers
            (pet_id,id,template,status,state_version,created_at,expires_at,is_proposal,shown_at,
             accepted_at,completed_at,completion_verified,excluded,cancelled_at)
            VALUES(%s,%s,%s,%s,0,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (pet, ident, Jsonb({'candidate': candidate, 'target': 1, 'fixture_note': 'synthetic proposal lifecycle setup'}),
             status, created, deadline, is_proposal, None if status == 'offered' else created,
             accepted, completed, status == 'completed', excluded, cancelled_at))


def test_rest_preserves_past_completed_nonworkout_and_basic_quests(client, pet, db):
    fixtures = {
        'completed': {'status': 'completed'},
        'expired': {'status': 'expired', 'deadline': NOW - timedelta(seconds=1)},
        'past-active': {'created': NOW - timedelta(days=8), 'deadline': NOW - timedelta(days=7)},
        'deadline-equal-now': {'status': 'accepted', 'created': NOW - timedelta(days=1), 'deadline': NOW},
        'rejected': {'status': 'rejected'},
        'meal': {'candidate': 'meal1'},
        'two-meals': {'candidate': 'meal2'},
        'chat': {'candidate': 'chat1'},
        'basic': {'is_proposal': False},
        'already-cancelled': {'excluded': True, 'cancelled_at': NOW - timedelta(minutes=10)},
        'already-excluded': {'excluded': True},
        'future-fixture': {'created': NOW + timedelta(days=1)},
    }
    for ident, args in fixtures.items():
        seed(db, pet, ident, **args)
    # A previous calendar day's still-live 24-hour opportunity is current, not
    # expired history. Rest interrupts its remaining performance time as well.
    seed(db, pet, 'live-from-yesterday', status='accepted', created=NOW - timedelta(hours=18))
    before = {ident: row(db, pet, ident) for ident in fixtures}
    assert client.post(f'/pets/{pet}/proposal-control', json={'action': 'rest'}).status_code == 200
    for ident in fixtures:
        assert row(db, pet, ident) == before[ident], ident
    current = row(db, pet, 'live-from-yesterday')
    assert current['excluded'] and current['cancelled_at'] == NOW and current['template']['rest'] is True


def test_rest_cancellation_requires_pet_owner_and_does_not_apply_to_stop(client, pet, db):
    seed(db, pet, 'owned-live')
    before = row(db, pet, 'owned-live')
    denied = client.post(f'/pets/{pet}/proposal-control', json={'action': 'rest'},
                         headers={'Authorization': 'Bearer test-owner-b-token'})
    assert denied.status_code == 404
    assert row(db, pet, 'owned-live') == before
    assert client.post(f'/pets/{pet}/proposal-control', json={'action': 'stop'}).status_code == 200
    assert row(db, pet, 'owned-live') == before
