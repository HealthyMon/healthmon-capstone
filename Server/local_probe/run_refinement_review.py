"""Prepare, or explicitly execute, fictional same-v1 refinement acceptance.

The default prepares a new ignored report without HTTP, model imports or GPU
access. Execution must be explicitly requested after the GPU has been released.
No private keys, fixture text or model replies are printed to stdout.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import uuid

import httpx

from Server.healthmon.gateway import Envelope, Speech
from Server.healthmon.rules import initial_state
from Server.local_probe.gpu_gateway import ROOT, atomic_json, digest, expected_model_mode, file_digest, selected_model_descriptor, style_context, validate_contract

AXES = ('activity', 'affinity', 'initiative')
NEUTRAL_TEXT = '오늘은 그냥 나랑 이야기하고 싶어. 너다운 말투로 한두 마디 해 줘.'
NATIVE_IDS = tuple(axis + '-' + side for axis in AXES for side in ('low', 'high'))
ORIGIN = 'http://127.0.0.1:18091'


def build_cases(native_config):
    if native_config.get('isolated_fixture') is not True:
        raise ValueError('Native input must be an explicitly isolated fictional fixture')
    native = {item['case_id']: item for item in native_config.get('cases', []) if item['case_id'] in NATIVE_IDS}
    if set(native) != set(NATIVE_IDS):
        raise ValueError('All six original native axis cases are required')
    cases = []
    for axis in AXES:
        for side, value in (('low', 10), ('high', 90)):
            state = dict(initial_state(), **{axis: value})
            context = {'state': state, 'personality': {key: state[key] for key in AXES},
                       'settings': {'name': '테스트몽글', 'speech_level': 'casual', 'profanity': 'none'},
                       'memories': [], 'recent': []}
            cases.append({'suite': 'neutral', 'case_id': 'neutral-' + axis + '-' + side,
                          'axis': axis, 'side': side, 'value': value,
                          'input': {'text': NEUTRAL_TEXT, 'context': context}})
    for axis in AXES:
        for side, value in (('low', 20), ('high', 80)):
            source = native[axis + '-' + side]
            state = deepcopy(source['expected_state'])
            expected = {key: value if key == axis else 50 for key in AXES}
            if {key: state.get(key) for key in AXES} != expected:
                raise ValueError('Native authority axis state must exactly retain 20/80 and other axes50')
            prompt = source.get('prompt')
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError('Original native prompt is missing')
            settings = deepcopy(state.get('settings'))
            if not isinstance(settings, dict):
                raise ValueError('Original native settings are required')
            context = {'state': state, 'personality': expected, 'settings': settings,
                       'memories': [], 'recent': [],
                       'classification_policy': {
                           'target_priority': ['direct_character_expression', 'actual_proposal_decision', 'exercise', 'food', 'other'],
                           'exercise_complaints_are_not_character_dislike': True,
                           'proposal_requires_valid_visible_id': True,
                           'never_invent_memory_or_exercise_completion': True}}
            cases.append({'suite': 'native', 'case_id': 'native-' + source['case_id'],
                          'native_case_id': source['case_id'], 'axis': axis, 'side': side,
                          'value': value, 'native_prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
                          'authority_state_sha256': digest(state),
                          'context_scope': 'original fixture prompt/state/settings; empty memory/recent fixture',
                          'input': {'text': prompt, 'context': context}})
    for case in cases:
        style_context(case['input']['context'])
    return cases


def pair_review_plan(cases):
    rubrics = {
        'activity': {'low': 'Calm tempo and restrained energy.',
                     'high': 'Noticeably lively actual language and tempo while respecting worry/rest; naming a trait is not expression.',
                     'failure_codes': ['energy_difference_insufficient', 'explicit_personality_axis_meta_explanation']},
        'affinity': {'low': 'Polite distance without asserting closeness or invented shared history.',
                     'high': 'Natural warmth and closer rapport without explaining closeness or inventing memories.',
                     'failure_codes': ['relationship_distance_contrast_insufficient', 'low_affinity_overfamiliar_assurance',
                                       'explicit_personality_axis_meta_explanation']},
        'initiative': {'low': 'Listens and leaves room without imposing a new task.',
                       'high': 'Opens a low-pressure topic or choice, without requiring a question mark or exercise task.',
                       'failure_codes': ['initiative_behavior_contrast_insufficient', 'explicit_personality_axis_meta_explanation']}}
    return [{'suite': suite, 'axis': axis, 'case_ids': [c['case_id'] for c in cases if c['suite'] == suite and c['axis'] == axis],
             'manual_status': 'pending', 'rubric': rubrics[axis],
             'semantic_pass': None, 'failure_codes': []}
            for suite in ('neutral', 'native') for axis in AXES]


def annotate_pair_contrasts(report):
    """Identical wording is an observable failure in these comparison fixtures.

    Different wording never proves successful energy/distance/initiative style.
    """
    for pair in report['pair_reviews']:
        matched = [case for case in report['cases'] if case['case_id'] in pair['case_ids']]
        identical = len(matched) == 2 and matched[0]['selected_response']['speech'] == matched[1]['selected_response']['speech']
        pair['identical_low_high_response'] = identical
        pair['failure_codes'] = [code for code in pair['failure_codes'] if code != 'identical_low_high_response']
        if identical:
            if 'identical_low_high_response' not in pair['failure_codes']:
                pair['failure_codes'].append('identical_low_high_response')
            report['all_automatic_quality_checks_passed'] = False


def expected_identity(config):
    mode = expected_model_mode(config)
    manifest = selected_model_descriptor(config)
    identity = {'model_version': manifest['model_version'], 'model_mode': mode,
            'adapter_name': 'existing_' + manifest['model_version'] if mode == 'lora' else None,
            'adapter_sha256': manifest['artifact_checksums']['adapter_model.safetensors'] if mode == 'lora' else None,
            'base_revision': manifest['base_revision'], 'base_config_sha256': manifest['base_config_sha256'],
            'model_manifest_sha256': file_digest(Path(config['adapter_path']) / 'healthmon-model.json') if mode == 'lora' else None}
    if mode == 'base_only':
        identity['base_shard_proof_sha256'] = config['expected_base_shard_audit_sha256']
    return identity


def assert_ready(health, expected, require_refinement=True):
    model = health.get('model', {})
    activation = model.get('adapter_activation', {})
    mode = expected.get('model_mode', 'lora')
    adapter_name = 'existing_' + expected['model_version'] if mode == 'lora' else None
    if mode == 'base_only':
        activation_valid = (activation.get('verified_base_only') is True and
            activation.get('verified_expected_adapter_active') is False and activation.get('verified_existing_v1_active') is False and
            activation.get('peft_wrapper_present') is False and activation.get('peft_config_empty') is True and
            activation.get('hf_peft_config_loaded') is False and activation.get('adapter_layer_count') == 0 and
            model.get('adapter_name') is None and model.get('adapter_sha256') is None)
    else:
        activation_valid = (activation.get('verified_expected_adapter_active') is True and
            activation.get('selected_adapter_name') == adapter_name and activation.get('active_adapter_names') == [adapter_name] and
            activation.get('all_layers_select_expected_adapter') is True and
            (expected['model_version'] == 'v1' or not activation.get('verified_existing_v1_active')))
    if not (health.get('ready') is True and health.get('provenance') == 'real'
            and health.get('local_acceptance_only') is True and (not require_refinement or health.get('quality_refinement_enabled') is True)
            and all(model.get(key) == value for key, value in expected.items())
            and model.get('dtype') == 'bfloat16' and model.get('downloaded') is False
            and activation_valid):
        raise ValueError('Require ready exact selected real BF16 model/adapter identity and verified activation')


def inspect_response(case, request, response, runtime):
    response.raise_for_status()
    envelope = Envelope.model_validate(response.json())
    if envelope.contract_version != 'healthmon.ai.v1' or envelope.request_id != request['request_id'] or envelope.provenance != 'real':
        raise ValueError('Real response identity/contract mismatch')
    selected = Speech.model_validate(envelope.result)
    validate_contract(selected, case['input'])
    cache_path = runtime / 'responses' / (digest({'capability': 'chat', 'request_id': request['request_id'],
                                                 'pet_id': request['pet_id']}) + '.json')
    cache = json.loads(cache_path.read_text(encoding='utf-8'))
    if cache['fingerprint'] != digest(request) or cache['envelope'] != envelope.model_dump(mode='json'):
        raise ValueError('Frozen request or cached selected response mismatch')
    metrics = cache['metrics']
    candidates = cache.get('candidates', [])
    if not candidates or candidates[0].get('phase') != 'original':
        raise ValueError('Original model candidate evidence is required')
    if digest(candidates[0]['result']) != metrics['quality_refinement']['original_candidate_sha256']:
        raise ValueError('Original candidate hash mismatch')
    if any(digest(candidate['result']) != candidate['candidate_sha256'] for candidate in candidates):
        raise ValueError('Candidate audit hash mismatch')
    if digest(selected.model_dump(mode='json')) not in {candidate['candidate_sha256'] for candidate in candidates if candidate['contract_valid']}:
        raise ValueError('Selected response is not a validated generated candidate')
    attempts = metrics['attempts']
    proven = bool(attempts) and all(a.get('generated_tokens', 0) > 0 and a.get('generation_seconds', 0) > 0
        and a.get('peak_allocated_bytes', 0) > 0 and a.get('raw_sha256') and not a.get('test_double') for a in attempts)
    if metrics.get('fallback') is not False or not proven:
        raise ValueError('Actual GPU generation evidence without fallback is required')
    quality_limit = metrics.get('candidate_policy', {}).get('max_quality_candidates', 1)
    if quality_limit not in (1, 2) or sum(a.get('phase') == 'quality_refinement' for a in attempts) > quality_limit or len(attempts) > 3:
        raise ValueError('Bounded model generation budget exceeded')
    seeds = [attempt.get('seed') for attempt in attempts]
    if all(seed is not None for seed in seeds) and len(set(seeds)) != len(seeds):
        raise ValueError('Each bounded generation must have a distinct reproducible seed')
    return {'selected_response': selected.model_dump(mode='json'), 'model_candidates': candidates,
            'metrics': metrics, 'cache_path': str(cache_path.resolve()), 'actual_gpu_execution_proven': proven,
            'model': cache['model'], 'response_sha256': digest(selected.model_dump(mode='json')),
            'automatic_quality': metrics['quality'], 'manual_semantic_status': 'pending'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--native-config', type=Path, required=True)
    parser.add_argument('--prior-native-review', type=Path)
    parser.add_argument('--prior-neutral-report', type=Path)
    parser.add_argument('--axis', choices=AXES, action='append',
                        help='Restrict to an authorized axis comparison; default prepares all twelve cases')
    parser.add_argument('--execute-real-after-gpu-release', action='store_true',
                        help='Use only after explicit GPU release/start authorization; default is offline preparation')
    args = parser.parse_args()
    runtime = args.config.resolve().parent
    if not runtime.is_relative_to(ROOT / '.runtime'):
        raise ValueError('Use a private test config under this checkout .runtime')
    config = json.loads(args.config.read_text(encoding='utf-8'))
    if config.get('environment') != 'test':
        raise ValueError('Only an isolated test config is permitted')
    native = json.loads(args.native_config.read_text(encoding='utf-8'))
    cases = build_cases(native)
    if args.axis:
        cases = [case for case in cases if case['axis'] in args.axis]
    output_dir = runtime / ('refinement-review-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:12])
    output_dir.mkdir(exist_ok=False)
    output = output_dir / 'report.json'
    report = {'status': 'prepared', 'fixture_inputs': True, 'model_policy': 'explicit selected existing local Qwen3.5-9B BF16 mode; no fallback',
              'expected_identity': expected_identity(config), 'case_plan': cases, 'cases': [], 'failures': [],
              'pair_reviews': [pair for pair in pair_review_plan(cases) if pair['case_ids']], 'semantic_quality_passed': None,
              'automatic_flags_do_not_prove_semantics': True, 'previous_reports_overwritten': False,
              'execution_requested': args.execute_real_after_gpu_release,
              'native_config_path': str(args.native_config.resolve())}
    for key, path in (('previous_native_review', args.prior_native_review), ('previous_neutral_report', args.prior_neutral_report)):
        if path:
            previous = json.loads(path.read_text(encoding='utf-8'))
            report[key] = {'path': str(path.resolve()), 'content': previous, 'sha256': digest(previous)}
    atomic_json(output, report)
    if not args.execute_real_after_gpu_release:
        print(json.dumps({'report': str(output.resolve()), 'status': 'prepared', 'planned_cases': len(cases),
                          'http_requests': 0, 'model_loaded': False, 'gpu_accessed': False}))
        return

    headers = {'Authorization': 'Bearer ' + config['server_token']}
    report['status'] = 'running'
    with httpx.Client(timeout=240, trust_env=False, headers=headers, follow_redirects=False) as client:
        health = client.get(ORIGIN + '/health').json()
        assert_ready(health, report['expected_identity'])
        if config.get('compact_voice', False) is True and health.get('compact_voice_enabled') is not True:
            raise ValueError('The authorized compact voice runtime must be explicitly enabled')
        if config.get('full_personality_facts', False) is True and health.get('full_personality_facts_enabled') is not True:
            raise ValueError('The authorized full personality facts runtime must be explicitly enabled')
        if config.get('structured_dialogue', False) is True and health.get('structured_dialogue_enabled') is not True:
            raise ValueError('The authorized structured dialogue runtime must be explicitly enabled')
        report['model'] = health['model']
        for case in cases:
            request_id = 'refinement-' + case['case_id'] + '-' + uuid.uuid4().hex[:12]
            request = {'contract_version': 'healthmon.ai.v1', 'request_id': request_id,
                       'pet_id': 'pseudonymous-refinement-' + case['case_id'], 'input': case['input']}
            started = time.monotonic()
            try:
                response = client.post(ORIGIN + '/v1/chat', json=request)
                record = inspect_response(case, request, response, runtime)
                if any(record['model'].get(key) != value for key, value in report['expected_identity'].items()):
                    raise ValueError('A different model/adapter produced the candidate')
                report['cases'].append(dict(record, case_id=case['case_id'], suite=case['suite'], axis=case['axis'],
                                            side=case['side'], value=case['value'], request_id=request_id,
                                            authority=case['input']['context']['personality'],
                                            seconds=round(time.monotonic() - started, 3)))
            except (httpx.HTTPError, ValueError, KeyError, OSError) as exc:
                failure = {'case_id': case['case_id'], 'request_id': request_id,
                           'error_type': type(exc).__name__,
                           'status': getattr(getattr(exc, 'response', None), 'status_code', None)}
                if type(exc) is ValueError:
                    failure['code'] = str(exc)
                error_file = runtime / 'last-error.json'
                if error_file.is_file():
                    diagnostic = json.loads(error_file.read_text(encoding='utf-8'))
                    if diagnostic.get('request_id') == request_id:
                        failure['model_failure_evidence'] = diagnostic
                report['failures'].append(failure)
            atomic_json(output, report)
    report['status'] = 'contract_passed_semantic_review_pending' if not report['failures'] and len(report['cases']) == len(cases) else 'contract_failed'
    report['all_contracts_passed'] = not report['failures'] and len(report['cases']) == len(cases)
    report['all_automatic_quality_checks_passed'] = report['all_contracts_passed'] and all(c['automatic_quality']['passed'] for c in report['cases'])
    annotate_pair_contrasts(report)
    atomic_json(output, report)
    print(json.dumps({'report': str(output.resolve()), 'status': report['status'], 'cases': len(report['cases']),
                      'failures': len(report['failures']), 'automatic_quality_passed': report['all_automatic_quality_checks_passed'],
                      'semantic_quality_passed': None}))


if __name__ == '__main__':
    main()
