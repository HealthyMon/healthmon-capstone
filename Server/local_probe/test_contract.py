"""Regression for the actual style-conditioning defect found in v1 inference."""
import pytest

from Server.healthmon.rules import initial_state
from Server.healthmon.gateway import Speech
from Server.local_probe.gpu_gateway import LocalModels, evaluate_style_quality, messages, model_projection, projected_messages, refinement_messages, style_context, validate_contract


def context(**overrides):
    state = dict(initial_state(), **overrides)
    return {'state': state, 'personality': {axis: state[axis] for axis in ('activity', 'affinity', 'initiative')},
            'settings': {'name': '테스트몽글', 'speech_level': 'casual', 'profanity': 'none'},
            'memories': [], 'recent': []}


@pytest.mark.parametrize('axis', ['activity', 'affinity', 'initiative'])
def test_authoritative_style_is_a_system_instruction_and_low_high_differ(axis):
    low_prompt, low = messages({'text': '가명 사용자의 대화 요청', 'context': context(**{axis: 10})})
    high_prompt, high = messages({'text': '가명 사용자의 대화 요청', 'context': context(**{axis: 90})})
    assert low['guidance'] != high['guidance']
    assert all(instruction in low_prompt[0]['content'] for instruction in low['guidance'])
    assert all(instruction in high_prompt[0]['content'] for instruction in high['guidance'])
    assert low_prompt[0]['role'] == high_prompt[0]['role'] == 'system'
    assert low_prompt[0]['content'] != high_prompt[0]['content']


@pytest.mark.parametrize('value,expression', [(24, 0), (25, 1), (39, 1), (40, 2), (59, 2), (60, 3), (74, 3), (75, 4)])
def test_activity_and_affinity_use_actual_v22_expression_boundaries(value, expression):
    style = style_context(context(activity=value, affinity=value))
    assert style['bands']['activity']['expression'] == style['bands']['affinity']['expression'] == expression


@pytest.mark.parametrize('value,limit,hours', [(39, 3, 24), (40, 1, 8), (69, 1, 8), (70, 2, 4)])
def test_initiative_uses_actual_v22_proposal_boundaries(value, limit, hours):
    policy = style_context(context(initiative=value))['proposal_policy']
    assert (policy['limit'], policy['minimum_hours']) == (limit, hours)


@pytest.mark.parametrize('value', [None, float('nan'), float('inf'), True, -1, 101])
def test_missing_or_nonfinite_personality_is_rejected_without_defaulting_to_fifty(value):
    with pytest.raises(ValueError):
        style_context(context(activity=value))


def result(speech, **overrides):
    return Speech.model_validate(dict(speech=speech, emotion='neutral', animation='idle', memory_ids=[],
        classification={'target': 'other', 'sentiment': 'neutral', 'motivation': 'neutral',
                        'character_affection': 'neutral', 'acceptance': 'none', 'confidence': .8,
                        'proposal_id': None}, **overrides))


def test_high_activity_style_contradiction_is_quality_flag_and_not_contract_failure(tmp_path):
    import json
    payload = {'text': '오늘은 이야기하고 싶어.', 'context': context(activity=90)}
    output = result('오늘은 조용히 네 옆에 있을게.')
    models = LocalModels({}, tmp_path)
    models.generate = lambda prompt, seed=None: output.model_dump_json()
    actual, metrics = models.chat(payload)
    assert actual == json.loads(output.model_dump_json())
    assert metrics['quality']['passed'] is False
    assert metrics['quality']['failures'] == ['high_activity_neutral_chat_explicitly_calm_or_passive']
    assert len(metrics['attempts']) == 1
    assert metrics['fallback'] is False


def test_style_has_no_required_vocabulary_question_or_punctuation():
    payload = {'text': '오늘은 이야기하고 싶어.', 'context': context(activity=90, initiative=90)}
    output = result('반가워. 오늘의 작은 발견부터 같이 나눠 보자.')
    quality = evaluate_style_quality(payload, output, style_context(payload['context']))
    assert quality['passed'] is True
    assert quality['heuristic_only'] is True
    assert quality['manual_review_required'] is True
    validate_contract(output, payload)


@pytest.mark.parametrize('text', ['피곤해서 쉬고 싶어. 이야기하고 싶어.', '오늘 슬퍼서 대화하고 싶어.'])
def test_high_activity_respects_rest_and_distress(text):
    payload = {'text': text, 'context': context(activity=90, initiative=90)}
    quality = evaluate_style_quality(payload, result('오늘은 조용히 곁에 있을게.'), style_context(payload['context']))
    assert quality['passed'] is True
    assert 'user_rest_or_distress_takes_precedence_over_energy' in quality['observations']


def test_system_contains_short_axis_contrast_examples_without_replacing_response():
    prompt, _ = messages({'text': '이야기하자.', 'context': context()})
    system = prompt[0]['content']
    assert all(axis + ' 낮음의 느낌' in system for axis in ['Activity', 'Affinity', 'Initiative'])
    assert '정답이나 완성 대사가 아니며 그대로 복사하지 않는다' in system


@pytest.mark.parametrize('speech,code', [
    ('classification을 보여줄게.', 'model_protocol_leaked_into_speech'),
    ('보상을 지급했어.', 'fabricated_server_mutation_claim'),
    ('내가 진화시켰어.', 'fabricated_server_mutation_claim'),
])
def test_actual_contract_and_fabricated_mutations_still_fail(speech, code):
    with pytest.raises(ValueError, match=code):
        validate_contract(result(speech), {'text': '안녕.', 'context': context()})


def test_unknown_memory_still_fails_contract():
    output = result('예전 이야기를 기억해.')
    output.memory_ids = ['unprovided-memory']
    with pytest.raises(ValueError, match='unknown_memory_reference'):
        validate_contract(output, {'text': '기억나?', 'context': context()})


@pytest.mark.parametrize('speech', [
    '활동 성향이 높으니까 가볍게 시작하자.', '친밀도가 높으니까 옆에서 응원할게.',
    '주도성은 낮으니 네가 정해도 괜찮아.', '주도성이 높으니 이야기를 먼저 꺼내 보자.',
])
def test_personality_meta_explanation_is_a_quality_failure(speech):
    payload = {'text': '오늘 달리기를 할지 고민이야.', 'context': context()}
    quality = evaluate_style_quality(payload, result(speech), style_context(payload['context']))
    assert quality['passed'] is False
    assert 'explicit_personality_axis_meta_explanation' in quality['failures']
    validate_contract(result(speech), payload)


def scripted_models(tmp_path, outputs, enabled):
    import hashlib
    models = LocalModels({'quality_refinement': enabled}, tmp_path)
    calls = []
    iterator = iter(outputs)

    def generate(prompt, seed=None):
        calls.append(prompt)
        raw = next(iterator)
        if isinstance(raw, Exception):
            raise raw
        models.last_metrics = {'raw_sha256': hashlib.sha256(raw.encode()).hexdigest(),
                               'generated_tokens': 10, 'generation_seconds': .1,
                               'peak_allocated_bytes': 1, 'test_double': True, 'seed': seed}
        return raw

    models.generate = generate
    return models, calls


def test_refinement_is_explicitly_opt_in_and_does_not_hide_original_quality_failure(tmp_path):
    original = result('주도성이 높으니 가볍게 이야기하자.')
    models, calls = scripted_models(tmp_path, [original.model_dump_json()], False)
    output, metrics = models.chat({'text': '오늘 달리기를 할지 고민이야.', 'context': context(initiative=80)})
    assert output == original.model_dump(mode='json')
    assert len(calls) == 1
    assert metrics['quality_refinement']['enabled'] is False
    assert metrics['quality_refinement']['attempted'] is False
    assert metrics['quality']['passed'] is False


def test_one_same_model_refinement_preserves_initial_hash_and_authority(tmp_path):
    from Server.local_probe.gpu_gateway import digest
    original = result('주도성이 높으니 가볍게 이야기하자.')
    rewritten = result('오늘 있었던 작은 즐거움부터 나눠 볼까?')
    models, calls = scripted_models(tmp_path, [original.model_dump_json(), rewritten.model_dump_json()], True)
    output, metrics = models.chat({'text': '오늘 달리기를 할지 고민이야.', 'context': context(initiative=80)})
    refinement = metrics['quality_refinement']
    assert output == rewritten.model_dump(mode='json')
    assert len(calls) == 2
    assert [entry['phase'] for entry in metrics['attempts']] == ['initial', 'quality_refinement']
    assert refinement['original_candidate_sha256'] == digest(original.model_dump(mode='json'))
    assert refinement['original_raw_sha256'] == metrics['attempts'][0]['raw_sha256']
    assert refinement['generated_raw_sha256'] == metrics['attempts'][1]['raw_sha256']
    assert refinement['generated_candidate_sha256'] == digest(output)
    assert models.last_candidates[0]['result'] == original.model_dump(mode='json')
    assert models.last_candidates[1]['result'] == rewritten.model_dump(mode='json')
    assert all(candidate['contract_valid'] for candidate in models.last_candidates)
    assert refinement['original_quality']['passed'] is False
    assert refinement['outcome'] == 'selected_quality_pass'
    assert refinement['authority_personality'] == {'activity': 50, 'affinity': 50, 'initiative': 80}
    assert calls[1][0]['role'] == 'system'
    assert 'explicit_personality_axis_meta_explanation' in calls[1][0]['content']
    assert all(instruction in calls[1][0]['content'] for instruction in metrics['style']['guidance'])
    assert metrics['fallback'] is False
    assert metrics['quality']['manual_review_required'] is True


def test_refinement_failure_stays_quality_failure_and_never_requests_third_rewrite(tmp_path):
    original = result('활동 성향이 높으니 이야기하자.')
    rewritten = result('활동성이 높으니 가볍게 시작하자.')
    models, calls = scripted_models(tmp_path, [original.model_dump_json(), rewritten.model_dump_json()], True)
    output, metrics = models.chat({'text': '오늘 달리기를 할지 고민이야.', 'context': context(activity=80)})
    assert output == rewritten.model_dump(mode='json')
    assert len(calls) == 2
    assert metrics['quality']['passed'] is False
    assert metrics['quality_refinement']['outcome'] == 'selected_quality_fail'


def test_invalid_refinement_retains_real_validated_original_and_records_rejection(tmp_path):
    original = result('활동 성향이 높으니 이야기하자.')
    rewritten = result('기억해, 달리기를 좋아했지.')
    rewritten.memory_ids = ['not-provided']
    models, calls = scripted_models(tmp_path, [original.model_dump_json(), rewritten.model_dump_json()], True)
    output, metrics = models.chat({'text': '오늘 달리기를 할지 고민이야.', 'context': context(activity=80)})
    assert output == original.model_dump(mode='json')
    assert len(calls) == 2
    assert metrics['quality']['passed'] is False
    assert metrics['quality_refinement']['outcome'] == 'rejected_invalid_contract'
    assert metrics['quality_refinement']['selected_candidate'] == 'original'
    assert metrics['quality_refinement']['validation_code'] == 'unknown_memory_reference'
    assert models.last_candidates[1]['result'] == rewritten.model_dump(mode='json')
    assert models.last_candidates[1]['contract_valid'] is False
    assert metrics['fallback'] is False


def test_refinement_inference_failure_propagates_without_canned_response(tmp_path):
    original = result('활동 성향이 높으니 이야기하자.')
    models, calls = scripted_models(tmp_path, [original.model_dump_json(), RuntimeError('fixture failure')], True)
    with pytest.raises(RuntimeError, match='fixture failure'):
        models.chat({'text': '오늘 달리기를 할지 고민이야.', 'context': context(activity=80)})
    assert len(calls) == 2
    assert models.last_metrics['quality_refinement']['outcome'] == 'inference_failed'
    assert models.last_metrics['quality']['passed'] is False
    assert models.last_metrics['fallback'] is False


def test_contract_repair_and_quality_refinement_are_bounded_and_separately_recorded(tmp_path):
    original = result('주도성이 높으니 이야기하자.')
    rewritten = result('오늘의 소소한 발견부터 나눠 보자.')
    models, calls = scripted_models(tmp_path, ['{invalid', original.model_dump_json(), rewritten.model_dump_json()], True)
    output, metrics = models.chat({'text': '오늘 달리기를 할지 고민이야.', 'context': context(initiative=80)})
    assert output == rewritten.model_dump(mode='json')
    assert len(calls) == 3
    assert [a['phase'] for a in metrics['attempts']] == ['initial', 'contract_repair', 'quality_refinement']
    assert metrics['attempts'][0]['validation_error'] == 'ValidationError'


def test_quality_pass_does_not_trigger_refinement_or_prove_semantic_success(tmp_path):
    original = result('편하게 이야기하자.')
    models, calls = scripted_models(tmp_path, [original.model_dump_json()], True)
    _, metrics = models.chat({'text': '이야기하자.', 'context': context()})
    assert len(calls) == 1
    assert metrics['quality_refinement']['attempted'] is False
    assert metrics['quality']['passed'] is True
    assert metrics['quality']['heuristic_only'] is True


def test_style_refinement_cannot_change_game_classification(tmp_path):
    original = result('활동 성향이 높으니 이야기하자.')
    rewritten = result('같이 가볍게 이야기해 보자.')
    rewritten.classification.sentiment = 'positive'
    models, calls = scripted_models(tmp_path, [original.model_dump_json(), rewritten.model_dump_json()], True)
    output, metrics = models.chat({'text': '오늘 달리기를 할지 고민이야.', 'context': context(activity=80)})
    assert output == original.model_dump(mode='json')
    assert len(calls) == 2
    assert metrics['quality_refinement']['validation_code'] == 'quality_refinement_changed_classification'
    assert metrics['quality_refinement']['outcome'] == 'rejected_invalid_contract'
    assert metrics['quality']['passed'] is False


def test_refinement_uses_fresh_original_query_without_assistant_candidate_anchoring():
    import json
    payload = {'text': '활동성과 친밀도를 참고해 오늘 달리기를 고민하는 나에게 답해 줘.',
               'context': context(activity=80)}
    original = result('활동 성향이 높으니까 천천히 시작하자.')
    style = style_context(payload['context'])
    prompt = refinement_messages(payload, original, style, ['explicit_personality_axis_meta_explanation'])
    assert [m['role'] for m in prompt] == ['system', 'user']
    assert original.speech not in ''.join(m['content'] for m in prompt)
    user = json.loads(prompt[-1]['content'])
    assert user['user_text'] == payload['text']
    assert user['context'] == payload['context']
    assert user['fixed_classification'] == original.classification.model_dump(mode='json')
    assert 'style' not in user
    assert all(guidance in prompt[0]['content'] for guidance in style['guidance'])
    assert user['quality_feedback_codes'] == ['explicit_personality_axis_meta_explanation']


def test_model_projection_preserves_facts_memories_and_original_utterance_without_raw_personality():
    from copy import deepcopy
    import json
    ctx = context(activity=80, affinity=20)
    ctx['memories'] = [{'id': 'provided-id', 'content': '가명 사용자는 보리차를 좋아한다.', 'source_id': 'valid-source', 'source_revision': 1}]
    ctx['state']['trend'] = {'activity': 80, 'affinity': 20, 'initiative': 50}
    payload = {'text': '성격을 참고해서 달리기를 고민하는 나에게 답해 줘.', 'context': ctx}
    original = deepcopy(payload)
    prompt, style = projected_messages(payload)
    user = json.loads(prompt[1]['content'])
    assert payload == original
    assert user['user_text'] == payload['text']
    assert user['context']['memories'] == ctx['memories']
    assert user['context']['settings'] == ctx['settings']
    assert all(key not in user['context'] for key in ('state', 'personality', 'style', 'trend'))
    assert all(key not in user['context']['verified_game_facts'] for key in ('activity', 'affinity', 'initiative'))
    assert style['personality'] == {'activity': 80, 'affinity': 20, 'initiative': 50}


@pytest.mark.parametrize('axis', ['activity', 'affinity', 'initiative'])
def test_projection_axis_changes_only_its_corresponding_behavior_direction(axis):
    low = {'text': '가명 대화', 'context': context(**{axis: 10})}
    high = {'text': '가명 대화', 'context': context(**{axis: 90})}
    low_directions = model_projection(low, style_context(low['context']))[1]
    high_directions = model_projection(high, style_context(high['context']))[1]
    index = ['activity', 'affinity', 'initiative'].index(axis)
    assert [i for i in range(3) if low_directions[i] != high_directions[i]] == [index]
    assert not any(word in '\n'.join(high_directions) for word in ('활동성', '친밀도', '주도성', '높은', '낮은'))


def test_projected_refinement_retains_projection_and_fixed_classification_without_answer_copy():
    import json
    payload = {'text': '오늘 얘기하자.', 'context': context(affinity=20)}
    original = result('나는 네 곁에 항상 있을게.')
    style = style_context(payload['context'])
    prompt = refinement_messages(payload, original, style, ['low_affinity_overfamiliar_assurance'], projected=True)
    user = json.loads(prompt[1]['content'])
    assert original.speech not in ''.join(m['content'] for m in prompt)
    assert 'personality' not in user['context'] and 'state' not in user['context']
    assert user['fixed_classification'] == original.classification.model_dump(mode='json')


def test_bounded_search_uses_three_real_candidate_slots_distinct_seeds_and_selects_fewest_flags(tmp_path):
    original = result('오늘은 조용히 네 옆에 있을게.')
    second = result('오늘은 조용히 이야기하자.')
    third = result('반가워! 오늘 있었던 작은 발견부터 나눠 보자.')
    models, calls = scripted_models(tmp_path, [r.model_dump_json() for r in (original, second, third)], True)
    models.config.update(bounded_candidate_search=True)
    selected, metrics = models.chat({'text': '오늘 이야기하고 싶어.', 'context': context(activity=90)})
    assert len(calls) == 3
    assert selected == third.model_dump(mode='json')
    assert [a['seed'] for a in metrics['attempts']] == [20261022, 20261023, 20261024]
    assert [c['generation_seed'] for c in models.last_candidates] == [20261022, 20261023, 20261024]
    assert metrics['quality_refinement']['selected_candidate_index'] == 2
    assert metrics['quality_refinement']['all_valid_candidates_quality_failed'] is False
    assert metrics['quality']['heuristic_only'] is True
    assert metrics['quality']['manual_review_required'] is True


def test_all_bounded_candidates_failing_stays_failed_and_preserves_each_candidate(tmp_path):
    replies = [result('활동성이 높으니 오늘은 조용히 이야기하자.'),
               result('오늘은 조용히 네 옆에 있을게.'), result('오늘은 조용히 나눠 보자.')]
    models, calls = scripted_models(tmp_path, [r.model_dump_json() for r in replies], True)
    models.config.update(bounded_candidate_search=True)
    selected, metrics = models.chat({'text': '오늘 이야기하고 싶어.', 'context': context(activity=90)})
    assert len(calls) == len(models.last_candidates) == 3
    assert selected == replies[-1].model_dump(mode='json')
    assert metrics['quality']['passed'] is False
    assert metrics['quality_refinement']['all_valid_candidates_quality_failed'] is True
    assert metrics['quality_refinement']['outcome'] == 'selected_quality_fail'
    assert all(not c['quality']['passed'] for c in models.last_candidates)


def test_bounded_search_never_selects_unknown_memory_or_changed_classification(tmp_path):
    original = result('활동성이 높아.')
    invalid_memory = result('좋아! 같이 이야기해 보자.')
    invalid_memory.memory_ids = ['unknown-memory']
    invalid_classification = result('편하게 이야기하자.')
    invalid_classification.classification.confidence = .1
    models, calls = scripted_models(tmp_path, [r.model_dump_json() for r in (original, invalid_memory, invalid_classification)], True)
    models.config.update(bounded_candidate_search=True)
    selected, metrics = models.chat({'text': '오늘 이야기하고 싶어.', 'context': context(activity=90)})
    assert len(calls) == 3
    assert selected == original.model_dump(mode='json')
    assert [c['contract_valid'] for c in models.last_candidates] == [True, False, False]
    assert [t['validation_code'] for t in metrics['quality_refinement']['attempts']] == ['unknown_memory_reference', 'quality_refinement_changed_classification']
    assert metrics['quality_refinement']['selected_candidate_index'] == 0


def test_contract_repair_consumes_same_three_generation_budget_as_search(tmp_path):
    original, better = result('주도성이 높으니 이야기하자.'), result('오늘의 작은 즐거움부터 나눠 보자.')
    models, calls = scripted_models(tmp_path, ['{invalid', original.model_dump_json(), better.model_dump_json()], True)
    models.config.update(bounded_candidate_search=True)
    selected, metrics = models.chat({'text': '이야기하고 싶어.', 'context': context(initiative=90)})
    assert len(calls) == 3
    assert selected == better.model_dump(mode='json')
    assert [a['seed'] for a in metrics['attempts']] == [20261022, 20261023, 20261024]
    assert metrics['quality_refinement']['maximum_generations'] == 1
    assert len(models.last_candidates) == 2


def test_bounded_search_can_explore_without_claiming_initial_semantic_failure(tmp_path):
    replies = [result('편하게 이야기하자.'), result('반가워, 이야기해 줘.'), result('좋아, 함께 이야기하자.')]
    models, calls = scripted_models(tmp_path, [r.model_dump_json() for r in replies], True)
    models.config.update(bounded_candidate_search=True)
    selected, metrics = models.chat({'text': '대화하자.', 'context': context()})
    assert len(calls) == 3
    assert selected == replies[-1].model_dump(mode='json')
    assert metrics['quality_refinement']['original_quality']['passed'] is True
    assert metrics['quality_refinement']['attempts'][0]['cause_codes'] == ['bounded_behavioral_diversity_review_not_a_failure_verdict']
    assert metrics['quality']['manual_review_required'] is True


@pytest.mark.parametrize('budget', [1, 2])
def test_configured_smaller_generation_budget_is_respected(tmp_path, budget):
    reply = result('활동성이 높으니 조용히 이야기하자.')
    models, calls = scripted_models(tmp_path, [reply.model_dump_json()] * budget, True)
    models.config.update(bounded_candidate_search=True, max_real_generations=budget)
    _, metrics = models.chat({'text': '이야기하고 싶어.', 'context': context(activity=90)})
    assert len(calls) == budget
    assert metrics['quality']['passed'] is False


@pytest.mark.parametrize('key,value', [('max_real_generations', 0), ('max_real_generations', 4),
                                       ('max_real_generations', True), ('max_quality_candidates', 3),
                                       ('max_quality_candidates', False)])
def test_invalid_unbounded_generation_configuration_rejected_before_generation(tmp_path, key, value):
    models, calls = scripted_models(tmp_path, [], True)
    models.config[key] = value
    with pytest.raises(ValueError, match='Bounded generation budget'):
        models.chat({'text': '이야기하자.', 'context': context()})
    assert calls == []


@pytest.mark.parametrize('base', [True, -1, 2 ** 32, .5])
def test_invalid_seed_is_rejected_without_defaulting_or_model_load(tmp_path, base):
    models = LocalModels({'base_seed': base}, tmp_path)
    with pytest.raises(ValueError, match='base_seed'):
        models.generation_seed(0)


def test_seed_wraparound_is_deterministic(tmp_path):
    models = LocalModels({'base_seed': 2 ** 32 - 1}, tmp_path)
    assert [models.generation_seed(i) for i in range(3)] == [2 ** 32 - 1, 0, 1]


def test_meta_without_high_low_words_and_self_style_narration_remain_quality_failures():
    payload = {'text': '이야기하고 싶어.', 'context': context(activity=90)}
    style = style_context(payload['context'])
    assert 'explicit_personality_axis_meta_explanation' in evaluate_style_quality(payload, result('친밀도는 아직 쌓인 편이야.'), style)['failures']
    assert 'style_described_rather_than_expressed' in evaluate_style_quality(payload, result('내가 말을 조금 더 가볍게 해 볼게.'), style)['failures']
