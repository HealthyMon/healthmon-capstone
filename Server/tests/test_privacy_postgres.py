"""Privacy erasure tests against a fresh real PostgreSQL+pgvector database."""
from datetime import datetime, timedelta, timezone
import json

from fastapi import HTTPException
from psycopg.types.json import Jsonb
import pytest

from Server.healthmon import privacy, service, rules


BASE = datetime(2026, 10, 22, 3, tzinfo=timezone.utc)


def clock(client, when):
    client.app.state.clock = lambda: when


def workout(client, pet, ident='private-workout', when=None, actual=30):
    when = when or BASE + timedelta(hours=1)
    response = client.post(f'/pets/{pet}/workouts', json={
        'event_id': ident, 'occurred_at': when.isoformat(), 'started_at': when.isoformat(),
        'workout_type': 'running', 'actual': actual, 'unit': 'minutes', 'source': 'user'})
    assert response.status_code == 200, response.text
    return response.json()


def erase(db, settings, pet, when, source='private-workout', revision=1):
    with db.connect() as c:
        p = service.owned(c, 'owner-a', pet, True)
        return privacy.delete_source(c, p, source, revision, when, settings)


def state(client, pet):
    result = client.get(f'/pets/{pet}/state')
    assert result.status_code == 200, result.text
    return result.json()


def test_within_24h_erases_raws_recalculates_stats_preserves_paid_rewards(client, pet, db, settings):
    clock(client, BASE + timedelta(hours=2))
    before = workout(client, pet)['state']
    assert before['lower_body'] == 52
    output = erase(db, settings, pet, BASE + timedelta(hours=3))
    assert output['state']['lower_body'] == 50
    assert output['state']['total_exp'] == before['total_exp']
    assert output['state']['coin'] == before['coin']
    assert output['score_recalculated'] is True
    with db.connect() as c:
        row = c.execute('SELECT * FROM sources WHERE pet_id=%s', (pet,)).fetchone()
        assert row['valid'] is False and row['fingerprint'] is None
        assert row['payload'] == {'_privacy_erased': True, '_game_kind': 'workout', 'data': {}}
        assert row['occurred_at'] == BASE + timedelta(hours=3)
        assert c.execute('SELECT count(*) AS n FROM source_revisions WHERE pet_id=%s', (pet,)).fetchone()['n'] == 0
        assert c.execute('SELECT count(*) AS n FROM game_retained_scores WHERE pet_id=%s', (pet,)).fetchone()['n'] == 0
    clock(client, BASE + timedelta(hours=3))
    assert workout_resurrection(client, pet, 1).status_code == 410
    assert workout_resurrection(client, pet, 2).status_code == 410


def workout_resurrection(client, pet, revision):
    return client.post(f'/pets/{pet}/workouts', json={'event_id': 'private-workout', 'revision': revision,
        'occurred_at': (BASE + timedelta(hours=1)).isoformat(), 'started_at': (BASE + timedelta(hours=1)).isoformat(),
        'workout_type': 'running', 'actual': 30, 'unit': 'minutes', 'source': 'user'})


def test_after_24h_erasure_preserves_score_across_refresh_and_next_workout(client, pet, db, settings):
    clock(client, BASE + timedelta(hours=2))
    original = workout(client, pet)['state']
    deleted_at = BASE + timedelta(hours=26, microseconds=1)
    output = erase(db, settings, pet, deleted_at)
    assert output['score_recalculated'] is False
    assert output['state']['lower_body'] == 52
    assert output['state']['total_exp'] == original['total_exp']
    clock(client, deleted_at)
    assert state(client, pet)['lower_body'] == 52
    later = workout(client, pet, 'next-day-workout', deleted_at)['state']
    assert later['lower_body'] == 54
    assert state(client, pet)['lower_body'] == 54
    with db.connect() as c:
        rows = c.execute('SELECT * FROM game_retained_scores WHERE pet_id=%s', (pet,)).fetchall()
        assert len(rows) == 1 and rows[0]['adjustment']['body_events'][0]['score'] == 2
        assert set(rows[0]['adjustment']) <= {'upper_body', 'lower_body', 'nutrition', 'energy_balance', 'body_events'}
        assert set(rows[0]['adjustment']['body_events'][0]) == {'key', 'at', 'score', 'body_part', 'performed', 'missed'}
        text = json.dumps(rows[0]['adjustment'])
        assert not any(key in text for key in ('actual', 'target', 'protein', 'speech', 'text', 'food_name', 'private-workout'))


def test_exact_24h_still_recalculates_ordinary_scores(client, pet, db, settings):
    clock(client, BASE + timedelta(hours=2))
    workout(client, pet)
    output = erase(db, settings, pet, BASE + timedelta(hours=25))
    assert output['score_recalculated'] is True and output['state']['lower_body'] == 50


def test_old_erasure_and_late_same_day_events_still_use_daily_net_cap(client, pet, db, settings):
    clock(client, BASE + timedelta(hours=3))
    workout(client, pet, 'private-workout', BASE + timedelta(hours=1), 36)
    workout(client, pet, 'second', BASE + timedelta(hours=2), 36)
    assert workout(client, pet, 'third', BASE + timedelta(hours=3), 1)['state']['lower_body'] == 53
    delete_at = BASE + timedelta(hours=26, microseconds=1)
    assert erase(db, settings, pet, delete_at)['state']['lower_body'] == 53
    clock(client, delete_at)
    for index in range(3):
        result = workout(client, pet, f'late-{index}', BASE + timedelta(hours=10, minutes=index), 1)
    assert result['state']['lower_body'] == 52  # (+3+3-1-1-1-1)=+2, cap after sum.
    assert state(client, pet)['lower_body'] == 52


@pytest.mark.parametrize('same_time,late_id', [(False, 'late-full-body'), (True, 'a-before-erased'), (True, 'z-after-erased')])
def test_old_erased_workout_and_late_full_body_preserve_exact_pre_event_state_and_ties(client, pet, db, settings, same_time, late_id):
    goal = client.post(f'/pets/{pet}/goals', json={'exercise_type': 'full_body', 'target': 30,
        'unit': 'minutes', 'body_part': 'full'})
    assert goal.status_code == 200, goal.text
    old_time = BASE + timedelta(hours=1)
    clock(client, BASE + timedelta(hours=2))
    response = client.post(f'/pets/{pet}/workouts', json={'event_id': 'private-workout',
        'occurred_at': old_time.isoformat(), 'workout_type': 'pushup', 'actual': 36,
        'unit': 'repetitions', 'source': 'user'})
    assert response.status_code == 200 and response.json()['state']['upper_body'] == 53
    deleted_at = old_time + timedelta(hours=24, microseconds=1)
    assert erase(db, settings, pet, deleted_at)['state']['upper_body'] == 53
    clock(client, deleted_at)
    # Exact equal-time records can still arrive within24h when deletion is just
    # beyond24h only if receipt was previously durable. Test replay directly with
    # that immutable first receipt for equal-time transport/restart recovery.
    late_time = old_time if same_time else BASE + timedelta(hours=10)
    if same_time:
        with db.connect() as c:
            p = service.owned(c, 'owner-a', pet, True)
            data = service.events(c, pet)
            late = {'event_id': late_id, 'kind': 'workout', 'occurred_at': late_time,
                    'received_at': old_time + timedelta(hours=23), 'valid': True,
                    'payload': {'exercise_type': 'full_body', 'actual': 21, 'target': 30,
                                'unit': 'minutes', 'body_part': 'full', 'goal_confirmed_before_start': True}}
            output = rules.replay(data + [late], deleted_at, retained=privacy.load_retained(c, pet))
            scored = output['state']
    else:
        response = client.post(f'/pets/{pet}/workouts', json={'event_id': late_id,
            'occurred_at': late_time.isoformat(), 'workout_type': 'full_body', 'actual': 21,
            'unit': 'minutes', 'source': 'user'})
        assert response.status_code == 200, response.text
        scored = response.json()['state']
    if same_time and late_id < 'private-workout':
        # Full-body score+1 is first at 50/50: remainder upper, then upper+3 capped.
        assert (scored['upper_body'], scored['lower_body']) == (53, 50)
    else:
        # Erased upper+3 comes first; later full-body+1 must go to weaker lower.
        assert (scored['upper_body'], scored['lower_body']) == (53, 51)


def test_multiple_old_erasures_compose_without_double_counting(client, pet, db, settings):
    clock(client, BASE + timedelta(hours=2))
    workout(client, pet, 'private-workout', BASE + timedelta(hours=1))
    assert workout(client, pet, 'second', BASE + timedelta(hours=2))['state']['lower_body'] == 53
    when = BASE + timedelta(hours=27)
    assert erase(db, settings, pet, when)['state']['lower_body'] == 53
    assert erase(db, settings, pet, when, source='second')['state']['lower_body'] == 53
    repeated = erase(db, settings, pet, when)
    assert repeated['duplicate'] is True and repeated['state']['lower_body'] == 53


def test_old_meal_bundle_erasure_preserves_applied_game_delta_without_nutrients(client, pet, db, settings):
    clock(client, BASE + timedelta(hours=1))
    for ident in ('meal-a', 'meal-b'):
        response = client.post(f'/pets/{pet}/meals', json={
            'event_id': ident, 'occurred_at': (BASE + timedelta(hours=1)).isoformat(),
            'food_name': 'private food name', 'meal_type': 'breakfast', 'confirmed': True,
            'quantity_confirmed': True, 'carbohydrate_g': None, 'protein_g': None,
            'fat_g': None, 'kcal': 225})
        assert response.status_code == 200, response.text
    assert response.json()['state']['energy_balance'] == 0  # Combined 450kcal, not two low meals.
    output = erase(db, settings, pet, BASE + timedelta(hours=26), source='meal-a')
    assert output['state']['energy_balance'] == 0
    with db.connect() as c:
        anchor = c.execute("SELECT adjustment FROM game_retained_scores WHERE pet_id=%s AND period='daily'", (pet,)).fetchone()
        assert anchor['adjustment']['energy_balance'] == 3  # Frozen interaction cancels remaining -3.
        erased = c.execute('SELECT payload FROM sources WHERE pet_id=%s AND id=%s', (pet, 'meal-a')).fetchone()['payload']
        assert 'private food name' not in json.dumps(erased)
    clock(client, BASE + timedelta(hours=26))
    assert state(client, pet)['energy_balance'] == 0


def test_already_applied_weekly_personality_is_retained_after_old_event_erasure(client, db, settings):
    start = datetime(2026, 10, 12, 3, tzinfo=timezone.utc)
    clock(client, start)
    pet = client.post('/pets', json={'name': 'privacy-week'}).json()['pet_id']
    for index in range(3):
        when = start + timedelta(days=index, hours=1)
        clock(client, when)
        workout(client, pet, 'private-workout' if index == 0 else f'other-{index}', when)
    clock(client, BASE)
    before = state(client, pet)
    assert before['activity'] == 51 and before['lower_body'] == 56
    output = erase(db, settings, pet, BASE)
    assert output['state']['activity'] == 51 and output['state']['lower_body'] == 56
    assert state(client, pet)['activity'] == 51
    with db.connect() as c:
        anchors = c.execute("SELECT adjustment FROM game_retained_scores WHERE pet_id=%s AND period='weekly'", (pet,)).fetchall()
        assert any(item['adjustment']['activity'] == 1 for item in anchors)


def test_paid_levels_coin_and_published_asset_never_claw_back(client, pet, db, settings):
    clock(client, BASE + timedelta(hours=2))
    workout(client, pet)
    with db.connect() as c:
        c.execute("INSERT INTO game_ledger(pet_id,reward_key,exp,coin,reason) VALUES(%s,'fixture-paid',10000,60,'test_fixture')", (pet,))
        saved = c.execute('SELECT state FROM game_states WHERE pet_id=%s', (pet,)).fetchone()['state']
        saved.update(published_model_stage=1, model_reference='/saved-model', asset_status='ready')
        c.execute('UPDATE game_states SET state=%s WHERE pet_id=%s', (Jsonb(saved), pet))
    before = state(client, pet)
    output = erase(db, settings, pet, BASE + timedelta(hours=3))['state']
    for key in ('level', 'total_exp', 'coin', 'evolution_target_stage', 'published_model_stage', 'model_reference'):
        assert output[key] == before[key]


def test_erasure_narrowly_invalidates_dependent_cached_and_pending_chat(client, pet, db, settings):
    clock(client, BASE + timedelta(hours=2))
    workout(client, pet)
    with db.connect() as c:
        c.execute("INSERT INTO sources(pet_id,id,kind,revision,occurred_at,payload) VALUES(%s,'other-chat','message',1,%s,%s)",
                  (pet, BASE, Jsonb({'text': 'unrelated raw user message'})))
        c.execute("INSERT INTO memories(pet_id,id,source_id,source_revision,slot,content,embedding) VALUES(%s,'private-memory','private-workout',1,'experience','private recalled health data',%s::vector)",
                  (pet, json.dumps([1.] + [0.] * 1023)))
        for ident, dependencies in [('dependent-pending', ['private-workout']), ('unrelated-pending', [])]:
            c.execute("INSERT INTO requests(pet_id,id,fingerprint,status,dependency_source_ids,ai_input,lease_until,lease_token) VALUES(%s,%s,'fixture','running',%s,%s,%s,'fixture-lease')",
                      (pet, ident, Jsonb(dependencies), Jsonb({'text': 'private frozen text', 'context': 'private recalled context'}), BASE + timedelta(days=1)))
        c.execute("INSERT INTO requests(pet_id,id,fingerprint,status,result) VALUES(%s,'dependent-done','fixture','done',%s)", (pet, Jsonb({'speech': 'private cached answer'})))
        c.execute("INSERT INTO exchanges(pet_id,request_id,source_id,speech,memory_ids,state_used,state_after) VALUES(%s,'dependent-done','other-chat','private cached speech',%s,%s,%s)",
                  (pet, Jsonb(['private-memory']), Jsonb({'private': 'context'}), Jsonb({'private': 'context'})))
    output = erase(db, settings, pet, BASE + timedelta(hours=3))
    assert output['invalidated_requests'] == 2
    with db.connect() as c:
        statuses = {row['id']: row['status'] for row in c.execute('SELECT id,status FROM requests WHERE pet_id=%s', (pet,))}
        assert statuses == {'dependent-pending': 'invalidated', 'unrelated-pending': 'running', 'dependent-done': 'invalidated'}
        frozen = c.execute("SELECT ai_input,lease_until,lease_token FROM requests WHERE pet_id=%s AND id='dependent-pending'", (pet,)).fetchone()
        assert frozen == {'ai_input': None, 'lease_until': None, 'lease_token': None}
        unrelated = c.execute("SELECT ai_input FROM requests WHERE pet_id=%s AND id='unrelated-pending'", (pet,)).fetchone()
        assert unrelated['ai_input']['text'] == 'private frozen text'
        assert c.execute('SELECT count(*) AS n FROM memories WHERE pet_id=%s', (pet,)).fetchone()['n'] == 0
        cached = c.execute('SELECT * FROM exchanges WHERE pet_id=%s', (pet,)).fetchone()
        assert cached['speech'] == '' and cached['state_used'] == {} and cached['memory_ids'] == []
        assert c.execute("SELECT payload FROM sources WHERE pet_id=%s AND id='other-chat'", (pet,)).fetchone()['payload']['text'] == 'unrelated raw user message'


def test_direct_pending_chat_request_erasure_clears_frozen_input_before_exchange_exists(client, pet, db, settings):
    with db.connect() as c:
        c.execute("INSERT INTO sources(pet_id,id,kind,revision,occurred_at,received_at,payload) VALUES(%s,'message:pending-direct','message',1,%s,%s,%s)",
                  (pet, BASE, BASE, Jsonb({'_game_kind': 'chat', 'data': {'text': 'private pending text', 'normal': True}})))
        c.execute("INSERT INTO requests(pet_id,id,fingerprint,status,ai_input,lease_until,lease_token) VALUES(%s,'pending-direct','fixture','running',%s,%s,'leased')",
                  (pet, Jsonb({'text': 'private pending text', 'context': {'private': 'health memory'}}), BASE + timedelta(hours=4)))
    output = erase(db, settings, pet, BASE + timedelta(hours=1), source='message:pending-direct')
    assert output['invalidated_requests'] == 1
    with db.connect() as c:
        row = c.execute("SELECT status,ai_input,lease_until,lease_token,result FROM requests WHERE pet_id=%s AND id='pending-direct'", (pet,)).fetchone()
        assert row == {'status': 'invalidated', 'ai_input': None, 'lease_until': None, 'lease_token': None, 'result': None}


def test_food_cached_confirmation_and_analysis_are_erased_and_blocked(client, pet, db, settings):
    clock(client, BASE + timedelta(hours=1))
    response = client.post(f'/pets/{pet}/meals', json={'event_id': 'food-private-analysis',
        'occurred_at': (BASE + timedelta(hours=1)).isoformat(), 'food_name': 'secret food', 'meal_type': 'lunch',
        'confirmed': True, 'quantity_confirmed': True, 'analysis_id': 'private-analysis'})
    assert response.status_code == 200, response.text
    with db.connect() as c:
        c.execute('INSERT INTO food_analyses(id,pet_id,result,confirmation) VALUES(%s,%s,%s,%s)',
                  ('private-analysis', pet, Jsonb({'candidates': [{'food': 'secret food'}], 'image_hash': 'private-hash'}),
                   Jsonb({'source_id': 'food-private-analysis', 'record': {'food': 'secret food'}})))
    erase(db, settings, pet, BASE + timedelta(hours=2), source='food-private-analysis')
    with db.connect() as c:
        cached = c.execute('SELECT * FROM food_analyses WHERE pet_id=%s', (pet,)).fetchone()
        assert cached['result'] == {'_privacy_erased': True} and cached['confirmation'] is None
        assert cached['erased_at'] is not None
    clock(client, BASE + timedelta(hours=2))
    result = client.post(f'/pets/{pet}/food/confirm', json={'analysis_id': 'private-analysis', 'candidate_id': 0, 'grams': 100})
    assert result.status_code == 410, result.text


def test_owner_and_revision_checks_are_required(client, pet, db, settings):
    clock(client, BASE + timedelta(hours=2))
    workout(client, pet)
    with db.connect() as c:
        with pytest.raises(HTTPException) as caught:
            privacy.delete_source(c, {'id': pet, 'owner_id': 'owner-b'}, 'private-workout', 1, BASE + timedelta(hours=3), settings)
        assert caught.value.status_code == 404
        p = service.owned(c, 'owner-a', pet)
        with pytest.raises(HTTPException) as caught:
            privacy.delete_source(c, p, 'private-workout', 2, BASE + timedelta(hours=3), settings)
        assert caught.value.status_code == 409


def test_memory_erasure_removes_vector_and_pet_erasure_purges_all_owned_data(client, pet, db, settings):
    clock(client, BASE + timedelta(hours=2))
    workout(client, pet)
    with db.connect() as c:
        p = service.owned(c, 'owner-a', pet, True)
        c.execute("INSERT INTO memories(pet_id,id,source_id,source_revision,slot,content,embedding) VALUES(%s,'private-memory','private-workout',1,'experience','private',%s::vector)",
                  (pet, json.dumps([1.] + [0.] * 1023)))
        assert privacy.delete_memory(c, p, 'private-memory')['deleted'] is True
        assert c.execute('SELECT count(*) AS n FROM memories WHERE pet_id=%s', (pet,)).fetchone()['n'] == 0
    assert state(client, pet)['lower_body'] == 52
    with db.connect() as c:
        p = service.owned(c, 'owner-a', pet, True)
        assert privacy.delete_pet(c, p)['deleted'] is True
        for table in ('pets', 'sources', 'source_revisions', 'game_ledger', 'quest_offers', 'game_states'):
            column = 'id' if table == 'pets' else 'pet_id'
            assert c.execute(f'SELECT count(*) AS n FROM {table} WHERE {column}=%s', (pet,)).fetchone()['n'] == 0
    assert client.get(f'/pets/{pet}/state').status_code == 404
