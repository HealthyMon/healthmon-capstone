"""Read base-only activation metadata without model imports or tensor access."""
from collections.abc import Mapping
import hashlib
import json
import re


_MISSING = object()
_ADAPTER_ATTRIBUTES = (
    'adapter_layer_names', 'lora_A', 'lora_B', 'lora_embedding_A',
    'lora_embedding_B', 'lora_magnitude_vector', 'ia3_l', 'hada_w1_a',
    'lokr_w1', 'oft_r', 'boft_R',
)


def _class_metadata(value):
    classes = type(value).__mro__
    names = [(cls.__module__, cls.__name__) for cls in classes]
    wrapper = any(module == 'peft' or module.startswith('peft.')
                  or name.startswith(('PeftModel', 'PeftMixedModel'))
                  or name in ('BaseTuner', 'BaseTunerLayer')
                  for module, name in names)
    tuner = wrapper or any(re.search(r'lora|adalora|ia3|loha|lokr|dora|basetuner|tunerlayer', name, re.I)
                           for _, name in names)
    return names, wrapper, tuner


def _empty_config(value):
    config = getattr(value, 'peft_config', _MISSING)
    return config is _MISSING, config is _MISSING or isinstance(config, Mapping) and len(config) == 0


def base_only_activation_audit(model):
    """Verify an unloaded-adapter state using only readable model metadata.

    Transformers' PeftAdapterMixin and its active_adapters method do not imply
    an installed adapter. That method is deliberately neither read nor called.
    Any inaccessible or ambiguous metadata fails closed with an exception name.
    """
    audit = {'model_kind': 'base_only', 'selected_adapter_name': 'none',
             'verified_base_only': False, 'verified_expected_adapter_active': False,
             'verified_existing_v1_active': False, 'all_layers_select_expected_adapter': False,
             'active_adapter_names': [], 'peft_wrapper_present': False,
             'peft_config_present': False, 'peft_config_empty': False,
             'hf_peft_config_loaded': False, 'inspected_module_count': 0,
             'adapter_layer_count': 0, 'lora_or_tuner_module_count': 0,
             'nonempty_or_invalid_peft_config_count': 0,
             'loaded_or_invalid_hf_peft_flag_count': 0}
    metadata = []
    try:
        _, root_wrapper, _ = _class_metadata(model)
        audit['model_class_name'] = type(model).__name__
        audit['model_class_module'] = type(model).__module__
        absent, empty = _empty_config(model)
        audit.update(peft_wrapper_present=root_wrapper, peft_config_present=not absent,
                     peft_config_empty=empty)
        root_loaded = getattr(model, '_hf_peft_config_loaded', False)
        audit['hf_peft_config_loaded'] = root_loaded is not False
        root_seen = False
        names = set()
        for entry in model.named_modules():
            if not isinstance(entry, (tuple, list)) or len(entry) != 2:
                raise TypeError('Invalid named-module metadata')
            name, module = entry
            if not isinstance(name, str) or name in names:
                raise ValueError('Invalid named-module identity')
            names.add(name)
            root_seen = root_seen or module is model
            classes, wrapper, tuner = _class_metadata(module)
            # Container presence is sufficient: a disabled/empty LoRA wrapper
            # is still an adapter-bearing model, not a verified plain base.
            marker = any(getattr(module, attr, _MISSING) is not _MISSING for attr in _ADAPTER_ATTRIBUTES)
            _, config_empty = _empty_config(module)
            loaded = getattr(module, '_hf_peft_config_loaded', False)
            adapter = tuner or marker
            audit['inspected_module_count'] += 1
            audit['adapter_layer_count'] += int(adapter)
            audit['lora_or_tuner_module_count'] += int(adapter)
            audit['nonempty_or_invalid_peft_config_count'] += int(not config_empty)
            audit['loaded_or_invalid_hf_peft_flag_count'] += int(loaded is not False)
            audit['peft_wrapper_present'] = audit['peft_wrapper_present'] or wrapper
            metadata.append({'name': name, 'classes': classes, 'wrapper': wrapper,
                             'adapter': adapter, 'config_empty': config_empty,
                             'hf_peft_flag_false': loaded is False})
        if not root_seen or not audit['inspected_module_count']:
            raise ValueError('Named modules must include the inspected root')
        audit['verified_base_only'] = (
            not audit['peft_wrapper_present'] and empty and root_loaded is False
            and audit['adapter_layer_count'] == 0
            and audit['nonempty_or_invalid_peft_config_count'] == 0
            and audit['loaded_or_invalid_hf_peft_flag_count'] == 0)
    except Exception as exc:
        audit['verified_base_only'] = False
        audit['audit_error_name'] = type(exc).__name__
    audit['activation_state_sha256'] = hashlib.sha256(json.dumps(
        {'audit': audit, 'modules': metadata}, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True).encode()).hexdigest()
    return audit
