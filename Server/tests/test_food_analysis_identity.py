from psycopg.types.json import Jsonb

from Server.tests.test_food_confirmation_fixture import prepare_analysis


def test_new_analysis_of_same_photo_is_a_separate_meal_and_retry_is_idempotent(client, pet, settings, db, monkeypatch):
    first_body = prepare_analysis(client, pet, settings, monkeypatch, 'same-photo-first-meal')
    second_body = prepare_analysis(client, pet, settings, monkeypatch, 'same-photo-next-meal')
    second_body.update(grams=379., meal_type='dinner')
    first = client.post(f'/pets/{pet}/food/confirm', json=first_body)
    assert first.status_code == 200, first.text
    original = client.get(f'/pets/{pet}/meals').json()['records'][0]
    second = client.post(f'/pets/{pet}/food/confirm', json=second_body)
    assert second.status_code == 200, second.text
    assert second.json()['source_id'] != first.json()['source_id']
    records = client.get(f'/pets/{pet}/meals').json()['records']
    assert len(records) == 2
    assert original in records
    assert sorted(row['record']['grams'] for row in records) == [100., 379.]
    for body, saved in [(first_body, first), (second_body, second)]:
        repeated = client.post(f'/pets/{pet}/food/confirm', json=body)
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()['duplicate']
        assert repeated.json()['source_id'] == saved.json()['source_id']
    assert len(client.get(f'/pets/{pet}/meals').json()['records']) == 2
    with db.connect() as connection:
        hashes = connection.execute('SELECT result FROM food_analyses WHERE pet_id=%s', (pet,)).fetchall()
        assert len({row['result']['image_hash'] for row in hashes}) == 1


def test_legacy_image_record_keeps_its_id_for_retry_and_explicit_revision(client, pet, settings, db, monkeypatch):
    body = prepare_analysis(client, pet, settings, monkeypatch, 'legacy-image-confirmation')
    with db.connect() as connection:
        result = connection.execute('SELECT result FROM food_analyses WHERE id=%s', (body['analysis_id'],)).fetchone()['result']
    legacy_id = 'food-image-' + result['image_hash']
    first = client.post(f'/pets/{pet}/food/confirm', json=dict(body, event_id=legacy_id))
    assert first.status_code == 200, first.text
    # Older clients left event_id empty while the server used the image hash.
    with db.connect() as connection:
        confirmation = connection.execute('SELECT confirmation FROM food_analyses WHERE id=%s', (body['analysis_id'],)).fetchone()['confirmation']
        confirmation['input']['event_id'] = None
        connection.execute('UPDATE food_analyses SET confirmation=%s WHERE id=%s', (Jsonb(confirmation), body['analysis_id']))
    repeated = client.post(f'/pets/{pet}/food/confirm', json=body)
    assert repeated.status_code == 200 and repeated.json()['duplicate']
    assert repeated.json()['source_id'] == legacy_id
    edited = client.post(f'/pets/{pet}/food/confirm', json=dict(body, grams=379., revision=2))
    assert edited.status_code == 200, edited.text
    assert edited.json()['source_id'] == legacy_id
    records = client.get(f'/pets/{pet}/meals').json()['records']
    assert len(records) == 1 and records[0]['record']['grams'] == 379.
