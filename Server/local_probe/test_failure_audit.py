"""CPU-only request isolation and inference-failure audit regressions."""
from copy import deepcopy
import hashlib
import json

import pytest

from Server.local_probe.test_contract import context, result, scripted_models


@pytest.mark.parametrize('invalid', ['authority', 'budget'])
def test_pre_generation_failure_cannot_retain_previous_request_audit(tmp_path, invalid):
    raw = result('오늘 있었던 일부터 함께 이야기해 보자.').model_dump_json()
    models, calls = scripted_models(tmp_path, [raw], False)
    models.config['full_personality_facts'] = True
    payload = {'text': '오늘은 이야기하고 싶어.', 'context': context(activity=80)}
    models.chat(payload)
    assert models.last_candidates and models.last_metrics['raw_sha256']

    failing = deepcopy(payload)
    if invalid == 'authority':
        failing['context']['state']['activity'] = 79
        expected = 'full_personality_facts_authority_mismatch'
    else:
        models.config['max_real_generations'] = 0
        expected = 'Bounded generation budget'
    with pytest.raises(ValueError, match=expected):
        models.chat(failing)

    assert len(calls) == 1
    assert models.last_candidates == []
    assert models.last_metrics == {'attempts': [], 'fallback': False}


@pytest.mark.parametrize('repair', [False, True])
def test_initial_or_repair_inference_exception_preserves_current_attempt_history(tmp_path, repair):
    invalid_raw = 'invalid JSON from the first generation'
    private_error = 'fixture-only private diagnostic that must not enter audit'
    outputs = [invalid_raw, TimeoutError(private_error)] if repair else [TimeoutError(private_error)]
    models, calls = scripted_models(tmp_path, outputs, False)
    models.last_metrics = {'raw_sha256': 'previous-request-hash'}
    models.last_candidates = [{'result': 'previous-request-response'}]

    with pytest.raises(TimeoutError, match=private_error):
        models.chat({'text': '오늘은 이야기하고 싶어.', 'context': context()})

    attempts = models.last_metrics['attempts']
    assert len(calls) == len(attempts) == (2 if repair else 1)
    assert [attempt['phase'] for attempt in attempts] == (['initial', 'contract_repair'] if repair else ['initial'])
    assert [attempt['seed'] for attempt in attempts] == ([20261022, 20261023] if repair else [20261022])
    failed = attempts[-1]
    assert failed['outcome'] == 'inference_failed'
    assert failed['error_type'] == 'TimeoutError'
    assert 'raw_sha256' not in failed
    if repair:
        assert attempts[0]['raw_sha256'] == hashlib.sha256(invalid_raw.encode()).hexdigest()
        assert attempts[0]['validation_error'] == 'ValidationError'
        assert attempts[0]['validation_fields']
    assert models.last_candidates == []
    assert models.last_metrics['fallback'] is False
    audit = json.dumps(models.last_metrics)
    assert private_error not in audit and invalid_raw not in audit
    assert 'previous-request' not in audit
