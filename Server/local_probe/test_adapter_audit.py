"""Metadata-only adapter audit: no torch/PEFT import, weights or GPU required."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from Server.local_probe.gpu_gateway import adapter_activation_audit


class MetadataOnlyModel:
    def __init__(self):
        self.active_adapters = ['existing_v1']
        self.peft_config = {'existing_v1': object()}
        self._adapters_disabled = False
        self.layers = [SimpleNamespace(name='text.layer.' + str(i), enabled=True,
                                       active_adapters=['existing_v1'], available_adapters=['existing_v1']) for i in range(2)]
        self.modules = [SimpleNamespace(adapter_layer_names=('lora_A', 'lora_B'), disable_adapters=False,
                                        active_adapters=['existing_v1']) for _ in range(2)]
        self.status = SimpleNamespace(active_adapters=['existing_v1'], num_adapter_layers=2, enabled=True, merged_adapters=[])
        self.read_calls = []

    def get_model_status(self):
        self.read_calls.append('get_model_status')
        return self.status

    def get_layer_status(self):
        self.read_calls.append('get_layer_status')
        return self.layers

    def named_modules(self):
        self.read_calls.append('named_modules')
        return [('text.layer.' + str(i), module) for i, module in enumerate(self.modules)]

    def set_adapter(self, *_):
        pytest.fail('Audit must never change the selected adapter')

    def disable_adapter(self, *_):
        pytest.fail('Audit must never change adapter state')

    def generate(self, *_):
        pytest.fail('Audit must not perform inference')

    def cuda(self, *_):
        pytest.fail('Audit must not move a model to a GPU')


def test_expected_active_adapter_is_recorded_using_safe_metadata_only():
    model = MetadataOnlyModel()
    before = deepcopy((model.active_adapters, model._adapters_disabled, model.status, model.layers, model.modules))
    audit = adapter_activation_audit(model)
    assert audit['verified_existing_v1_active'] is True
    assert audit['verified_expected_adapter_active'] is True
    assert audit['selected_adapter_name'] == 'existing_v1'
    assert audit['active_adapter_names'] == ['existing_v1']
    assert audit['disable_adapters'] is False
    assert audit['adapter_layer_count'] == audit['inspected_disable_flag_count'] == 2
    assert audit['disabled_adapter_layer_count'] == 0
    assert len(audit['activation_state_sha256']) == 64
    assert before == (model.active_adapters, model._adapters_disabled, model.status, model.layers, model.modules)
    assert model.read_calls == ['get_model_status', 'get_layer_status', 'named_modules']
    assert all(isinstance(value, (str, bool, int)) or isinstance(value, list) and all(isinstance(name, str) for name in value)
               for value in audit.values())


@pytest.mark.parametrize('state', ['wrong_active', 'globally_disabled', 'one_layer_disabled', 'irregular_enabled',
                                  'irregular_active', 'missing_adapter', 'zero_layers', 'unexpected_merged', 'irregular_merged'])
def test_inactive_or_inconsistent_adapter_is_recorded_without_repair_or_false_success(state):
    model = MetadataOnlyModel()
    if state == 'wrong_active':
        model.active_adapters = ['default']
    elif state == 'globally_disabled':
        model._adapters_disabled = True
    elif state == 'one_layer_disabled':
        model.modules[0].disable_adapters = True
    elif state == 'irregular_enabled':
        model.status.enabled = 'irregular'
    elif state == 'irregular_active':
        model.status.active_adapters = 'irregular'
    elif state == 'missing_adapter':
        model.layers[0].available_adapters = []
    elif state == 'zero_layers':
        model.layers, model.modules = [], []
        model.status.num_adapter_layers = 0
    elif state == 'unexpected_merged':
        model.status.merged_adapters = ['existing_v1']
    else:
        model.status.merged_adapters = 'irregular'
    audit = adapter_activation_audit(model)
    assert audit['verified_existing_v1_active'] is False
    if state == 'globally_disabled':
        assert model._adapters_disabled is True and audit['disable_adapters'] is True
    if state == 'wrong_active':
        assert model.active_adapters == ['default']


def test_metadata_reader_failure_records_only_exception_name_without_tensor_or_message_content():
    model = MetadataOnlyModel()

    def broken_status():
        raise RuntimeError('private model diagnostic content must not be recorded')

    model.get_model_status = broken_status
    audit = adapter_activation_audit(model)
    assert audit == {'selected_adapter_name': 'existing_v1', 'verified_existing_v1_active': False,
                     'verified_expected_adapter_active': False,
                     'audit_error_name': 'RuntimeError'}


def test_activation_hash_is_stable_but_changes_for_disabled_layer():
    model = MetadataOnlyModel()
    first = adapter_activation_audit(model)['activation_state_sha256']
    assert adapter_activation_audit(model)['activation_state_sha256'] == first
    model.modules[1].disable_adapters = True
    assert adapter_activation_audit(model)['activation_state_sha256'] != first
