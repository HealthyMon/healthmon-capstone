def analyze(client, pet, ident):
    response = client.post(f'/pets/{pet}/food/analyze', content=b'\x89PNG\r\n\x1a\nsynthetic-image-fixture', headers={'X-Request-Id': ident, 'Content-Type': 'image/png'})
    assert response.status_code == 200, response.text
    return response.json()['analysis_id']


def confirm(client, pet, ident, **extra):
    return client.post(f'/pets/{pet}/food/confirm', json={'analysis_id': ident, 'candidate_id': 0, 'grams': 100,
                       'meal_type': 'breakfast', 'vegetable_fruit_g': 80, **extra})


def test_reanalysis_of_same_photo_is_not_another_consumption(client, pet, settings, db):
    settings.ai_mode = 'mock'
    first_id = analyze(client, pet, 'first-analysis-id')
    first = confirm(client, pet, first_id)
    assert first.status_code == 200, first.text
    repeated_id = analyze(client, pet, 'repeated-analysis-id')
    repeated = confirm(client, pet, repeated_id)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()['source_id'] == first.json()['source_id']
    assert repeated.json()['duplicate'] is True
    assert repeated.json()['state']['total_exp'] == first.json()['state']['total_exp']
    assert len(client.get(f'/pets/{pet}/meals').json()['records']) == 1


def test_reanalysis_correction_requires_explicit_revision(client, pet, settings):
    settings.ai_mode = 'mock'
    first = confirm(client, pet, analyze(client, pet, 'original-analysis-id'))
    second_id = analyze(client, pet, 'changed-analysis-id')
    assert confirm(client, pet, second_id, grams=200).status_code == 409
    corrected = confirm(client, pet, second_id, grams=200, revision=2)
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()['revision'] == 2
    assert corrected.json()['state']['total_exp'] == first.json()['state']['total_exp']


def test_erased_consumption_cannot_return_through_reanalysis(client, pet, settings):
    settings.ai_mode = 'mock'
    first = confirm(client, pet, analyze(client, pet, 'erased-first-analysis'))
    deleted = client.delete(f"/pets/{pet}/sources/{first.json()['source_id']}", params={'expected_revision': 1})
    assert deleted.status_code == 200
    next_id = analyze(client, pet, 'erased-reanalysis-id')
    assert confirm(client, pet, next_id).status_code == 410
