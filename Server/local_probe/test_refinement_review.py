"""CPU-only verification of deferred real-inference review preparation."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from Server.healthmon.rules import initial_state
from Server.local_probe.gpu_gateway import atomic_json, digest
from Server.local_probe import run_refinement_review as review


def native_fixture():
    cases = []
    for axis in review.AXES:
        for side, value in (('low', 20), ('high', 80)):
            state = dict(initial_state(), **{axis: value}, settings={'name': '가명몽글', 'speech_level': 'casual'})
            cases.append({'case_id': axis + '-' + side, 'prompt': '세 성격 축을 참고해서 달리기 고민에 두 문장으로 답해 줘.',
                          'expected_state': state})
    return {'isolated_fixture': True, 'cases': cases}


def speech(text):
    return {'speech': text, 'emotion': 'neutral', 'animation': 'idle', 'memory_ids': [],
            'classification': {'target': 'exercise', 'sentiment': 'neutral', 'motivation': 'neutral',
                               'character_affection': 'neutral', 'acceptance': 'none', 'confidence': .8, 'proposal_id': None}}


def evidence(tmp_path):
    case = review.build_cases(native_fixture())[-1]
    request = {'contract_version': 'healthmon.ai.v1', 'request_id': 'fictional-review-request-12345',
               'pet_id': 'fictional-review-pet', 'input': case['input']}
    original, refined = speech('주도성이 높으니 이야기하자.'), speech('오늘 있었던 작은 즐거움부터 나눠 볼까?')
    envelope = {'contract_version': 'healthmon.ai.v1', 'request_id': request['request_id'], 'provenance': 'real', 'result': refined}
    quality = {'passed': True, 'failures': [], 'heuristic_only': True, 'manual_review_required': True}
    cache = {'fingerprint': digest(request), 'envelope': envelope, 'model': {'model_version': 'v1'},
             'candidates': [{'phase': 'original', 'candidate_sha256': digest(original), 'result': original, 'contract_valid': True},
                            {'phase': 'refined', 'candidate_sha256': digest(refined), 'result': refined, 'contract_valid': True}],
             'metrics': {'fallback': False, 'quality': quality, 'quality_refinement': {'original_candidate_sha256': digest(original)},
                         'attempts': [{'phase': phase, 'generated_tokens': 20, 'generation_seconds': .5,
                                       'peak_allocated_bytes': 1024, 'raw_sha256': digest(phase)} for phase in ('initial', 'quality_refinement')]}}
    path = tmp_path / 'responses' / (digest({'capability': 'chat', 'request_id': request['request_id'], 'pet_id': request['pet_id']}) + '.json')
    path.parent.mkdir()
    atomic_json(path, cache)
    response = httpx.Response(200, json=envelope, request=httpx.Request('POST', review.ORIGIN + '/v1/chat'))
    return case, request, response, cache, path


def test_plan_contains_exact_native_prompts_states_and_separate_neutral_suite():
    source = native_fixture()
    original = deepcopy(source)
    cases = review.build_cases(source)
    assert len(cases) == 12
    assert source == original
    for case in cases:
        if case['suite'] == 'native':
            native = next(c for c in source['cases'] if c['case_id'] == case['native_case_id'])
            assert case['input']['text'] == native['prompt']
            assert case['input']['context']['state'] == native['expected_state']
            assert case['native_prompt_sha256'] == hashlib.sha256(native['prompt'].encode()).hexdigest()
            assert case['value'] in (20, 80)
        else:
            assert case['input']['text'] == review.NEUTRAL_TEXT
            assert case['value'] in (10, 90)


@pytest.mark.parametrize('mutation', ['real_user', 'missing_case', 'wrong_authority'])
def test_nonfixture_or_changed_native_authority_is_rejected(mutation):
    source = native_fixture()
    if mutation == 'real_user':
        source['isolated_fixture'] = False
    elif mutation == 'missing_case':
        source['cases'].pop()
    else:
        source['cases'][0]['expected_state']['activity'] = 21
    with pytest.raises(ValueError):
        review.build_cases(source)


def test_pair_review_uses_behavioral_rubrics_and_stays_pending():
    pairs = review.pair_review_plan(review.build_cases(native_fixture()))
    assert len(pairs) == 6
    assert all(pair['semantic_pass'] is None and pair['manual_status'] == 'pending' for pair in pairs)
    assert all(len(pair['case_ids']) == 2 for pair in pairs)
    assert 'energy_difference_insufficient' in pairs[0]['rubric']['failure_codes']
    assert 'relationship_distance_contrast_insufficient' in pairs[1]['rubric']['failure_codes']


def test_identical_low_high_reply_is_flagged_but_different_reply_never_proves_semantic_pass():
    report = {'pair_reviews': review.pair_review_plan(review.build_cases(native_fixture())), 'cases': [],
              'all_automatic_quality_checks_passed': True}
    pair = next(p for p in report['pair_reviews'] if p['suite'] == 'neutral' and p['axis'] == 'initiative')
    report['cases'] = [{'case_id': ident, 'selected_response': {'speech': '같은 수동 응답.'}} for ident in pair['case_ids']]
    review.annotate_pair_contrasts(report)
    assert pair['identical_low_high_response'] is True
    assert pair['failure_codes'] == ['identical_low_high_response']
    assert report['all_automatic_quality_checks_passed'] is False
    assert pair['semantic_pass'] is None
    report['cases'][1]['selected_response']['speech'] = '다르지만 품질은 미검증.'
    review.annotate_pair_contrasts(report)
    assert pair['semantic_pass'] is None


def test_inspection_preserves_both_candidates_and_generation_evidence_without_semantic_pass(tmp_path):
    case, request, response, cache, path = evidence(tmp_path)
    record = review.inspect_response(case, request, response, tmp_path)
    assert record['actual_gpu_execution_proven'] is True
    assert len(record['model_candidates']) == 2
    assert record['selected_response'] == cache['candidates'][1]['result']
    assert record['manual_semantic_status'] == 'pending'
    assert record['cache_path'] == str(path.resolve())


@pytest.mark.parametrize('mutation', ['original_tampered', 'request_tampered', 'test_double', 'four_generations', 'two_refinements'])
def test_inspection_rejects_missing_or_tampered_execution_evidence(tmp_path, mutation):
    case, request, response, cache, path = evidence(tmp_path)
    if mutation == 'original_tampered':
        cache['candidates'][0]['result']['speech'] = '바뀐 후보.'
    elif mutation == 'request_tampered':
        cache['fingerprint'] = '0' * 64
    elif mutation == 'test_double':
        cache['metrics']['attempts'][0]['test_double'] = True
    elif mutation == 'four_generations':
        cache['metrics']['attempts'] += [dict(cache['metrics']['attempts'][0])] * 2
    else:
        cache['metrics']['attempts'].append(dict(cache['metrics']['attempts'][-1]))
    atomic_json(path, cache)
    with pytest.raises(ValueError):
        review.inspect_response(case, request, response, tmp_path)


@pytest.mark.parametrize('change', ['disabled_refinement', 'different_adapter', 'different_version', 'not_ready', 'quantized'])
def test_execution_preflight_requires_unchanged_real_ready_bf16_v1_with_refinement(change):
    expected = {'model_version': 'v1', 'adapter_sha256': 'a' * 64, 'base_revision': 'existing'}
    health = {'ready': True, 'provenance': 'real', 'local_acceptance_only': True, 'quality_refinement_enabled': True,
              'model': dict(expected, dtype='bfloat16', downloaded=False)}
    health['model']['adapter_activation'] = {'verified_expected_adapter_active': True,
        'selected_adapter_name': 'existing_v1', 'active_adapter_names': ['existing_v1'],
        'all_layers_select_expected_adapter': True, 'verified_existing_v1_active': True}
    review.assert_ready(health, expected)
    if change == 'disabled_refinement':
        health['quality_refinement_enabled'] = False
    elif change == 'different_adapter':
        health['model']['adapter_sha256'] = 'b' * 64
    elif change == 'different_version':
        health['model']['model_version'] = 'v2'
    elif change == 'not_ready':
        health['ready'] = False
    else:
        health['model']['dtype'] = 'int8'
    with pytest.raises(ValueError):
        review.assert_ready(health, expected)


def test_prepare_default_performs_no_http_and_does_not_overwrite_prior_reports(tmp_path, monkeypatch, capsys):
    runtime = tmp_path / '.runtime' / 'local-gpu-probe'
    runtime.mkdir(parents=True)
    adapter = tmp_path / 'adapter'
    adapter.mkdir()
    atomic_json(adapter / 'healthmon-model.json', {'model_version': 'v1', 'base_revision': 'a' * 40,
                'status': 'ready', 'format': 'peft_lora', 'base_model_id': 'Qwen/Qwen3.5-9B',
                'base_config_sha256': 'b' * 64,
                'artifact_checksums': {'adapter_model.safetensors': 'a' * 64, 'adapter_config.json': 'c' * 64}})
    config = runtime / 'private.json'
    atomic_json(config, {'environment': 'test', 'server_token': 'secret-that-must-not-print', 'adapter_path': str(adapter)})
    native = tmp_path / '.runtime' / 'native.json'
    atomic_json(native, native_fixture())
    previous = runtime / 'previous.json'
    previous.write_text('{"do_not_replace":true}', encoding='utf-8')
    original = previous.read_bytes()
    monkeypatch.setattr(review, 'ROOT', tmp_path)
    monkeypatch.setattr(review.httpx, 'Client', lambda *a, **k: pytest.fail('Offline preparation must not open HTTP'))
    monkeypatch.setattr('sys.argv', ['review', '--config', str(config), '--native-config', str(native)])
    review.main()
    printed = capsys.readouterr().out
    assert 'secret-that-must-not-print' not in printed
    summary = json.loads(printed)
    assert summary['http_requests'] == 0 and summary['gpu_accessed'] is False
    report = json.loads(Path(summary['report']).read_text(encoding='utf-8'))
    assert len(report['case_plan']) == 12
    assert report['semantic_quality_passed'] is None
    assert previous.read_bytes() == original
    assert report['cases'] == []
