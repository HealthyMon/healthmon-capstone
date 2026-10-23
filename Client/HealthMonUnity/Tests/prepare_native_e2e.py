"""Prepare a new isolated PostgreSQL fixture for the native Unity verifier.

This helper never starts an API, AI worker, or Unity process. Historical score
offsets and EXP below are synthetic *game setup*, not measured health records.
An existing AI key must be supplied; only this fixture's user token is generated.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from Server.healthmon import rules, service
from Server.healthmon.config import Settings
from Server.healthmon.contracts import PetSettings
from Server.healthmon.db import Database

SYNTHETIC_REASON = 'synthetic isolated Unity fixture game setup; not an exercise or measured health record'
PROMPT = ('지금 내 헬스몬의 활동성, 친밀도, 주도성을 참고해서, 오늘 달리기를 할지 고민하는 나에게 '
          '헬스몬답게 두 문장으로 말해 줘. 새로운 운동 완료 기록이나 보상은 만들지 마.')
AXES = ('upper_body', 'lower_body', 'nutrition', 'energy_balance', 'activity', 'affinity', 'initiative')


def fixture_cases() -> list[dict]:
    def case(ident, level=10, run_chat=False, appearance='ordinary', **scores):
        targets = {axis: 0 if axis == 'energy_balance' else 50 for axis in AXES}
        targets.update(scores)
        return dict(case_id=ident, level=level, targets=targets, run_chat=run_chat, appearance=appearance)

    cases = [case('initial-running-smoke', 1, True)]
    cases[0]['run_workout_smoke'] = True
    cases += [case(f'level-{level}', level) for level in (9, 10, 19, 20, 29, 30)]
    cases += [
        case('body-balanced', 10, appearance='balanced_athletic', upper_body=80, lower_body=80, nutrition=80),
        case('body-upper', 20, appearance='upper_developed', upper_body=90, lower_body=60, nutrition=70),
        case('body-lower', 20, appearance='lower_developed', upper_body=60, lower_body=90, nutrition=70),
        case('body-lean', 30, appearance='lean_athletic', upper_body=75, lower_body=75, nutrition=70, energy_balance=-40),
        case('body-adipose', 10, appearance='adipose', upper_body=30, lower_body=30, nutrition=30, energy_balance=40),
        case('nutrition-low', 10, appearance='developed_general', upper_body=75, lower_body=75, nutrition=20),
        case('nutrition-high', 10, appearance='balanced_athletic', upper_body=75, lower_body=75, nutrition=80),
    ]
    for axis in ('activity', 'affinity', 'initiative'):
        for label, score in (('low', 20), ('high', 80)):
            cases.append(case(f'{axis}-{label}', 10, True, **{axis: score}))
    assert len(cases) == 20 and sum(c['run_chat'] for c in cases) == 7
    return cases


def bounded_parts(amount: int, low: int, high: int) -> list[int]:
    parts = []
    while amount:
        delta = min(high, max(low, amount))
        parts.append(delta)
        amount -= delta
    return parts


def retained_offsets(targets: dict, now: datetime) -> dict:
    """Build only past completed-period offsets, respecting ordinary period caps.

    EB is solved backwards across Monday's two-point convergence. No offset is
    placed on today's date, so the native running smoke has its full daily cap.
    """
    today = now.astimezone(rules.KST).date()
    daily: dict[str, dict] = {}
    weekly: dict[str, dict] = {}
    for axis, low in (('upper_body', -2), ('lower_body', -2), ('nutrition', -3)):
        parts = bounded_parts(targets[axis] - 50, low, 3)
        for index, delta in enumerate(parts):
            day = today - timedelta(days=len(parts) - index)
            daily.setdefault(day.isoformat(), {})[axis] = delta

    # needed denotes the state after this day's processing. First reverse today,
    # on which the fixture deliberately has no synthetic daily contribution.
    day, needed = today, targets['energy_balance']
    for _ in range(180):
        delta = 0 if day == today else min(4, max(-4, needed))
        if delta:
            daily.setdefault(day.isoformat(), {})['energy_balance'] = delta
        before_daily = needed - delta
        if day.weekday() == 0 and before_daily:
            before_daily += 2 if before_daily > 0 else -2
        needed = before_daily
        if not needed:
            break
        day -= timedelta(days=1)
    else:
        raise AssertionError('Energy fixture did not converge')

    monday = today - timedelta(days=today.weekday())
    for axis in ('activity', 'affinity', 'initiative'):
        parts = bounded_parts(targets[axis] - 50, -3 if axis == 'initiative' else -2, 3)
        for index, delta in enumerate(parts):
            start = monday - timedelta(weeks=len(parts) - index)
            weekly.setdefault(start.isoformat(), {})[axis] = delta
    result = {'daily': daily, 'weekly': weekly}
    replayed = rules.replay([], now, retained=result)['state']
    assert all(replayed[axis] == targets[axis] for axis in AXES), 'Synthetic offset construction differs from replay'
    assert today.isoformat() not in daily
    return result


def private_json(path: Path, payload: dict):
    # Exclusive creation prevents replacing another fixture or a live API config.
    with path.open('x', encoding='utf-8') as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    if os.name != 'nt':
        path.chmod(0o600)


def prepare(args) -> dict:
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    from psycopg.types.json import Jsonb

    if args.ai_key_config:
        ai_token = json.loads(args.ai_key_config.read_text(encoding='utf-8'))[args.ai_key_field]
    else:
        ai_token = os.environ.get(args.ai_key_env, '')
    if not isinstance(ai_token, str) or not ai_token.strip() or '\n' in ai_token or '\r' in ai_token:
        raise ValueError('An existing, nonempty AI key is required before creating a fixture database')
    runtime = ROOT / '.runtime'
    runtime.mkdir(exist_ok=True)
    manifest_path, env_path = runtime / 'unity-native-e2e.json', runtime / 'unity-native-api-env.json'
    if manifest_path.exists() or env_path.exists():
        raise FileExistsError('Native fixture output already exists; preserve it and choose a deliberate new run')
    admin_dsn = json.loads(args.admin_config.read_text(encoding='utf-8'))['admin_dsn']
    info = conninfo_to_dict(admin_dsn)
    if info.get('host') not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('This native fixture helper accepts only an explicitly local PostgreSQL admin connection')
    stamp = uuid.uuid4().hex
    db_name, owner, user_token, instance = 'healthmon_test_unity_' + stamp, 'unity-native-' + stamp, secrets.token_urlsafe(40), str(uuid.uuid4())
    info['dbname'] = db_name
    settings = Settings(database_url=make_conninfo(**info), environment='test', ai_mode='remote',
                        ai_base_url='http://127.0.0.1:18091', ai_token=ai_token, ai_timeout=180,
                        token_hashes={hashlib.sha256(user_token.encode()).hexdigest(): owner},
                        test_owners=frozenset({owner}), instance_id=instance, allow_http_ai=True,
                        worker_enabled=False, public_base_url='http://127.0.0.1:18092')
    now = datetime.now(timezone.utc)
    cases = fixture_cases()
    offsets = {case['case_id']: retained_offsets(case['targets'], now) for case in cases}
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(db_name)))
    db = Database(settings)
    db.migrate()
    db.ready()
    manifest_cases = []
    for item in cases:
        pet = uuid.uuid4().hex
        # Every period here is game-only fixture setup; sources remains empty.
        pet_settings = PetSettings(name='u-e2e-' + item['case_id'][:13]).model_dump()
        with db.connect() as c:
            created = now - timedelta(days=180)
            c.execute('INSERT INTO pets(id,owner_id,settings,created_at) VALUES(%s,%s,%s,%s)',
                      (pet, owner, Jsonb(pet_settings), created))
            service.seed_goals(c, pet, created)
            exp = sum(rules.required_exp(level) for level in range(1, item['level']))
            c.execute('INSERT INTO game_ledger(pet_id,reward_key,exp,coin,reason) VALUES(%s,%s,%s,0,%s)',
                      (pet, 'native-fixture:' + item['case_id'], exp, SYNTHETIC_REASON))
            for period, entries in offsets[item['case_id']].items():
                for day, adjustment in entries.items():
                    c.execute('INSERT INTO game_retained_scores(pet_id,period,period_start,adjustment,rule_version) VALUES(%s,%s,%s,%s,%s)',
                              (pet, period, date.fromisoformat(day), Jsonb(adjustment), rules.RULE_VERSION))
            p = service.owned(c, owner, pet, True)
            state, _ = service.refresh(c, p, now, ai_available=True, reason='synthetic_native_fixture_setup')
            assert state['level'] == item['level']
            assert all(state[axis] == item['targets'][axis] for axis in AXES)
            assert state['evolution_profile']['appearance'] == item['appearance']
        # A separate read/refresh transaction proves the fixture survives replay.
        with db.connect() as c:
            p = service.owned(c, owner, pet, True)
            repeated, _ = service.refresh(c, p, now, ai_available=True)
            assert repeated == state, 'Fixture changed on ordinary service.refresh replay'
            assert c.execute('SELECT count(*) AS n FROM sources WHERE pet_id=%s', (pet,)).fetchone()['n'] == 0
        manifest_cases.append(dict(case_id=item['case_id'], pet_id=pet, prompt=PROMPT if item['run_chat'] else '',
                                   expected_state=state, expected_evolution_profile=state['evolution_profile'],
                                   run_workout_smoke=item.get('run_workout_smoke', False), run_chat=item['run_chat'],
                                   require_model_display=False, expected_lower_body_after_workout=52 if item.get('run_workout_smoke') else 0))

    api_env = {
        'DATABASE_URL': settings.database_url, 'APP_ENV': 'test', 'AI_MODE': 'remote',
        'AI_BASE_URL': settings.ai_base_url, 'AI_SERVER_TOKEN': ai_token, 'AI_TIMEOUT_SECONDS': '180',
        'AI_CONTRACT_VERSION': settings.contract_version, 'ALLOW_HTTP_AI': 'true',
        'DEV_TOKENS': json.dumps({user_token: owner}), 'AUTH_TOKEN_HASHES': '{}',
        'TEST_OWNERS': json.dumps([owner]), 'SERVER_INSTANCE_ID': instance, 'WORKER_ENABLED': 'false',
        'PUBLIC_BASE_URL': settings.public_base_url, 'EMBEDDING_MODEL_ID': settings.embedding_model,
        'EMBEDDING_MODEL_VERSION': settings.embedding_version, 'API_BIND': '127.0.0.1', 'API_PORT': '18092',
    }
    manifest = dict(isolated_fixture=True, api_base_url=settings.public_base_url, bearer_token=user_token,
                    expected_server_instance_id=instance, expected_owner_id=owner, timeout_seconds=240,
                    require_real_llm=True, require_distinct_llm_responses=True, capture_screenshots=True,
                    fixture_created_at_utc=now.isoformat(), fixture_database=db_name,
                    fixture_note=SYNTHETIC_REASON, fixture_ai_chat_case_count=7, cases=manifest_cases)
    private_json(env_path, api_env)
    private_json(manifest_path, manifest)
    return dict(database=db_name, cases=len(manifest_cases), real_llm_cases=7,
                service_refresh_verified_twice=True, synthetic_sources_created=0,
                manifest=str(manifest_path), private_api_env=str(env_path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--admin-config', type=Path, default=ROOT / '.runtime/test-connection.json')
    key = parser.add_mutually_exclusive_group(required=True)
    key.add_argument('--ai-key-config', type=Path, help='Existing private JSON containing an AI key; no key is generated')
    key.add_argument('--ai-key-env', help='Name of an environment variable holding an existing AI key')
    parser.add_argument('--ai-key-field', default='server_token')
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args), ensure_ascii=False))
    except Exception as error:
        # Database/lib exception strings can contain private connection details.
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__}), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
