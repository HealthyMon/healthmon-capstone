"""CPU-only wiring checks: same authority, first voice, budget and real-output policy."""
from copy import deepcopy
import hashlib
import json

import pytest

from Server.local_probe.compact_voice import compact_messages, voice_sentence
from Server.local_probe.gpu_gateway import LocalModels, digest, messages, projected_messages
from Server.local_probe.test_contract import context, result


def model(tmp_path, outputs, **options):
    instance = LocalModels(dict(quality_refinement=True, bounded_candidate_search=True,
                               max_real_generations=3, max_quality_candidates=2, **options), tmp_path)
    calls = []
    values = iter(outputs)

    def generate(prompt, seed=None):
        calls.append(deepcopy(prompt))
        raw = next(values)
        instance.last_metrics = {'raw_sha256': hashlib.sha256(raw.encode()).hexdigest(),
                                'generated_tokens': 10, 'generation_seconds': .1,
                                'peak_allocated_bytes': 1, 'test_double': True, 'seed': seed}
        return raw

    instance.generate = generate
    return instance, calls


@pytest.mark.parametrize('projected', [False, True])
def test_disabled_compact_keeps_existing_initial_prompt_exact(tmp_path, projected):
    raw = result('오늘 있었던 일을 들려줘도 좋아.').model_dump_json()
    instance, calls = model(tmp_path, [raw] * 3, compact_voice=False, prompt_projection=projected)
    payload = {'text': '오늘은 이야기하고 싶어.', 'context': context(activity=90)}
    expected, _ = projected_messages(payload) if projected else messages(payload)
    _, metrics = instance.chat(payload)
    assert calls[0] == expected
    assert metrics['compact_voice']['enabled'] is False


def test_compact_first_voice_and_frozen_facts_survive_all_real_candidate_slots(tmp_path):
    outputs = [result(text).model_dump_json() for text in ('편하게 말해 줘.', '반가워, 오늘 이야기를 들려줘.', '지금 마음에 드는 이야기를 해 볼까?')]
    instance, calls = model(tmp_path, outputs, compact_voice=True)
    payload = {'text': '오늘은 이야기하고 싶어.', 'context': context(activity=90)}
    saved = deepcopy(payload)
    expected, style = compact_messages(payload, enabled=True)
    output, metrics = instance.chat(payload)
    assert payload == saved and calls[0] == expected
    assert len(calls) == 3 and len(instance.last_candidates) == 3
    assert all(prompt[0]['content'].splitlines()[0] == voice_sentence(style) for prompt in calls)
    assert [a['seed'] for a in metrics['attempts']] == [20261022, 20261023, 20261024]
    assert metrics['compact_voice']['initial_voice_sha256'] == digest(voice_sentence(style))
    assert all(a['system_first_voice_sha256'] == metrics['compact_voice']['initial_voice_sha256'] for a in metrics['quality_refinement']['attempts'])
    original_user = json.loads(calls[0][1]['content'])
    for prompt in calls[1:]:
        user = json.loads(prompt[1]['content'])
        assert user['context'] == original_user['context']
        assert user['user_text'] == payload['text']
        assert user['fixed_classification'] == result('내용').classification.model_dump(mode='json')
    assert output in [candidate['result'] for candidate in instance.last_candidates if candidate['contract_valid']]
    assert metrics['fallback'] is False


def test_compact_contract_repair_consumes_same_three_generation_budget(tmp_path):
    raw = result('반가워, 편하게 이야기하자.').model_dump_json()
    instance, calls = model(tmp_path, ['invalid JSON', raw, raw], compact_voice=True)
    payload = {'text': '오늘은 이야기하고 싶어.', 'context': context(activity=90)}
    _, metrics = instance.chat(payload)
    assert len(calls) == 3
    assert [a['phase'] for a in metrics['attempts']] == ['initial', 'contract_repair', 'quality_refinement']
    assert len({prompt[0]['content'].splitlines()[0] for prompt in calls}) == 1
    assert metrics['quality_refinement']['maximum_generations'] == 1


def test_compact_never_selects_candidate_with_changed_classifier(tmp_path):
    original = result('편하게 말해 줘.')
    changed = result('오늘 이야기를 시작해 볼까?')
    changed.classification.sentiment = 'positive'
    instance, _ = model(tmp_path, [original.model_dump_json(), changed.model_dump_json(), changed.model_dump_json()], compact_voice=True)
    output, metrics = instance.chat({'text': '오늘은 이야기하고 싶어.', 'context': context(activity=90)})
    assert output == original.model_dump(mode='json')
    assert all(not candidate['contract_valid'] for candidate in instance.last_candidates[1:])
    assert all(a['validation_code'] == 'quality_refinement_changed_classification' for a in metrics['quality_refinement']['attempts'])
