"""Metadata-only base audit; no torch, PEFT, model, tokenizer or GPU loads."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from Server.local_probe.base_audit import base_only_activation_audit


class PeftAdapterMixin:
    __module__ = 'transformers.integrations.peft'

    def active_adapters(self):
        pytest.fail('The Transformers active_adapters method must not be called')


class MetadataBase(PeftAdapterMixin):
    _hf_peft_config_loaded = False

    def __init__(self):
        self.children = [('language_model.linear', SimpleNamespace())]

    def named_modules(self):
        yield '', self
        yield from self.children

    def generate(self, *_):
        pytest.fail('Audit must never generate')

    def cuda(self, *_):
        pytest.fail('Audit must never move tensors')


@pytest.mark.parametrize('empty_config', [False, True])
def test_plain_base_with_transformers_peft_mixin_is_verified_without_calling_adapter_methods(empty_config):
    model = MetadataBase()
    if empty_config:
        model.peft_config = {}
    before = deepcopy(vars(model))
    audit = base_only_activation_audit(model)
    assert audit['verified_base_only'] is True
    assert audit['peft_config_present'] is empty_config
    assert audit['peft_config_empty'] is True
    assert audit['adapter_layer_count'] == audit['lora_or_tuner_module_count'] == 0
    assert audit['inspected_module_count'] == 2
    assert audit['peft_wrapper_present'] is audit['hf_peft_config_loaded'] is False
    assert audit['verified_expected_adapter_active'] is False
    assert audit['verified_existing_v1_active'] is False
    assert audit['all_layers_select_expected_adapter'] is False
    assert audit['active_adapter_names'] == []
    assert len(audit['activation_state_sha256']) == 64
    assert vars(model) == before
    assert all(isinstance(value, (str, bool, int)) or isinstance(value, list) and not value
               for value in audit.values())


def test_active_adapters_getter_is_never_even_read():
    def unread(_):
        pytest.fail('active_adapters must not even be read by the base audit')
    model = type('UnreadAdapterMethod', (MetadataBase,), {'active_adapters': property(unread)})()
    assert base_only_activation_audit(model)['verified_base_only'] is True


def test_module_without_any_peft_attributes_can_be_verified():
    class PlainModel:
        def named_modules(self):
            return [('', self)]
    assert base_only_activation_audit(PlainModel())['verified_base_only'] is True


@pytest.mark.parametrize('config', [None, [], False, {'existing_v1': object()}])
def test_nonempty_or_ambiguous_peft_config_is_not_a_verified_base(config):
    model = MetadataBase()
    model.peft_config = config
    audit = base_only_activation_audit(model)
    assert audit['verified_base_only'] is False
    assert audit['peft_config_empty'] is False


@pytest.mark.parametrize('flag', [True, None, 0, 'False'])
def test_loaded_or_ambiguous_transformers_adapter_flag_fails_closed(flag):
    model = MetadataBase()
    model._hf_peft_config_loaded = flag
    assert base_only_activation_audit(model)['verified_base_only'] is False


@pytest.mark.parametrize('module_name,class_name', [
    ('peft.peft_model', 'PeftModelForCausalLM'),
    ('peft.tuners.lora.layer', 'Linear'),
    ('local_wrapper', 'PeftModelWrapper'),
    ('local_wrapper', 'BaseTuner'),
])
def test_peft_wrapper_or_inherited_wrapper_is_detected_even_with_no_config(module_name, class_name):
    wrapper = type(class_name, (MetadataBase,), {'__module__': module_name})
    inherited = type('CustomModel', (wrapper,), {})
    audit = base_only_activation_audit(inherited())
    assert audit['verified_base_only'] is False
    assert audit['peft_wrapper_present'] is True


@pytest.mark.parametrize('marker', ['lora_A', 'lora_B', 'adapter_layer_names', 'ia3_l', 'lora_magnitude_vector'])
def test_even_empty_disabled_adapter_containers_are_not_plain_base(marker):
    model = MetadataBase()
    model.children = [('language_model.linear', SimpleNamespace(**{marker: {}}))]
    audit = base_only_activation_audit(model)
    assert audit['verified_base_only'] is False
    assert audit['adapter_layer_count'] == 1


def test_nested_tuner_mro_and_loaded_config_are_detected():
    tuner = type('CustomLoRALinear', (), {})
    model = MetadataBase()
    model.children = [('language_model.linear', tuner())]
    assert base_only_activation_audit(model)['verified_base_only'] is False
    model.children = [('language_model', SimpleNamespace(peft_config={'existing_v1': object()}))]
    assert base_only_activation_audit(model)['verified_base_only'] is False
    model.children = [('language_model', SimpleNamespace(_hf_peft_config_loaded=True))]
    assert base_only_activation_audit(model)['verified_base_only'] is False


@pytest.mark.parametrize('where', ['peft_config', '_hf_peft_config_loaded', 'named_modules', 'iterator', 'marker'])
def test_getter_or_iterator_error_records_exception_class_without_private_message(where):
    private = 'private diagnostic content and tensor text must not enter audit'

    def broken(*_):
        raise RuntimeError(private)

    model = MetadataBase()
    if where in ('peft_config', '_hf_peft_config_loaded'):
        model = type('BrokenMetadata', (MetadataBase,), {where: property(broken)})()
    elif where == 'named_modules':
        model.named_modules = broken
    elif where == 'iterator':
        def partial():
            yield '', model
            broken()
        model.named_modules = partial
    else:
        layer = type('BrokenLayer', (), {'lora_A': property(broken)})()
        model.children = [('language_model.linear', layer)]
    audit = base_only_activation_audit(model)
    assert audit['verified_base_only'] is False
    assert audit['audit_error_name'] == 'RuntimeError'
    assert private not in json.dumps(audit)


@pytest.mark.parametrize('kind', ['empty', 'missing_root', 'duplicate', 'invalid_name', 'invalid_entry'])
def test_unverifiable_module_inventory_cannot_report_base_only(kind):
    model = MetadataBase()
    inventories = {'empty': [], 'missing_root': [('other', SimpleNamespace())],
                   'duplicate': [('', model), ('', model)], 'invalid_name': [(None, model)],
                   'invalid_entry': [model]}
    model.named_modules = lambda: iter(inventories[kind])
    assert base_only_activation_audit(model)['verified_base_only'] is False


def test_audit_hash_is_stable_and_changes_for_adapter_metadata():
    model = MetadataBase()
    first = base_only_activation_audit(model)['activation_state_sha256']
    assert base_only_activation_audit(model)['activation_state_sha256'] == first
    model.children[0][1].lora_A = {}
    audit = base_only_activation_audit(model)
    assert audit['verified_base_only'] is False
    assert audit['activation_state_sha256'] != first
