import hashlib
import json
import os
from pathlib import Path
import sys
import uuid
from datetime import datetime, timezone
import psycopg
from psycopg import sql
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'Server'))
from Server.healthmon.config import Settings
from Server.healthmon.db import Database
from Server.healthmon.app import create_app


@pytest.fixture(scope='session')
def admin_dsn():
    value = os.getenv('TEST_ADMIN_DSN')
    if not value:
        path = ROOT / '.runtime/test-connection.json'
        if path.exists():
            value = json.loads(path.read_text())['admin_dsn']
    if not value:
        pytest.skip('Explicit isolated PostgreSQL TEST_ADMIN_DSN is required')
    return value


@pytest.fixture
def settings(admin_dsn):
    name = 'healthmon_test_' + uuid.uuid4().hex
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    info = conninfo_to_dict(admin_dsn)
    info['dbname'] = name
    config = Settings(database_url=make_conninfo(**info), environment='test', ai_mode='disabled',
                      token_hashes={hashlib.sha256(b'test-owner-a-token').hexdigest(): 'owner-a', hashlib.sha256(b'test-owner-b-token').hexdigest(): 'owner-b'},
                      test_owners=frozenset({'owner-a', 'owner-b'}), worker_enabled=False)
    yield config
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


@pytest.fixture
def db(settings):
    database = Database(settings)
    database.migrate()
    return database


@pytest.fixture
def client(settings, db):
    application = create_app(settings, db)
    application.state.clock = lambda: datetime(2026, 10, 22, 3, 0, tzinfo=timezone.utc)
    with TestClient(application) as result:
        result.headers['Authorization'] = 'Bearer test-owner-a-token'
        yield result


@pytest.fixture
def pet(client):
    response = client.post('/pets', json={'name': '테스트펫'})
    assert response.status_code == 200, response.text
    return response.json()['pet_id']
