import copy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from Ai.Generation3D.runtime.evolution_2511 import assets, provenance
from Ai.Generation3D.runtime.common_gateway import runtime
from Ai.Generation3D.runtime.common_gateway.worker import docker_command


@pytest.mark.parametrize('name', ['../outside', '/outside', 'C:/outside', 'folder/../../outside', 'folder\\outside'])
def test_model_manifest_cannot_escape_installation(tmp_path, name):
    with pytest.raises(ValueError):
        assets.contained(tmp_path, name)


def test_incomplete_and_corrupted_files_are_rejected(tmp_path):
    path = tmp_path / 'model.safetensors'
    item = {'bytes': 4, 'sha256': hashlib.sha256(b'good').hexdigest()}
    for value in (b'go', b'evil'):
        path.write_bytes(value)
        with pytest.raises(ValueError):
            assets.checked(path, item)
    path.write_bytes(b'good')
    assert assets.checked(path, item) == path


def test_download_relative_root_and_resume_without_network(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = tmp_path / 'config'
    config.mkdir()
    payload = b'verified public base fixture'
    item = {'name': 'weights/part.safetensors', 'bytes': len(payload),
            'sha256': hashlib.sha256(payload).hexdigest()}
    (config / 'base_models.json').write_text(json.dumps({'models': [
        {'repo_id': 'public/base', 'revision': 'fixed-revision', 'files': [item]}]}))
    monkeypatch.setattr(assets, 'CONFIG', config)
    calls = []
    def download(**kwargs):
        calls.append(kwargs)
        path = Path(kwargs['local_dir']) / kwargs['filename']
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    monkeypatch.setitem(sys.modules, 'huggingface_hub', SimpleNamespace(hf_hub_download=download))
    first = assets.download_base(Path('relative-models'))
    second = assets.download_base(Path('relative-models'))
    assert first == second
    assert len(calls) == 1 and calls[0]['revision'] == 'fixed-revision'
    assert calls[0]['token'] is False
    assert first['files'][0]['path'] == 'base/public--base/fixed-revision/weights/part.safetensors'
    assert first['inference_verified'] is False
    destination = tmp_path / 'relative-models' / first['files'][0]['path']
    destination.write_bytes(b'x' * len(payload))
    with pytest.raises(ValueError, match='checksum'):
        assets.download_base(Path('relative-models'))
    assert destination.read_bytes() == b'x' * len(payload)  # Never overwrite unexplained corruption.


def valid_metadata(tmp_path):
    paths = [tmp_path / name for name in ('image.png', 'prompt.txt', 'parent.png')]
    for path in paths:
        path.write_bytes(path.name.encode())
    model = assets.read(assets.CONFIG / 'model.json')
    return paths, dict(status='PASS', local_inference=True, model_id=assets.MODEL_ID,
        model_revision=assets.REVISION, backend={'commit': assets.SOURCE_COMMIT},
        adapter={'sha256': assets.ADAPTER_SHA256}, lora_layers_applied=720,
        inference=model['inference'], mode='native_image_edit',
        output={'sha256': assets.sha256(paths[0])}, prompt_sha256=assets.sha256(paths[1]),
        parent_sha256=assets.sha256(paths[2]))


@pytest.mark.parametrize('key,value', [
    ('model_id', 'Qwen/Qwen-Image-2.1'), ('model_revision', 'main'),
    ('adapter', {}), ('lora_layers_applied', 719), ('parent_sha256', 'wrong-parent'),
    ('prompt_sha256', 'previous-prompt'), ('local_inference', False),
    ('inference', {'steps': 1}), ('backend', {'commit': 'latest'}),
])
def test_wrong_or_partial_inference_cannot_be_published(tmp_path, key, value):
    paths, metadata = valid_metadata(tmp_path)
    assert provenance.validate_image(metadata, *paths)
    metadata[key] = value
    with pytest.raises(ValueError, match='provenance'):
        provenance.validate_image(metadata, *paths)


def test_changed_output_cannot_be_reused(tmp_path):
    paths, metadata = valid_metadata(tmp_path)
    paths[0].write_bytes(b'replaced image')
    with pytest.raises(ValueError):
        provenance.validate_image(metadata, *paths)


def test_upgrade_preserves_job_database_and_older_runtime(tmp_path, monkeypatch):
    source, work, models, vendor = [tmp_path / name for name in ('source', 'work', 'models', 'vendor')]
    for path in (source / 'runtime', models, vendor, work / 'runtime'):
        path.mkdir(parents=True)
    code = source / 'runtime/worker.py'
    code.write_text('first version')
    legacy = work / 'runtime/legacy.py'
    legacy.write_text('historical code')
    database = work / 'jobs.sqlite3'
    database.write_bytes(b'published assets and pet state fixture')
    monkeypatch.setattr(runtime, 'SOURCE', source)
    first = runtime.prepare_runtime(work, models, vendor, versioned=True)
    assert runtime.prepare_runtime(work, models, vendor, versioned=True) == first
    code.write_text('second version')
    second = runtime.prepare_runtime(work, models, vendor, versioned=True)
    assert first != second
    assert (first / 'runtime/worker.py').read_text() == 'first version'
    assert (second / 'runtime/worker.py').read_text() == 'second version'
    assert legacy.read_text() == 'historical code'
    assert database.read_bytes() == b'published assets and pet state fixture'
    (second / 'runtime/worker.py').write_text('unexpected mutation')
    with pytest.raises(ValueError, match='modified'):
        runtime.prepare_runtime(work, models, vendor, versioned=True)


def test_only_image_phase_loads_the_new_pinned_adapter(tmp_path):
    for phase in ('plan', 'image', 'evolution_check', 'reconstruction'):
        command = docker_command(tmp_path, tmp_path/'old-models', tmp_path/'vendor', 'unique-job', phase,
                                 runtime=tmp_path/'snapshot/runtime', image_model_root=tmp_path/'new-models')
        assert command[command.index('--network') + 1] == 'none'
        assert ('healthmon-evolution-2511:local' in command) is (phase == 'image')
        model_mounts = [arg for arg in command if 'src=' + str((tmp_path/'new-models').resolve()) in arg]
        assert len(model_mounts) == (1 if phase == 'image' else 0)
        assert all(arg.endswith(',readonly') for arg in model_mounts)
