"""Explicit pseudonymous low/high personality acceptance against a real probe."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import uuid

import httpx

from Server.healthmon.gateway import Speech, EmbeddingResult
from Server.healthmon.rules import initial_state
from Server.local_probe.gpu_gateway import atomic_json, digest, style_context
from Server.local_probe.run_refinement_review import assert_ready, expected_identity


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--only', choices=('activity', 'affinity', 'initiative'))
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    output = args.config.parent / ('comparison-' + uuid.uuid4().hex + '.json')
    expected = expected_identity(config)
    report = {'provenance': 'real', 'fixture_inputs': True, 'gpu_inference': True, 'downloaded': False,
              'model_version': expected['model_version'], 'expected_identity': expected, 'cases': [], 'failures': []}
    headers = {'Authorization': 'Bearer ' + config['server_token']}
    axes = (args.only,) if args.only else ('activity', 'affinity', 'initiative')
    with httpx.Client(timeout=180, trust_env=False, headers=headers) as client:
        health = client.get('http://127.0.0.1:18091/health').json()
        assert_ready(health, expected, require_refinement=False)
        report['model'] = health['model']
        for axis in axes:
            for value in (10, 90):
                state = dict(initial_state(), **{axis: value})
                context = {'state': state, 'personality': {key: state[key] for key in ('activity', 'affinity', 'initiative')},
                           'settings': {'name': '테스트몽글', 'speech_level': 'casual', 'profanity': 'none'},
                           'memories': [], 'recent': []}
                request_id = 'real-probe-' + axis + '-' + str(value) + '-' + uuid.uuid4().hex[:12]
                request = {'contract_version': 'healthmon.ai.v1', 'request_id': request_id, 'pet_id': 'pseudonymous-probe-pet',
                           'input': {'text': '오늘은 그냥 나랑 이야기하고 싶어. 너다운 말투로 한두 마디 해 줘.', 'context': context}}
                started = time.monotonic()
                response = client.post('http://127.0.0.1:18091/v1/chat', json=request)
                if response.status_code != 200:
                    report['failures'].append({'axis': axis, 'value': value, 'status': response.status_code, 'error': response.json()})
                    atomic_json(output, report)
                    continue
                envelope = response.json()
                result = Speech.model_validate(envelope['result']).model_dump(mode='json')
                assert envelope['provenance'] == 'real' and envelope['request_id'] == request_id
                cache = args.config.parent / 'responses' / (digest({'capability': 'chat', 'request_id': request_id,
                         'pet_id': request['pet_id']}) + '.json')
                metrics = json.loads(cache.read_text(encoding='utf-8'))['metrics']
                report['cases'].append({'axis': axis, 'value': value, 'style': style_context(context),
                                        'seconds': round(time.monotonic() - started, 3), 'result': result,
                                        'request_id': request_id, 'quality': metrics['quality'],
                                        'quality_refinement': metrics.get('quality_refinement'),
                                        'generation_attempts': len(metrics['attempts']), 'fallback': False})
                atomic_json(output, report)
        embedding_id = 'real-embedding-' + uuid.uuid4().hex
        response = client.post('http://127.0.0.1:18091/v1/embedding', json={
            'contract_version': 'healthmon.ai.v1', 'request_id': embedding_id, 'pet_id': 'pseudonymous-probe-pet',
            'input': {'text': '가명 테스트 사용자의 공용 서버 상태 확인'}})
        if response.status_code == 200:
            embedded = EmbeddingResult.model_validate(response.json()['result'])
            report['embedding'] = {'passed': embedded.dimension == len(embedded.vector) == 1024,
                                   'model_id': embedded.model_id, 'model_version': embedded.model_version,
                                   'dimension': embedded.dimension, 'device': 'cpu', 'provenance': response.json()['provenance']}
        else:
            report['failures'].append({'capability': 'embedding', 'status': response.status_code})
        report['all_contracts_passed'] = not report['failures'] and len(report['cases']) == 2 * len(axes) and report.get('embedding', {}).get('passed', False)
        report['style_adapter'] = 'authoritative-three-axis-system-guidance.v2-fewshot'
        report['all_automatic_quality_checks_passed'] = (len(report['cases']) == 2 * len(axes)
            and all(case['quality']['passed'] for case in report['cases']))
        report['identical_pair_speeches'] = [axis for axis in axes if len([case for case in report['cases'] if case['axis'] == axis]) == 2
                                           and len({case['result']['speech'] for case in report['cases'] if case['axis'] == axis}) == 1]
        report['semantic_review_required'] = True
        atomic_json(output, report)
    # Never print credentials, input text or raw/selected model speech to stdout.
    print(json.dumps({'report': str(output.resolve()), 'all_contracts_passed': report['all_contracts_passed'],
                      'all_automatic_quality_checks_passed': report['all_automatic_quality_checks_passed'],
                      'successful_cases': len(report['cases']), 'failed_cases': len(report['failures']),
                      'identical_pair_axes': report['identical_pair_speeches']}))


if __name__ == '__main__':
    main()
