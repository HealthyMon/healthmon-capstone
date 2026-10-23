from datetime import datetime, timedelta, timezone

from psycopg.types.json import Jsonb

from Server.healthmon import rules


def test_explicit_rest_command_works_without_ai_and_is_idempotent(client, pet, db):
    request = {'request_id': 'explicit-rest-command', 'text': '오늘 쉬고 싶어'}
    first = client.post(f'/pets/{pet}/chat', json=request)
    assert first.status_code == 200, first.text
    assert first.json()['provenance'] == 'server_rule'
    duplicate = client.post(f'/pets/{pet}/chat', json=request)
    assert duplicate.status_code == 200 and duplicate.json() == first.json()
    proposal = client.post(f'/pets/{pet}/proposals', json={'request_id': 'blocked-rest-offer', 'candidate': 'workout1'})
    assert proposal.status_code == 409
    with db.connect() as c:
        row = c.execute('SELECT rest_until FROM game_proposal_controls WHERE pet_id=%s', (pet,)).fetchone()
    assert row['rest_until'].astimezone(timezone.utc).isoformat().startswith('2026-10-22T15:00:00')


def test_stop_resume_controls_are_scoped_and_persisted(client, pet):
    assert client.post(f'/pets/{pet}/proposal-control', json={'action': 'stop'}).status_code == 200
    assert client.post(f'/pets/{pet}/proposals', json={'request_id': 'blocked-stop-offer', 'candidate': 'meal1'}).status_code == 409
    assert client.post(f'/pets/{pet}/proposal-control', json={'action': 'resume'}).status_code == 200
    offer = client.post(f'/pets/{pet}/proposals', json={'request_id': 'resumed-test-offer', 'candidate': 'meal1'})
    assert offer.status_code == 200, offer.text
    ident = offer.json()['id']
    assert client.post(f'/pets/{pet}/proposals/{ident}/shown').status_code == 200
    assert client.post(f'/pets/{pet}/quests/{ident}/decision', json={'decision': 'accept'}).status_code == 200


def test_current_slots_and_proposal_survive_more_than_100_historical_quests(client, pet, db):
    timestamp = datetime(2026, 10, 22, 3, tzinfo=timezone.utc)
    today = rules._day(timestamp)
    with db.connect() as c:
        rows = []
        for age in range(1, 56):
            day = today - timedelta(days=age)
            for slot in ('easy', 'medium'):
                rows.append((pet, f'historical:{age}:{slot}',
                             Jsonb({'candidate': 'workout1', 'target': 1, 'basic_quest': True}),
                             rules._midnight(day), rules._midnight(day + timedelta(days=1)), slot, day))
        with c.cursor() as cursor:
            cursor.executemany("""INSERT INTO quest_offers
                (pet_id,id,template,status,state_version,created_at,expires_at,slot,period_start,is_proposal)
                VALUES(%s,%s,%s,'expired',0,%s,%s,%s,%s,false)""", rows)
    created = client.post(f'/pets/{pet}/proposals', json={'request_id': 'visible-after-long-history', 'candidate': 'workout1'})
    assert created.status_code == 200, created.text
    proposal = created.json()
    assert proposal['shown_at'] is None and proposal['status'] == 'offered'
    response = client.get(f'/pets/{pet}/quests')
    assert response.status_code == 200, response.text
    offers = response.json()['quests']
    assert len(offers) == 100 and response.json()['offers'] == offers
    assert {row['slot'] for row in offers[:3]} == {'easy', 'medium', 'weekly'}
    assert all(not row['is_proposal'] for row in offers[:3])
    assert offers[3]['id'] == proposal['id'] and offers[3]['shown_at'] is None
    # Fetching a list cannot manufacture display evidence. The actual UI ACK
    # remains required, and its retry must not count a second opportunity.
    route = f"/pets/{pet}/proposals/{proposal['id']}/shown"
    decision = f"/pets/{pet}/quests/{proposal['id']}/decision"
    assert client.post(decision, json={'decision': 'accept'}).status_code == 409
    shown = client.post(route)
    assert shown.status_code == 200 and shown.json()['status'] == 'active'
    again = client.post(route)
    assert again.status_code == 200 and again.json()['shown_at'] == shown.json()['shown_at']
    accepted = client.post(decision, json={'decision': 'accept'})
    assert accepted.status_code == 200 and accepted.json()['status'] == 'accepted'
    refreshed = client.get(f'/pets/{pet}/quests').json()['quests']
    assert refreshed[3]['id'] == proposal['id'] and refreshed[3]['status'] == 'accepted'
