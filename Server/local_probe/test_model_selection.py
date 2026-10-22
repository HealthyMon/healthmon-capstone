"""Explicit ready-candidate selection and safe activation names; CPU/files only."""
from copy import deepcopy
import hashlib
import json

import pytest

from Server.local_probe.gpu_gateway import adapter_activation_audit, selected_model_manifest, verify_local_model_files
from Server.local_probe.run_refinement_review import assert_ready, expected_identity
from Server.local_probe.test_adapter_audit import MetadataOnlyModel


def write_json(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')


def local_bundle(tmp_path, version='v1'):
    adapter, base = tmp_path / 'adapter', tmp_path / 'base'
    adapter.mkdir()
    base.mkdir()
    (adapter / 'adapter_config.json').write_bytes(b'{}')
    (adapter / 'adapter_model.safetensors').write_bytes(b'fictional adapter file for CPU checksum testing')
    (base / 'config.json').write_bytes(b'{"model_type":"fictional-cpu-test"}')
    (base / 'model.safetensors').write_bytes(b'fictional base checkpoint')
    metadata = base / '.cache/huggingface/download'
    metadata.mkdir(parents=True)
    for name in ('config.json', 'model.safetensors'):
        (metadata / (name + '.metadata')).write_text('a' * 40 + '\netag\n0\n', encoding='utf-8')
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {'model_version': version, 'status': 'ready', 'format': 'peft_lora',
                'base_model_id': 'Qwen/Qwen3.5-9B', 'base_revision': 'a' * 40,
                'base_config_sha256': sha(base / 'config.json'),
                'artifact_checksums': {name: sha(adapter / name) for name in ('adapter_config.json', 'adapter_model.safetensors')}}
    write_json(adapter / 'healthmon-model.json', manifest)
    return {'adapter_path': str(adapter), 'model_path': str(base)}, manifest


@pytest.mark.parametrize('version', ['v1', 'v2'])
def test_explicit_approved_ready_bundle_checks_real_local_files(tmp_path, version):
    config, expected = local_bundle(tmp_path, version)
    config['expected_model_version'] = version
    assert selected_model_manifest(config) == expected
    verify_local_model_files(config, expected)
    identity = expected_identity(config)
    assert identity['model_version'] == version and identity['adapter_name'] == 'existing_' + version
    assert identity['adapter_sha256'] == expected['artifact_checksums']['adapter_model.safetensors']
    assert len(identity['model_manifest_sha256']) == 64


def test_legacy_private_config_still_selects_v1_only(tmp_path):
    config, _ = local_bundle(tmp_path, 'v1')
    assert selected_model_manifest(config)['model_version'] == 'v1'
    path = tmp_path / 'adapter/healthmon-model.json'
    manifest = json.loads(path.read_text())
    manifest['model_version'] = 'v2'
    write_json(path, manifest)
    with pytest.raises(ValueError):
        selected_model_manifest(config)


@pytest.mark.parametrize('mutation', ['wrong_version', 'not_ready', 'wrong_format', 'wrong_base', 'bad_revision', 'bad_sha', 'missing_artifact', 'artifact_path_escape', 'invalid_checksum_object', 'unapproved_request'])
def test_manifest_mismatch_is_an_error_without_implicit_fallback(tmp_path, mutation):
    config, manifest = local_bundle(tmp_path, 'v2')
    config['expected_model_version'] = 'v2'
    if mutation == 'wrong_version': manifest['model_version'] = 'v1'
    elif mutation == 'not_ready': manifest['status'] = 'candidate'
    elif mutation == 'wrong_format': manifest['format'] = 'other'
    elif mutation == 'wrong_base': manifest['base_model_id'] = 'different/base'
    elif mutation == 'bad_revision': manifest['base_revision'] = 'wrong'
    elif mutation == 'bad_sha': manifest['base_config_sha256'] = 'wrong'
    elif mutation == 'missing_artifact': manifest['artifact_checksums'].pop('adapter_config.json')
    elif mutation == 'artifact_path_escape': manifest['artifact_checksums']['../other'] = 'b' * 64
    elif mutation == 'invalid_checksum_object': manifest['artifact_checksums'] = None
    else: config['expected_model_version'] = 'repair-v5'
    write_json(tmp_path / 'adapter/healthmon-model.json', manifest)
    with pytest.raises(ValueError): selected_model_manifest(config)


@pytest.mark.parametrize('mutation', ['adapter_changed', 'base_config_changed', 'revision_changed', 'missing_metadata', 'empty_metadata', 'missing_weights'])
def test_real_local_file_or_download_revision_mismatch_fails(tmp_path, mutation):
    config, manifest = local_bundle(tmp_path)
    if mutation == 'adapter_changed': (tmp_path / 'adapter/adapter_model.safetensors').write_bytes(b'changed')
    elif mutation == 'base_config_changed': (tmp_path / 'base/config.json').write_bytes(b'changed')
    elif mutation == 'revision_changed': (tmp_path / 'base/.cache/huggingface/download/model.safetensors.metadata').write_text('b' * 40)
    elif mutation == 'missing_metadata': (tmp_path / 'base/.cache/huggingface/download/config.json.metadata').unlink()
    elif mutation == 'empty_metadata': (tmp_path / 'base/.cache/huggingface/download/config.json.metadata').write_text('')
    else: (tmp_path / 'base/model.safetensors').unlink()
    with pytest.raises(ValueError): verify_local_model_files(config, manifest)


def v2_model():
    model = MetadataOnlyModel()
    model.active_adapters = ['existing_v2']
    model.peft_config = {'existing_v2': object()}
    model.status.active_adapters = ['existing_v2']
    for layer in model.layers:
        layer.active_adapters = layer.available_adapters = ['existing_v2']
    for module in model.modules:
        module.active_adapters = ['existing_v2']
    return model


def test_v2_activation_is_never_reported_as_active_v1():
    model = v2_model()
    audit = adapter_activation_audit(model, expected='existing_v2')
    assert audit['verified_expected_adapter_active'] is True
    assert audit['all_layers_select_expected_adapter'] is True
    for field in ('verified_existing_v1_active', 'all_layers_select_existing_v1',
                  'all_layer_statuses_select_existing_v1', 'all_layers_have_existing_v1'):
        assert audit[field] is False
    assert model.active_adapters == ['existing_v2']


def test_wrong_active_adapter_is_not_a_success_for_selected_v2():
    model = v2_model()
    model.modules[0].active_adapters = ['existing_v1']
    assert adapter_activation_audit(model, expected='existing_v2')['verified_expected_adapter_active'] is False


@pytest.mark.parametrize('mutation', ['none', 'wrong_generic_name', 'wrong_version', 'fake_v1_legacy_success'])
def test_runner_preflight_checks_exact_selected_version_and_generic_activation(tmp_path, mutation):
    config, _ = local_bundle(tmp_path, 'v2')
    config['expected_model_version'] = 'v2'
    expected = expected_identity(config)
    health = {'ready': True, 'provenance': 'real', 'local_acceptance_only': True, 'quality_refinement_enabled': True,
              'model': dict(expected, dtype='bfloat16', downloaded=False, adapter_activation=adapter_activation_audit(v2_model(), expected='existing_v2'))}
    if mutation == 'wrong_generic_name': health['model']['adapter_activation']['selected_adapter_name'] = 'existing_v1'
    elif mutation == 'wrong_version': health['model']['model_version'] = 'v1'
    elif mutation == 'fake_v1_legacy_success': health['model']['adapter_activation']['verified_existing_v1_active'] = True
    if mutation == 'none': assert_ready(health, expected)
    else:
        with pytest.raises(ValueError): assert_ready(health, expected)
