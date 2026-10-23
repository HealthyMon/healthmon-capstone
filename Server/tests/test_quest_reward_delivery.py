"""Exercise quest completion through public APIs and reconcile the reward ledger."""
from datetime import datetime, timedelta, timezone

import pytest
from psycopg.types.json import Jsonb


BASE = datetime(2026, 10, 22, 3, tzinfo=timezone.utc)


@pytest.mark.parametrize('slot,candidate,target,expected_exp,expected_coin,days', [
    ('easy', 'workout1', 1, 30, 10, 1),
    ('medium', 'workout70', 1, 50, 20, 1),
    ('weekly', 'workout_days3', 3, 160, 60, 3),
])
def test_completed_quest_reward_reaches_state_once_after_event_retry_and_polling(
        client, pet, db, slot, candidate, target, expected_exp, expected_coin, days):
    response = client.get(f'/pets/{pet}/quests')
    assert response.status_code == 200, response.text
    offer = next(row for row in response.json()['offers'] if row['slot'] == slot)
    # Pin a valid fixture candidate so random pet IDs do not change test coverage.
    with db.connect() as connection:
        template = dict(offer['template'], candidate=candidate, target=target)
        assert (template['exp'], template['coin']) == (expected_exp, expected_coin)
        connection.execute('UPDATE quest_offers SET template=%s WHERE pet_id=%s AND id=%s',
                           (Jsonb(template), pet, offer['id']))
    uploaded = []
    for day in range(days):
        occurred = BASE + timedelta(days=day, minutes=30)
        client.app.state.clock = lambda when=occurred + timedelta(minutes=1): when
        body = {'event_id': f'quest-reward-{slot}-{day}', 'revision': 1,
                'occurred_at': occurred.isoformat(), 'started_at': occurred.isoformat(),
                'workout_type': 'run', 'actual': 30, 'unit': 'minutes',
                'source': 'user', 'synthetic': True}
        posted = client.post(f'/pets/{pet}/workouts', json=body)
        assert posted.status_code == 200, posted.text
        uploaded.append(body)
        progress = next(row for row in client.get(f'/pets/{pet}/quests').json()['offers']
                        if row['id'] == offer['id'])
        assert progress['progress'] == min(target, day + 1)
        assert (progress['status'] == 'completed') is (day + 1 == days)

    reward_key = 'quest:' + offer['id']
    with db.connect() as connection:
        rewards = connection.execute('SELECT exp,coin FROM game_ledger WHERE pet_id=%s AND reward_key=%s',
                                     (pet, reward_key)).fetchall()
        totals = connection.execute('SELECT sum(exp) AS exp,sum(coin) AS coin,count(*) AS count '
                                    'FROM game_ledger WHERE pet_id=%s', (pet,)).fetchone()
    assert rewards == [{'exp': expected_exp, 'coin': expected_coin}]
    baseline = client.get(f'/pets/{pet}/state').json()
    assert (baseline['total_exp'], baseline['coin']) == (totals['exp'], totals['coin'])

    for _ in range(3):
        for body in uploaded:
            repeated = client.post(f'/pets/{pet}/workouts', json=body)
            assert repeated.status_code == 200 and repeated.json()['duplicate'] is True
        assert client.get(f'/pets/{pet}/quests').status_code == 200
        state = client.get(f'/pets/{pet}/state').json()
        assert (state['total_exp'], state['coin']) == (baseline['total_exp'], baseline['coin'])
    with db.connect() as connection:
        after = connection.execute('SELECT sum(exp) AS exp,sum(coin) AS coin,count(*) AS count '
                                   'FROM game_ledger WHERE pet_id=%s', (pet,)).fetchone()
    assert after == totals
