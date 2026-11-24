import copy
import pytest
from pydantic import ValidationError
from Server.healthmon.gateway import FoodResult
from Server.local_probe.vision_gateway import normalize_result, MULTIFOOD_BACKEND


def result():
    n = dict(calories=0, carbs=0, protein=5, fat=0,
             has_calories=True, has_carbs=False, has_protein=True, has_fat=False)
    f = dict(id=0, class_id=2, name='fixture', grams=100, has_weight=True,
             weight_status='estimated', name_confidence=.8, bbox=[0, 0, 1, 1], per100=n,
             crop_base64='', nutrition_source='', nutrition_confidence='')
    return {'backend': MULTIFOOD_BACKEND,
        'candidates': [dict(food='fixture', confidence=.8, estimated_grams=100,
                           per_100g=dict(energy_kcal=0, carbohydrate_g=None, protein_g=5, fat_g=None))],
        'vision': dict(schema_version=1, analysis_id='multi-fixture', image_width=100, image_height=100,
                       original_base64='', annotated_base64='', foods=[f])}


def test_regions_survive_authenticated_gateway_and_keep_missing_distinct():
    value = normalize_result(result())
    assert value['candidates'][0]['per_100g']['energy_kcal'] == 0
    assert value['candidates'][0]['per_100g']['carbohydrate_g'] is None
    assert value['vision']['foods'][0]['per100']['has_calories']
    assert not value['vision']['foods'][0]['per100']['has_carbs']
    assert FoodResult.model_validate(value).vision.foods[0].class_id == 2


@pytest.mark.parametrize('issue', ['duplicate', 'bbox', 'nan', 'zero_weight', 'class', 'unbounded_image', 'too_many', 'missing_regions'])
def test_invalid_regions_never_reach_food_confirmation(issue):
    value = result(); vision = value['vision']; food = vision['foods'][0]
    if issue == 'duplicate': vision['foods'].append(copy.deepcopy(food))
    if issue == 'bbox': food['bbox'] = [0, 0, -.1, 1]
    if issue == 'nan': food['per100']['calories'] = float('nan')
    if issue == 'zero_weight': food['grams'] = 0
    if issue == 'class': food['class_id'] = 2000
    if issue == 'unbounded_image': vision['image_width'] = 16000001
    if issue == 'too_many': vision['foods'] = [dict(food, id=i) for i in range(33)]
    if issue == 'missing_regions': value.pop('vision')
    with pytest.raises((ValidationError, ValueError)):
        normalize_result(value)
