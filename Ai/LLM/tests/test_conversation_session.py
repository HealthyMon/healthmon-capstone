"""Real child processes verify reuse, cleanup, deadlines and tab-switch races."""
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import psutil
import pytest
from fastapi.testclient import TestClient
from src import app as api
from src import model_runtime as models

REAL_POPEN = subprocess.Popen
CODE = '''import json,os,sys,time
print(json.dumps({'ready':True}),flush=True)
for line in sys.stdin:
 job=json.loads(line)
 if job.get('hang'):time.sleep(60)
 print(json.dumps({'id':job['id'],'pid':os.getpid(),'response':{'speech':'반가워!','emotion':'happy','animation':'wave','action':{'type':'none','target_id':None},'memory_ids':[],'personality_update':None},'metrics':{}}),flush=True)
'''


@pytest.fixture
def manager(monkeypatch):
    monkeypatch.setattr(models, 'runtime', models.ModelRuntime())
    popen = REAL_POPEN
    def process(*args, **kwargs):
        return popen([sys.executable, '-u', '-c', CODE], **kwargs)
    monkeypatch.setattr(models.subprocess, 'Popen', process)
    instance = models.OnDemandQwen()
    yield instance
    instance.close()


def key(index=0):
    return ('test-owner', 'test-pet', str(index).zfill(32))


def test_tab_keeps_same_process_for_multiple_messages_and_close_frees_it(manager):
    assert manager.open_session(key())['ready']
    first = manager.conversation.run({})
    second = manager.conversation.run({})
    assert first['pid'] == second['pid'] and psutil.pid_exists(first['pid'])
    assert manager.heartbeat(key())['ready']
    assert models.runtime.status()['idle_models_resident']
    manager.close_session(key())
    assert not psutil.pid_exists(first['pid'])
    assert manager.model is None and not manager.heartbeat(key())['active']


def test_foreign_close_cannot_unload_current_conversation(manager):
    manager.open_session(key())
    with pytest.raises(models.ModelBusy):manager.open_session(('other', 'other-pet', key()[2]))
    manager.close_session(('other', 'other-pet', key()[2]))
    assert manager.heartbeat(key())['ready']
    with pytest.raises(models.ModelBusy):manager.respond({}, '안녕', owner='other', pet='other-pet')


def test_late_open_cannot_resurrect_a_closed_tab(manager):
    manager.close_session(key())
    assert not manager.open_session(key())['active']
    assert manager.model is None


def test_close_during_loading_releases_after_load_without_resurrecting(manager, monkeypatch):
    entered, finish = threading.Event(), threading.Event()
    real_start = manager.conversation.start
    def start():
        entered.set()
        assert finish.wait(5)
        real_start()
    monkeypatch.setattr(manager.conversation, 'start', start)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(manager.open_session, key())
        assert entered.wait(5)
        assert not manager.close_session(key())['active']
        finish.set()
        assert not future.result(timeout=5)['active']
    assert manager.model is None


def test_missing_heartbeat_and_vision_switch_both_unload(manager):
    manager.open_session(key())
    manager.expires = 0
    manager._close_if_unleased()
    assert manager.model is None and not manager.heartbeat(key())['active']
    manager.open_session(key(1))
    with models.runtime.reserve('vision'):models.runtime.before_vision()
    assert manager.model is None and not manager.heartbeat(key(1))['active']


def test_session_deadline_kills_the_process(manager):
    manager.open_session(key())
    pid = manager.conversation.run({})['pid']
    with pytest.raises(TimeoutError):manager.conversation.run({'hang': True}, timeout=.2)
    assert not psutil.pid_exists(pid) and manager.model is None


def test_close_cancels_real_unfinished_startup(manager, monkeypatch):
    created = threading.Event()
    pids = []
    def delayed(*args, **kwargs):
        process = REAL_POPEN([sys.executable, '-u', '-c', 'import time;time.sleep(60)'], **kwargs)
        pids.append(process.pid); created.set()
        return process
    monkeypatch.setattr(models.subprocess, 'Popen', delayed)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(manager.open_session, key())
        assert created.wait(5)
        manager.close_session(key())
        assert not future.result(timeout=5)['active']
    assert manager.model is None and not psutil.pid_exists(pids[0])


def test_background_monitor_releases_an_expired_lease(manager):
    manager.open_session(key())
    pid = manager.conversation.run({})['pid']
    manager.expires = 0
    deadline = time.monotonic() + 7
    while psutil.pid_exists(pid) and time.monotonic() < deadline:
        time.sleep(.1)
    assert not psutil.pid_exists(pid) and manager.model is None


def test_conversation_routes_require_pet_ownership_and_valid_session_id(manager, monkeypatch):
    monkeypatch.setattr(api, 'backend', manager)
    client = TestClient(api.app)
    tokens = list(json.loads(os.environ['DEV_TOKENS']))
    headers = {'Authorization':'Bearer ' + tokens[0]}
    pet = client.post('/pets', json={}, headers=headers).json()['pet_id']
    route = f'/pets/{pet}/chat-session'
    body = {'session_id':uuid.uuid4().hex, 'active':True}
    assert client.post(route, json=body).status_code == 401
    assert client.post(route, json=body, headers={'Authorization':'Bearer '+tokens[1]}).status_code == 404
    assert client.post(route, json={**body,'session_id':'bad'}, headers=headers).status_code == 422
    assert client.post(route, json=body, headers=headers).json()['ready']
    assert client.post(route+'/heartbeat', json=body, headers=headers).json()['ready']
    assert not client.post(route, json={**body,'active':False}, headers=headers).json()['active']
    assert manager.model is None
