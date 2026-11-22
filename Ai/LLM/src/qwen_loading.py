"""Explicit Qwen base/LoRA selection shared by training and inference."""
import json
from pathlib import Path


def verify_adapter_base(base, adapter):
    """Reject a 9B adapter on 4B before allocating GPU memory."""
    base, adapter = Path(base).resolve(), Path(adapter).resolve()
    config = json.loads((adapter / 'adapter_config.json').read_text(encoding='utf-8'))
    declared = config.get('base_model_name_or_path', '')
    if not declared:
        raise ValueError('Adapter must declare its base model')
    if Path(declared).resolve() == base:
        return
    source_file = base / 'healthmon-source.json'
    source = json.loads(source_file.read_text(encoding='utf-8')) if source_file.exists() else {}
    if declared == source.get('model_id'):
        return
    # Older local adapters can move with the original checkpoint directory.
    if Path(declared.replace('\\', '/')).name.lower() == base.name.lower():
        return
    raise ValueError(f'Adapter base mismatch: {declared!r} != {str(base)!r}')


def loading_kwargs(quantization='none'):
    import torch
    if quantization not in ('none', 'nf4'):
        raise ValueError('Quantization must be none or nf4')
    result = dict(dtype=torch.bfloat16, device_map='cuda:0',
                  attn_implementation='sdpa', local_files_only=True)
    if quantization == 'nf4':
        from transformers import BitsAndBytesConfig
        result['quantization_config'] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type='nf4',
            bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16)
    return result
