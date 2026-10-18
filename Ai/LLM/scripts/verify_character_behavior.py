"""Finite CPU-only behavioral audit; never starts Qwen or writes existing databases.

This checks integration contracts and backend behavior, not generated speech quality.
Recorded gaps are observations, not passing implementations of those features.
"""
import argparse
import gc
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from src.agent import respond, validate
from src.character_lab_engine import execute, fresh
from src.character_lab_models import response_context
from src.character_lab_presets import PRESETS, preview
from src.contracts import ModelOutput
from src.persona_lab import create_app
from src.persona_runtime import PersonaRuntime, persona_messages
from src.persona_store import LabStore


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Choose a new audit output path')
    checks, observations = [], []

    def check(name, condition, **detail):
        checks.append({'name': name, 'passed': bool(condition), **detail})

    def event(kind, ident, **payload):
        return {'kind': kind, 'event_id': ident, 'payload': payload}

    def checksum(path):
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None

    protected = ROOT / 'runs/persona-lab/test-characters.sqlite3'
    before_hash = checksum(protected)
    for name in PRESETS:
        result = preview(name)
        check('preset:'+name, result['dry_run'] and result['training_data'] is False
              and all(command['event_id'] in result['session']['processed'] for command in result['commands']),
              before=result['before'], after=result['after'], event_count=len(result['results']))

    for days in (1, 7, 30, 366):
        lab = fresh({'initiative': 85})
        result = execute(lab, [event('time', 'time-'+str(days), days=days)])
        daily = [q for q in result['session']['quests'].values() if q.get('quest_scope') == 'daily']
        check('time_creates_daily_quest:'+str(days), len(daily) == days+1
              and sum(q['status'] == 'created' for q in daily) == 1,
              virtual_date=result['after']['virtual_test_date'], quest_count=len(result['session']['quests']))
    observations.append({'kind': 'remaining_integration', 'feature': 'wall_clock_trigger',
                         'detail': 'Virtual time creates daily quests. A production wall-clock trigger and Unity delivery remain separate.'})

    lab = execute(fresh(), [event('quest', 'create-expiry', quest_id='expiry', due_date='2026-10-04'),
                           event('quest', 'accept-expiry', quest_id='expiry', action='accept')])['session']
    expired = execute(lab, [event('time', 'past-due', days=7)])['session']
    check('accepted_overdue_quest_fails', expired['quests']['expiry']['status'] == 'failed')
    observations.append({'kind': 'implemented', 'feature': 'expiry_processing',
                         'status_after_7_days': expired['quests']['expiry']['status'],
                         'detail': 'Overdue accepted quests fail, unaccepted quests expire, and rewards are not paid.'})

    matrices = []
    text = '오늘 할 수 있는 작은 목표를 추천해 줘'
    baseline = fresh()
    for axis in ('activity', 'affection', 'initiative'):
        for value in (25, 39, 40, 50, 53, 69, 70, 85, 100):
            state = dict(baseline['state'], **{axis: value})
            ctx = response_context(baseline, state, text, [], 'casual')
            row = {'axis': axis, 'value': value, 'agent_policy': ctx['agent_policy'],
                   'candidates': [q['id'] for q in ctx['candidates']],
                   'style': {k: ctx['style_profile'][k] for k in ('stages', 'warmth', 'initiative',
                             'encouragement_strength', 'sentence_budget', 'question_budget', 'guidance')},
                   'prompt_sha256': hashlib.sha256(json.dumps(persona_messages(ctx, text),
                                                  ensure_ascii=False).encode()).hexdigest()}
            matrices.append(row)
            check(f'axis_reaches_response_context:{axis}:{value}',
                  ctx['traits'][axis] == value and ctx['character_state'][axis] == value,
                  agent_band=ctx['agent_policy']['initiative_band'])
    by_axis = {axis: {r['value']: r for r in matrices if r['axis'] == axis}
               for axis in ('activity', 'affection', 'initiative')}
    check('affinity_changes_warmth', by_axis['affection'][25]['style']['warmth']
          < by_axis['affection'][85]['style']['warmth'])
    check('activity_changes_encouragement', by_axis['activity'][25]['style']['encouragement_strength']
          < by_axis['activity'][85]['style']['encouragement_strength'])
    check('initiative_low_suppresses_candidates', not by_axis['initiative'][39]['candidates'])
    check('initiative_40_medium', by_axis['initiative'][40]['agent_policy']['initiative_band'] == 'medium')
    check('initiative_70_high', by_axis['initiative'][70]['agent_policy']['initiative_band'] == 'high')
    for axis in by_axis:
        check('small_change_reaches_prompt:'+axis, by_axis[axis][50]['prompt_sha256']
              != by_axis[axis][53]['prompt_sha256'])
        observations.append({'kind': 'quality_limit', 'feature': 'small_personality_change:'+axis,
                             'same_agent_band': by_axis[axis][50]['agent_policy']['initiative_band']
                                                == by_axis[axis][53]['agent_policy']['initiative_band'],
                             'same_trait_stages': by_axis[axis][50]['style']['stages']
                                                  == by_axis[axis][53]['style']['stages'],
                             'detail': 'A changed prompt is not proof that generated dialogue is perceptibly different.'})

    for name, axis, expected in [('exercise_7', 'activity', 53), ('positive_chat', 'affection', 53),
                                 ('reject_proposals', 'initiative', 48)]:
        lab = preview(name)['session']
        ctx = response_context(lab, lab['state'], text, [], 'casual')
        check('earned_change_reaches_responder:'+name, ctx['character_state'][axis] == expected,
              axis=axis, before=50, after=ctx['character_state'][axis],
              agent_band=ctx['agent_policy']['initiative_band'])
    for initiative in (25, 50, 85):
        lab = fresh({'initiative': initiative})
        ctx = response_context(lab, lab['state'], '오늘은 운동 안 할래. 쉬고 싶어.', [], 'casual')
        exercise = [q for q in ctx['candidates'] if q['category'] != 'food']
        check('refusal_respected_in_candidates:'+str(initiative), not exercise,
              candidate_ids=[q['id'] for q in ctx['candidates']])

    ctx = response_context(baseline, baseline['state'], text, [], 'casual')
    valid = {'speech': '오늘은 부담 없이 작은 목표부터 골라 보자.', 'emotion': 'encouraging',
             'animation': 'encourage', 'action': {'type': 'none', 'target_id': None},
             'memory_ids': [], 'personality_update': None}
    check('valid_unity_display_fields', validate(json.dumps(valid, ensure_ascii=False), ctx, text)
          .model_dump() == valid)
    invalid = [
        ('missing_speech', {k: v for k, v in valid.items() if k != 'speech'}),
        ('unknown_animation', dict(valid, animation='dance')),
        ('null_quest_target', dict(valid, action={'type': 'offer_quest', 'target_id': None})),
        ('unauthorized_quest_target', dict(valid, action={'type': 'offer_quest', 'target_id': 'invented'})),
        ('unknown_memory', dict(valid, memory_ids=['invented-memory'])),
        ('model_claims_reward', dict(valid, speech='보상을 지급했어.')),
    ]
    for name, output in invalid:
        try:
            validate(json.dumps(output, ensure_ascii=False), ctx, text)
        except ValueError as error:
            check('reject_invalid_output:'+name, True, error_category=type(error).__name__)
        else:
            check('reject_invalid_output:'+name, False)

    class InvalidGenerator:
        def generate(self, context, user_text, repair=None):
            return json.dumps(dict(valid, action={'type': 'offer_quest', 'target_id': None}), ensure_ascii=False)

    output, metrics = respond(InvalidGenerator(), ctx, text)
    check('invalid_output_falls_back_to_safe_contract', metrics['fallback']
          and output.action.type == 'none' and output.action.target_id is None,
          controlled_fixture=True, attempts=metrics['attempts'], response=output.model_dump())

    os.environ.update(APP_ENV='development', PERSONA_LAB_ENABLED='1')
    os.environ.pop('ENVIRONMENT', None)
    os.environ.pop('NODE_ENV', None)
    runtime = PersonaRuntime()

    def forbidden(*args, **kwargs):
        raise AssertionError('Audit must not load Qwen or connect to PostgreSQL')

    runtime._load = forbidden
    import src.db
    src.db.connect = forbidden
    origin = 'http://127.0.0.1:8001'
    headers = {'Origin': origin, 'X-Persona-Lab': '1'}
    with tempfile.TemporaryDirectory(prefix='character-behavior-') as folder:
        path = Path(folder) / 'isolated.sqlite3'
        app = create_app(runtime, LabStore(path))
        with TestClient(app, base_url=origin, client=('127.0.0.1', 30000)) as client:
            def post(endpoint, body):
                return client.post('/dev/character-lab'+endpoint, json=body, headers=headers)

            response = post('/conversation/respond', {'text': text, 'session': baseline, 'mode': 'dummy'})
            check('response_http_200', response.status_code == 200)
            body = response.json()
            for side in ('a', 'b'):
                out = body['results'][0][side]
                ModelOutput.model_validate(out['output'])
                check('dummy_response_contract:'+side, out['output_origin'] == 'dummy'
                      and not out['is_real_model'], response=out['output'])
            check('response_does_not_write_db', not path.exists() and body['database_write'] is False)
            analysis = post('/conversation/analyze', {'text': '운동하기 싫다', 'mode': 'dummy'}).json()
            check('analysis_kept_separate_from_speech', 'speech' not in analysis['prediction']
                  and analysis['output_origin'] == 'dummy')
            mismatched = dict(baseline['state'], virtual_test_date='2026-10-05')
            bad_cases = [
                ('invalid_goal', '/exercise', {'commands': [event('exercise', 'bad-goal', actual=1, target=0)]}),
                ('future_record', '/exercise', {'session': baseline, 'commands': [event('exercise', 'future',
                                          actual=1, target=1, date='2026-10-05')]}),
                ('mixed_event_endpoint', '/time', {'commands': [event('exercise', 'wrong-endpoint', actual=1, target=1)]}),
                ('date_mismatch', '/conversation/respond', {'text': text, 'session': baseline, 'a': mismatched, 'mode': 'dummy'}),
                ('early_weekly', '/time', {'commands': [event('time', 'early-week', action='weekly')]}),
                ('commit_without_session', '/run', {'dry_run': False, 'commands': []}),
            ]
            for name, endpoint, request in bad_cases:
                result = post(endpoint, request)
                check('http_validation:'+name, result.status_code == 422, status_code=result.status_code)
            state = post('/sessions', {}).json()
            ident = state['session_id']
            commands = [event('exercise', 'idempotent-exercise', actual=50, target=50, category='full')]
            request = {'session_id': ident, 'expected_revision': 0, 'dry_run': False, 'commands': commands}
            saved = post('/run', request)
            check('isolated_test_commit', saved.status_code == 200 and saved.json()['after']['upper_body'] == 51)
            duplicate = post('/run', dict(request, expected_revision=1))
            check('duplicate_event_no_double_growth', duplicate.status_code == 200
                  and duplicate.json()['after']['upper_body'] == 51)
            stale = post('/run', request)
            check('stale_revision_http_409', stale.status_code == 409)
        # sqlite connection context managers commit/rollback but do not close;
        # release their unreachable cycles before Windows temporary-file cleanup.
        gc.collect()

    check('existing_test_database_unchanged', before_hash == checksum(protected),
          before_sha256=before_hash, after_sha256=checksum(protected))
    result = {'started_at': datetime.now(timezone.utc).isoformat(), 'mode': 'cpu_contract_and_rules',
              'actual_qwen_executed': False, 'training_executed': False,
              'checks': checks, 'observations': observations, 'axis_matrix': matrices,
              'summary': {'passed': sum(x['passed'] for x in checks), 'total': len(checks),
                          'failed': [x['name'] for x in checks if not x['passed']]}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result['summary'], ensure_ascii=False))
    raise SystemExit(bool(result['summary']['failed']))


if __name__ == '__main__':
    main()
