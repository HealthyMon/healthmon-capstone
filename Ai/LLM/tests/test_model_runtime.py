import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import psutil
import pytest

from src import model_runtime as models
from src.prompts import dialogue_context


def test_models_cannot_overlap_and_reservation_releases_after_failure():
    runtime = models.ModelRuntime()
    with runtime.reserve('vision'):
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(lambda: runtime.reserve('qwen').__enter__())
            with pytest.raises(models.ModelBusy):
                future.result()
        assert runtime.status()['active_model'] == 'vision'
    with pytest.raises(ValueError):
        with runtime.reserve('qwen'):
            raise ValueError('injected failure')
    assert runtime.status()['active_model'] is None
    with runtime.reserve('embedding'):
        assert runtime.status()['active_model'] == 'embedding'


def test_nested_embedding_restores_chat_reservation():
    runtime = models.ModelRuntime()
    with runtime.reserve('llm'):
        with runtime.reserve('embedding'):
            assert runtime.active == 'embedding'
        assert runtime.active == 'llm'
    assert runtime.active is None


def test_completed_worker_process_does_not_remain_resident(monkeypatch):
    popen = subprocess.Popen
    def child(*args, **kwargs):
        return popen([sys.executable, '-c',
                      'import json,os,sys;json.load(sys.stdin);print(json.dumps({"pid":os.getpid()}))'], **kwargs)
    monkeypatch.setattr(models.subprocess, 'Popen', child)
    worker = models.ModelWorker('probe')
    result = worker.run({})
    assert not psutil.pid_exists(result['pid'])
    assert worker.process is None and models.runtime.active is None


def test_deadline_kills_owned_worker_and_child(monkeypatch, tmp_path):
    popen = subprocess.Popen
    marker = tmp_path / 'child.pid'
    code = ('import json,subprocess,sys,time,pathlib;job=json.load(sys.stdin);'
            'p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"]);'
            'pathlib.Path(job["marker"]).write_text(str(p.pid));time.sleep(60)')
    def child(*args, **kwargs):
        return popen([sys.executable, '-c', code], **kwargs)
    monkeypatch.setattr(models.subprocess, 'Popen', child)
    worker = models.ModelWorker('probe')
    with pytest.raises(TimeoutError):
        worker.run({'marker': str(marker)}, timeout=1)
    assert marker.is_file(), 'The child must have started for this test to be meaningful'
    assert not psutil.pid_exists(int(marker.read_text()))
    assert worker.process is None and models.runtime.active is None


def test_food_prompt_preserves_facts_and_unknowns_without_transport_metadata():
    activity = {'id': 'activity:food-1', 'revision': 1, 'kind': 'food', 'source': 'user',
                'confirmed': True, 'event_id': 'duplicate-id', 'label': '치킨',
                'food_record': {'food': '치킨', 'grams': None, 'quantity_source': 'not_provided',
                                'analysis_id': 'transport-id', 'vision_backend': 'model-name',
                                'nutrition': {'protein_g': {'available': False, 'value': 0}}}}
    context = {'activities': [activity]}
    compact = dialogue_context(context)['activities'][0]
    assert compact['source'] == 'user' and compact['confirmed']
    assert compact['food_record']['grams'] is None
    assert compact['food_record']['nutrition'] == activity['food_record']['nutrition']
    assert 'analysis_id' not in compact['food_record'] and 'event_id' not in compact
    assert activity['food_record']['analysis_id'] == 'transport-id'


def test_low_vram_refuses_model_load_and_releases_gpu_lease(monkeypatch, tmp_path):
    import torch
    from src import model as model_module
    from src.model import QwenBackend
    (tmp_path / 'runtime').mkdir()
    monkeypatch.setattr(model_module, 'ROOT', tmp_path)
    monkeypatch.setattr(torch.cuda, 'mem_get_info', lambda: (0, 24 * 1024**3))
    backend = QwenBackend()
    with pytest.raises(RuntimeError, match='Insufficient free GPU memory'):
        backend.load()
    assert backend.model is None and not backend.gpu_lease.is_locked
