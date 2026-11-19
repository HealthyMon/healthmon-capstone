"""Watch detail metrics must survive the public API without changing game rewards."""
import pytest


def workout(**details):
    return dict(event_id='watch-details', occurred_at='2026-10-22T03:00:00+00:00',
                started_at='2026-10-22T02:30:00+00:00', workout_type='walking',
                actual=1000, unit='steps', source='watch', **details)


def test_watch_measurements_round_trip_and_retry_do_not_duplicate_rewards(client, pet):
    details = dict(duration_seconds=1800, average_heart_rate_bpm=110.5,
                   max_heart_rate_bpm=140, calories_kcal=95.25, steps=1000, distance_km=.8)
    response = client.post(f'/pets/{pet}/workouts', json=workout(**details))
    assert response.status_code == 200, response.text
    first = response.json()['state']
    retry = client.post(f'/pets/{pet}/workouts', json=workout(**details))
    assert retry.status_code == 200
    assert retry.json()['state']['total_exp'] == first['total_exp']
    assert retry.json()['state']['coin'] == first['coin']
    records = client.get(f'/pets/{pet}/workouts').json()['records']
    assert len(records) == 1
    record = records[0]['record']
    assert record['exercise_type'] == 'walking'
    assert {key: record[key] for key in details} == details
    assert client.get(f'/pets/{pet}/workouts', headers={'Authorization': 'Bearer test-owner-b-token'}).status_code == 404


def test_legacy_watch_history_keeps_missing_metrics_unknown(client, pet):
    assert client.post(f'/pets/{pet}/workouts', json=workout()).status_code == 200
    record = client.get(f'/pets/{pet}/workouts').json()['records'][0]['record']
    for name in ('duration_seconds', 'average_heart_rate_bpm', 'max_heart_rate_bpm', 'calories_kcal', 'steps', 'distance_km'):
        assert record[name] is None


@pytest.mark.parametrize('details', [
    {'duration_seconds': -1}, {'average_heart_rate_bpm': 301}, {'max_heart_rate_bpm': -1},
    {'calories_kcal': -1}, {'steps': -1}, {'distance_km': -1},
])
def test_invalid_watch_metrics_rejected_before_storage(client, pet, details):
    assert client.post(f'/pets/{pet}/workouts', json=workout(**details)).status_code == 422
    assert client.get(f'/pets/{pet}/workouts').json()['records'] == []
