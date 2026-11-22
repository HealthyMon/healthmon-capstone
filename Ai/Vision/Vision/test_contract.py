from types import SimpleNamespace
import torch
import pytest
from food_ai import format_result
from evaluate import weight_errors

def result(boxes, mtl):
    return SimpleNamespace(orig_shape=(100, 200), boxes=SimpleNamespace(data=torch.tensor(boxes).reshape(-1, 6)),
                           mtl=torch.tensor(mtl).reshape(-1, 3), names={0: 'rice'})

def test_coordinates_and_weights_stay_aligned():
    r = result([[-3, 10, 210, 90, .9, 0], [20, 20, 40, 40, .1, 0]], [[.9, 0, 123], [.1, 0, 900]])
    payload = format_result(r, .35)
    assert len(payload['foods']) == 1
    food = payload['foods'][0]
    assert food['bbox_xyxy'] == [0, 10, 200, 90]
    assert food['bbox_normalized_xyxy'] == [0, .1, 1, .9]
    assert food['weight_g'] == 123
    assert food['needs_weight_confirmation']

def test_empty_and_invalid_weight():
    assert format_result(result([], []), .35)['foods'] == []
    r = result([[1, 1, 20, 20, .9, 0]], [[.9, 0, float('nan')]])
    assert format_result(r, .35)['foods'][0]['weight_g'] is None

def test_standard_yolo_fails_instead_of_fabricating_weight():
    r = result([], [])
    r.mtl = None
    with pytest.raises(RuntimeError):
        format_result(r, .35)

def test_matching_is_one_to_one_and_class_aware():
    foods = [{'confidence': .9, 'bbox_normalized_xyxy': [0, 0, 1, 1], 'class_id': 0, 'weight_g': 110}] * 2
    targets = [{'box': [0, 0, 1, 1], 'class_id': 0, 'weight': 100}]
    assert weight_errors(foods, targets) == ([10], 1)
    targets[0]['class_id'] = 1
    assert weight_errors(foods, targets) == ([], 0)
