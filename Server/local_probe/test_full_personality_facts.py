"""Strict CPU checks of raw factual authority, distinct from performance bands."""
from copy import deepcopy
import json

import pytest

from Server.local_probe.compact_voice import compact_messages
from Server.local_probe.gpu_gateway import digest, model_projection, projected_messages, style_context
from Server.local_probe.test_compact_integration import model
from Server.local_probe.test_contract import context, result


AXES = ('activity', 'affinity', 'initiative')


def payload():
    ctx = context(activity=80, affinity=20, initiative=50)
    ctx['state'] = dict(ctx.get('state', {}), **ctx['personality'])
    return {'text': '성격을 참고해서 달리기 고민에 답해 줘.', 'context': ctx}


def test_default_projection_still_omits_raw_values_and_is_exactly_unchanged():
    value = payload()
    style = style_context(value['context'])
    assert model_projection(value, style) == model_projection(value, style, full_personality_facts=False)
    assert projected_messages(value) == projected_messages(value, full_personality_facts=False)
    assert not set(AXES).intersection(model_projection(value, style)[0]['context']['verified_game_facts'])


def test_full_facts_add_exactly_the_three_agreeing_scores_without_mutating_input_or_voice():
    value = payload()
    before = deepcopy(value)
    style = style_context(value['context'])
    ordinary, directions = model_projection(value, style)
    factual, actual_directions = model_projection(value, style, full_personality_facts=True)
    assert value == before and actual_directions == directions
    facts = factual['context']['verified_game_facts']
    assert {axis: facts[axis] for axis in AXES} == value['context']['personality']
    restored = deepcopy(factual)
    for axis in AXES:
        restored['context']['verified_game_facts'].pop(axis)
    assert restored == ordinary
    base, _ = compact_messages(value, enabled=True)
    with_facts, _ = compact_messages(value, enabled=True, base_builder=lambda item: projected_messages(item, full_personality_facts=True))
    assert base[0] == with_facts[0]
    before_user, after_user = json.loads(base[1]['content']), json.loads(with_facts[1]['content'])
    for axis in AXES:
        after_user['context']['verified_game_facts'].pop(axis)
    assert before_user == after_user


@pytest.mark.parametrize('where', ['state', 'personality', 'style'])
@pytest.mark.parametrize('bad', [None, True, float('nan'), float('inf'), -1, 101, '80'])
def test_invalid_factual_values_are_not_defaulted(where, bad):
    value = payload()
    style = style_context(value['context'])
    target = style['personality'] if where == 'style' else value['context'][where]
    target['activity'] = bad
    with pytest.raises((ValueError, TypeError)):
        model_projection(value, style, full_personality_facts=True)


@pytest.mark.parametrize('where', ['state', 'personality', 'style'])
def test_missing_factual_values_fail_closed(where):
    value = payload()
    style = deepcopy(style_context(value['context']))
    target = style['personality'] if where == 'style' else value['context'][where]
    target.pop('activity')
    with pytest.raises(ValueError, match='missing_authority'):
        model_projection(value, style, full_personality_facts=True)


@pytest.mark.parametrize('where', ['state', 'personality', 'style'])
def test_disagreeing_valid_factual_scores_fail_closed(where):
    value = payload()
    style = deepcopy(style_context(value['context']))
    target = style['personality'] if where == 'style' else value['context'][where]
    target['activity'] = 79
    with pytest.raises(ValueError, match='authority_mismatch'):
        model_projection(value, style, full_personality_facts=True)


@pytest.mark.parametrize('repair', [False, True])
def test_initial_refinement_and_repair_keep_facts_voice_classifier_and_budget(tmp_path, repair):
    raw = result('오늘 마음에 드는 속도를 골라 봐도 좋아.').model_dump_json()
    instance, calls = model(tmp_path, ['invalid JSON', raw, raw] if repair else [raw] * 3,
                            compact_voice=True, full_personality_facts=True)
    value = payload()
    before = deepcopy(value)
    output, metrics = instance.chat(value)
    assert value == before and len(calls) == 3
    expected = value['context']['personality']
    first_voice = calls[0][0]['content'].splitlines()[0]
    for prompt in calls:
        assert prompt[0]['content'].splitlines()[0] == first_voice
        user = json.loads(prompt[1]['content'])
        facts = user['context']['verified_game_facts']
        assert {axis: facts[axis] for axis in AXES} == expected
        assert user['user_text'] == value['text']
        assert user['context']['memories'] == value['context'].get('memories', [])
    assert output['classification'] == result('같은 분류').classification.model_dump(mode='json')
    assert metrics['full_personality_facts'] == {'enabled': True, 'verified_personality_sha256': digest(expected), 'state_personality_style_agree': True}
    assert metrics['prompt_projection']['numeric_personality_not_in_model_context'] is False
    assert all(trial['model_personality_facts_sha256'] == digest(expected) for trial in metrics['quality_refinement']['attempts'])
    assert [attempt['seed'] for attempt in metrics['attempts']] == [20261022, 20261023, 20261024]


def test_missing_factual_authority_is_rejected_before_any_generation(tmp_path):
    instance, calls = model(tmp_path, [], compact_voice=True, full_personality_facts=True)
    value = payload()
    value['context']['state'].pop('activity')
    with pytest.raises(ValueError, match='missing_authority'):
        instance.chat(value)
    assert calls == []


@pytest.mark.parametrize('missing_state', [None, [], 'missing'])
def test_missing_or_invalid_state_container_has_no_factual_defaults(tmp_path, missing_state):
    instance, calls = model(tmp_path, [], compact_voice=True, full_personality_facts=True)
    value = payload()
    if missing_state == 'missing':
        value['context'].pop('state')
    else:
        value['context']['state'] = missing_state
    with pytest.raises(ValueError, match='missing_authority'):
        instance.chat(value)
    assert calls == []
