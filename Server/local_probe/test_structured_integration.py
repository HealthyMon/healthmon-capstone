"""CPU-only integration: exact original input on every bounded generation."""
from copy import deepcopy
import json

import pytest

from Server.local_probe.gpu_gateway import digest, messages, projected_messages
from Server.local_probe.test_compact_integration import model
from Server.local_probe.test_contract import context, result


def payload():
    value = {'text': '  오늘은 그냥 이야기하고 싶어.\n그대로 들어 줘.  ',
             'context': context(activity=90)}
    value['context']['arbitrary_future_field'] = {'nested': [None, 7, {'authority': 'data only'}]}
    return value


@pytest.mark.parametrize('projected', [False, True])
def test_default_off_keeps_legacy_initial_and_retry_inputs_exact(tmp_path, projected):
    raw = result('반가워, 편하게 말해 줘.').model_dump_json()
    before, old_calls = model(tmp_path / 'old', [raw] * 3, prompt_projection=projected)
    after, new_calls = model(tmp_path / 'new', [raw] * 3, prompt_projection=projected, structured_dialogue=False)
    a, am = before.chat(payload())
    b, bm = after.chat(payload())
    assert a == b and am == bm and old_calls == new_calls
    assert 'structured_dialogue' not in bm


def test_structured_every_candidate_repeats_exact_full_input_with_distinct_seeds(tmp_path):
    outputs = [result(text).model_dump_json() for text in ('조용히 곁에 있을게.', '오늘 이야기부터 해 볼까?', '편하게 들려줘.')]
    instance, calls = model(tmp_path, outputs, structured_dialogue=True, compact_voice=True,
                            full_personality_facts=True, prompt_projection=True)
    value, saved = payload(), deepcopy(payload())
    _, metrics = instance.chat(value)
    assert value == saved and len(calls) == 3 and calls[0] == calls[1] == calls[2]
    assert [x['role'] for x in calls[0]] == ['system', 'user', 'user']
    assert json.loads(calls[0][1]['content'])['DATA']['context'] == value['context']
    assert calls[0][2]['content'] == value['text']
    assert all('fixed_classification' not in p[1]['content'] and 'quality_feedback_codes' not in p[1]['content'] for p in calls)
    assert [x['seed'] for x in metrics['attempts']] == [20261022, 20261023, 20261024]
    audit = metrics['structured_dialogue']
    assert audit['initial_messages_sha256'] == digest(calls[0])
    assert audit['source_context_sha256'] == digest(value['context'])
    assert audit['source_text_sha256'] == digest(value['text'])
    assert audit['quality_feedback_in_model_input'] is False
    assert all(t['cause_codes'] for t in metrics['quality_refinement']['attempts'])
    assert metrics['quality_refinement']['prompt_strategy'] == 'identical_structured_dialogue_distinct_seed.v1'


def test_structured_contract_repair_also_keeps_original_input_and_audits_failure(tmp_path):
    valid = result('편하게 이야기해 줘.').model_dump_json()
    instance, calls = model(tmp_path, ['not JSON', valid, valid], structured_dialogue=True,
                            compact_voice=True, full_personality_facts=True)
    _, metrics = instance.chat(payload())
    assert len(calls) == 3 and calls[0] == calls[1] == calls[2]
    assert [a['phase'] for a in metrics['attempts']] == ['initial', 'contract_repair', 'quality_refinement']
    assert metrics['attempts'][0]['validation_error'] == 'ValidationError'
    assert all(len(p) == 3 for p in calls)
    assert metrics['quality_refinement']['maximum_generations'] == 1


@pytest.mark.parametrize('field,value', [('sentiment', 'positive'), ('confidence', .79)])
def test_structured_keeps_exact_classification_gate_including_confidence(tmp_path, field, value):
    original = result('편하게 이야기해 줘.')
    changed = result('오늘 일부터 들려줄래?')
    setattr(changed.classification, field, value)
    instance, calls = model(tmp_path, [original.model_dump_json(), changed.model_dump_json(), changed.model_dump_json()],
                            structured_dialogue=True, compact_voice=True, full_personality_facts=True)
    output, metrics = instance.chat(payload())
    assert output == original.model_dump(mode='json') and calls[0] == calls[1] == calls[2]
    assert all(not c['contract_valid'] for c in instance.last_candidates[1:])
    assert all(t['validation_code'] == 'quality_refinement_changed_classification' for t in metrics['quality_refinement']['attempts'])


def test_structured_authority_mismatch_rejected_without_generation(tmp_path):
    instance, calls = model(tmp_path, [], structured_dialogue=True, compact_voice=True, full_personality_facts=True)
    value = payload()
    value['context']['state']['activity'] = 89
    with pytest.raises(ValueError, match='authority_mismatch'):
        instance.chat(value)
    assert calls == [] and instance.last_candidates == [] and instance.last_metrics['attempts'] == []


def test_structured_audit_never_claims_original_context_numbers_were_removed(tmp_path):
    raw = result('편하게 이야기해 줘.').model_dump_json()
    instance, calls = model(tmp_path, [raw]*3, structured_dialogue=True, compact_voice=True,
                            full_personality_facts=False)
    _, metrics = instance.chat(payload())
    assert json.loads(calls[0][1]['content'])['DATA']['context']['state']['activity'] == 90
    assert metrics['prompt_projection']['numeric_personality_not_in_model_context'] is False
