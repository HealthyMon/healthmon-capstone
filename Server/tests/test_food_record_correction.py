from datetime import timedelta

from psycopg.types.json import Jsonb

from Server.tests.test_food_confirmation_fixture import prepare_analysis


def test_explicit_food_revision_corrects_same_meal_and_pays_quest_once(client, pet, settings, db, monkeypatch):
    body = prepare_analysis(client, pet, settings, monkeypatch, 'explicit-food-correction')
    with db.connect() as connection:
        easy = connection.execute("SELECT id,template FROM quest_offers WHERE pet_id=%s AND slot='easy'", (pet,)).fetchone()
        connection.execute('UPDATE quest_offers SET template=%s WHERE pet_id=%s AND id=%s',
                           (Jsonb(dict(easy['template'], candidate='meal1', target=1)), pet, easy['id']))
    original_body = dict(body, meal_type='snack', grams=None)
    first = client.post(f'/pets/{pet}/food/confirm', json=original_body)
    assert first.status_code == 200, first.text
    assert first.json()['state']['coin'] == 0
    original_record = client.get(f'/pets/{pet}/meals').json()['records'][0]
    correction = dict(body, meal_type='breakfast', grams=100, revision=2)
    # Changing a label alone cannot silently overwrite an earlier confirmation.
    assert client.post(f'/pets/{pet}/food/confirm', json=dict(correction, revision=1)).status_code == 409
    edited = client.post(f'/pets/{pet}/food/confirm', json=correction)
    assert edited.status_code == 200, edited.text
    assert edited.json()['source_id'] == first.json()['source_id']
    assert edited.json()['revision'] == 2 and not edited.json()['duplicate']
    after = client.get(f'/pets/{pet}/meals').json()['records']
    assert len(after) == 1 and after[0]['revision'] == 2
    assert after[0]['occurred_at'] == original_record['occurred_at']
    assert after[0]['record']['meal_type'] == 'breakfast'
    assert after[0]['record']['quantity_confirmed'] and after[0]['record']['grams'] == 100
    for _ in range(3):
        repeated = client.post(f'/pets/{pet}/food/confirm', json=correction)
        assert repeated.status_code == 200 and repeated.json()['duplicate']
    assert client.post(f'/pets/{pet}/food/confirm', json=original_body).status_code == 409
    with db.connect() as connection:
        rewards = connection.execute('SELECT exp,coin FROM game_ledger WHERE pet_id=%s AND reward_key=%s',
                                     (pet, 'quest:' + easy['id'])).fetchall()
        revisions = connection.execute('SELECT revision FROM source_revisions WHERE pet_id=%s AND source_id=%s ORDER BY revision',
                                       (pet, first.json()['source_id'])).fetchall()
    assert rewards == [{'exp': 30, 'coin': 10}]
    assert revisions == [{'revision': 1}, {'revision': 2}]


def test_food_correction_keeps_revision_window_and_original_record(client, pet, settings, monkeypatch):
    body = prepare_analysis(client, pet, settings, monkeypatch, 'expired-food-correction')
    first = client.post(f'/pets/{pet}/food/confirm', json=dict(body, meal_type='snack', grams=None))
    assert first.status_code == 200, first.text
    original = client.get(f'/pets/{pet}/meals').json()['records'][0]
    now = client.app.state.clock()
    client.app.state.clock = lambda: now + timedelta(hours=24, seconds=1)
    response = client.post(f'/pets/{pet}/food/confirm', json=dict(body, revision=2))
    assert response.status_code == 409
    records = client.get(f'/pets/{pet}/meals').json()['records']
    assert len(records) == 1 and records[0] == original
