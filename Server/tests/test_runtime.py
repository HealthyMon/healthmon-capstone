"""CPU import boundary and actual PostgreSQL migration/readiness guarantees."""
from dataclasses import replace
from pathlib import Path
import subprocess
import sys

import psycopg
import pytest

from Server.healthmon import db as db_module
from Server.healthmon.db import Database


def test_common_app_constructs_with_ml_packages_actively_blocked():
    code = r'''
import importlib.abc
import sys
blocked = {'torch','torchvision','transformers','diffusers','cv2','mmdet','mmcv','bpy','model_runtime','vision_service','embedding'}
class RejectModels(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in blocked:
            raise RuntimeError('Common server imported forbidden model dependency: ' + fullname)
sys.meta_path.insert(0, RejectModels())
from Server.healthmon.config import Settings
from Server.healthmon.app import create_app
app = create_app(Settings(database_url='postgresql://unused-test-host/explicit-test-db', worker_enabled=False))
assert app.title == 'HEALTHMON common server'
assert not any(name.split('.')[0] in blocked for name in sys.modules)
print('CPU_ONLY_IMPORT_BOUNDARY_PASS')
'''
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, '-I', '-c', "import sys; sys.path.insert(0," + repr(str(root)) + ");" + code],
                            cwd=root, capture_output=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stderr
    assert 'CPU_ONLY_IMPORT_BOUNDARY_PASS' in result.stdout


def test_database_restart_and_repeated_migration_preserve_identity_and_pet(db, settings, client, pet):
    before = db.ready()
    restarted = Database(settings)
    restarted.migrate()
    restarted.migrate()
    assert restarted.ready() == before
    with restarted.connect() as c:
        assert c.execute('SELECT owner_id FROM pets WHERE id=%s', (pet,)).fetchone()['owner_id'] == 'owner-a'
        versions = c.execute('SELECT version,count(*) AS n FROM schema_migrations GROUP BY version').fetchall()
        assert all(row['n'] == 1 for row in versions)
        assert {row['version'] for row in versions} == {version for version, _ in db_module.MIGRATIONS}
    assert client.get('/health/ready').status_code == 200


def test_failed_migration_is_atomic_preserves_existing_records_and_cannot_report_ready(db, client, pet, tmp_path, monkeypatch):
    original = db_module.MIGRATIONS
    bad = tmp_path / '999_intentional_failure.sql'
    bad.write_text('CREATE TABLE should_rollback(id int); SELECT * FROM intentional_missing_relation;', encoding='utf-8')
    monkeypatch.setattr(db_module, 'MIGRATIONS', [*original, ('999', bad)])
    with pytest.raises(psycopg.Error):
        db.migrate()
    assert client.get('/health/ready').status_code == 503
    with db.connect() as c:
        assert c.execute("SELECT to_regclass('should_rollback') AS item").fetchone()['item'] is None
        assert not c.execute("SELECT 1 FROM schema_migrations WHERE version='999'").fetchone()
        assert c.execute('SELECT id FROM pets WHERE id=%s', (pet,)).fetchone()['id'] == pet
    monkeypatch.setattr(db_module, 'MIGRATIONS', original)
    assert client.get('/health/ready').status_code == 200


def test_metadata_rejects_cross_environment_and_wrong_restored_server_id(db, settings):
    with pytest.raises(RuntimeError, match='environment'):
        Database(replace(settings, environment='development')).ready()
    with pytest.raises(RuntimeError, match='SERVER_INSTANCE_ID'):
        Database(replace(settings, instance_id='different-restored-instance')).ready()
    assert db.ready()['environment'] == 'test'


def test_default_container_path_uses_dedicated_cpu_requirements():
    # Build execution is a separate Docker check. This guards which implementation is
    # packaged: the legacy standalone vision Dockerfile must never become the default.
    root = Path(__file__).resolve().parents[2]
    compose = (root / 'compose.yaml').read_text(encoding='utf-8')
    docker = (root / 'Server/Dockerfile.common').read_text(encoding='utf-8')
    requirements = (root / 'Server/requirements.txt').read_text(encoding='utf-8').lower()
    assert 'dockerfile: Server/Dockerfile.common' in compose
    assert 'Server.healthmon.app:create_app' in docker and '--factory' in docker
    assert 'COPY Ai/LLM/migrations' in docker and 'COPY Ai/LLM/src' not in docker
    for forbidden in ('torch', 'transformers', 'diffusers', 'cuda', 'blender', 'mmdet', 'mmcv'):
        assert forbidden not in requirements


@pytest.mark.parametrize('exercise,unit,wrong_part', [
    ('walking', 'steps', 'upper'), ('running', 'minutes', 'full'),
    ('pushup', 'repetitions', 'lower'),
])
def test_known_goal_cannot_change_canonical_scored_body_part(client, pet, exercise, unit, wrong_part):
    response = client.post(f'/pets/{pet}/goals', json={
        'exercise_type': exercise, 'target': 100, 'unit': unit, 'body_part': wrong_part})
    assert response.status_code == 422


@pytest.mark.parametrize('mode,expected_ready', [('disabled', False), ('mock', True)])
def test_conversation_session_exposes_ready_field_used_by_unity(client, pet, settings, mode, expected_ready):
    settings.ai_mode = mode
    session = {'session_id': 'unity-session-readiness-test', 'active': True}
    response = client.post(f'/pets/{pet}/chat-session', json=session)
    assert response.status_code == 200
    assert response.json().get('ready') is expected_ready
    heartbeat = client.post(f'/pets/{pet}/chat-session/heartbeat', json=session)
    assert heartbeat.status_code == 200
    assert heartbeat.json().get('ready') is expected_ready
