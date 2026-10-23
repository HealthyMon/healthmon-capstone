"""Explicit adapter-free pinned selection and immutable full-SHA provenance."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from Server.local_probe import gpu_gateway
from Server.local_probe.gpu_gateway import selected_model_descriptor, verify_local_model_files
from Server.local_probe.run_refinement_review import assert_ready, expected_identity
from Server.local_probe.test_model_selection import local_bundle


def base_fixture(tmp_path, monkeypatch):
    legacy, manifest = local_bundle(tmp_path)
    base = Path(legacy['model_path'])
    (base / 'model.safetensors.index.json').write_bytes(b'{"fictional":"cpu index"}')
    runtime = tmp_path / '.runtime'
    runtime.mkdir()
    monkeypatch.setattr(gpu_gateway, 'ROOT', tmp_path)

    def record(path, shard=False):
        stat = path.stat()
        identity = {'size_bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns, 'inode': stat.st_ino}
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        return {'path': str(path.resolve()), 'sha256': sha, 'unchanged_during_read': True,
                'identity_before': identity, 'identity_after': identity,
                'cached_download_metadata': {'revision': manifest['base_revision'],
                    'declared_file_identity_matches': True, 'etag_kind': 'lfs_sha256' if shard else 'git_blob_sha1',
                    'etag': sha if shard else 'a' * 40}}

    proof = {'schema': 'healthmon.local_base_full_sha256.v1', 'base_path': str(base.resolve()),
             'base_revision': manifest['base_revision'], 'shard_count': 1,
             'shards': [record(base / 'model.safetensors', True)],
             'config_and_index': [record(base / 'config.json'), record(base / 'model.safetensors.index.json')]}
    for key in ('all_shards_match_cached_pinned_revision', 'all_shards_match_declared_lfs_sha256',
                'all_shards_unchanged_during_read', 'base_config_matches_bundle_manifests',
                'all_config_and_index_match_cached_git_blob_identity'):
        proof[key] = True
    path = runtime / 'full-sha-audit.json'
    path.write_text(json.dumps(proof), encoding='utf-8')
    config = {'expected_model_mode': 'base_only', 'expected_model_version': 'local-base-' + manifest['base_revision'],
              'model_path': str(base), 'expected_base_revision': manifest['base_revision'],
              'expected_base_config_sha256': manifest['base_config_sha256'], 'base_shard_audit_path': str(path),
              'expected_base_shard_audit_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    return config, proof, path


def test_explicit_base_only_has_no_synthetic_lora_manifest_or_adapter(tmp_path, monkeypatch):
    config, _, _ = base_fixture(tmp_path, monkeypatch)
    descriptor = selected_model_descriptor(config)
    verify_local_model_files(config, descriptor)
    identity = expected_identity(config)
    assert descriptor['selection_kind'] == 'explicit_existing_local_base'
    assert 'status' not in descriptor and descriptor['artifact_checksums'] == {}
    assert identity['model_mode'] == 'base_only'
    assert identity['model_version'] == 'local-base-' + descriptor['base_revision']
    assert identity['adapter_name'] is None and identity['adapter_sha256'] is None and identity['model_manifest_sha256'] is None
    assert identity['base_shard_proof_sha256'] == config['expected_base_shard_audit_sha256']


@pytest.mark.parametrize('mutation', ['missing_mode', 'bad_mode', 'missing_revision', 'wrong_version', 'adapter_present', 'missing_proof_sha'])
def test_base_mode_never_implicitly_loads_an_adapter_or_defaults_pinned_identity(tmp_path, monkeypatch, mutation):
    config, _, _ = base_fixture(tmp_path, monkeypatch)
    if mutation == 'missing_mode': config.pop('expected_model_mode')
    elif mutation == 'bad_mode': config['expected_model_mode'] = 'automatic'
    elif mutation == 'missing_revision': config.pop('expected_base_revision')
    elif mutation == 'wrong_version': config['expected_model_version'] = 'v2'
    elif mutation == 'adapter_present': config['adapter_path'] = str(tmp_path / 'adapter')
    else: config.pop('expected_base_shard_audit_sha256')
    with pytest.raises(ValueError): selected_model_descriptor(config)


@pytest.mark.parametrize('mutation', ['proof_sha', 'file_changed', 'wrong_revision', 'missing_index', 'wrong_lfs_sha', 'outside_runtime'])
def test_unchanged_full_shard_hash_audit_is_required_before_loading(tmp_path, monkeypatch, mutation):
    config, proof, path = base_fixture(tmp_path, monkeypatch)
    if mutation == 'proof_sha': config['expected_base_shard_audit_sha256'] = 'b' * 64
    elif mutation == 'file_changed': (Path(config['model_path']) / 'model.safetensors').write_bytes(b'changed after audit')
    elif mutation == 'wrong_revision': proof['base_revision'] = 'b' * 40
    elif mutation == 'missing_index': proof['config_and_index'].pop()
    elif mutation == 'wrong_lfs_sha': proof['shards'][0]['cached_download_metadata']['etag'] = 'b' * 64
    else:
        path = tmp_path / 'outside.json'
        config['base_shard_audit_path'] = str(path)
    if mutation not in ('proof_sha', 'file_changed'):
        path.write_text(json.dumps(proof), encoding='utf-8')
        config['expected_base_shard_audit_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError): verify_local_model_files(config, selected_model_descriptor(config))


@pytest.mark.parametrize('mutation', ['none', 'peft_wrapper', 'adapter_nonzero', 'fake_generic_success'])
def test_base_runner_requires_strict_adapter_free_audit(tmp_path, monkeypatch, mutation):
    config, _, _ = base_fixture(tmp_path, monkeypatch)
    expected = expected_identity(config)
    audit = {'verified_base_only': True, 'verified_expected_adapter_active': False, 'verified_existing_v1_active': False,
             'peft_wrapper_present': False, 'peft_config_empty': True, 'hf_peft_config_loaded': False,
             'adapter_layer_count': 0}
    health = {'ready': True, 'provenance': 'real', 'local_acceptance_only': True, 'quality_refinement_enabled': True,
              'model': dict(expected, dtype='bfloat16', downloaded=False, adapter_activation=audit)}
    if mutation == 'peft_wrapper': audit['peft_wrapper_present'] = True
    elif mutation == 'adapter_nonzero': audit['adapter_layer_count'] = 1
    elif mutation == 'fake_generic_success': audit['verified_expected_adapter_active'] = True
    if mutation == 'none': assert_ready(health, expected)
    else:
        with pytest.raises(ValueError): assert_ready(health, expected)
