"""Offline native HealthMon epoch-10 image editing; never falls back to a base-only model."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runtime.evolution_2511.assets import (ADAPTER_SHA256, CONFIG, MODEL_ID,
    REVISION, SOURCE_COMMIT, base_files, checked, read, sha256, validate_adapter)


def model_paths(root):
    root = Path(root).resolve()
    result = {}
    receipt_file = root / 'base-verification.json'
    receipt = read(receipt_file) if receipt_file.is_file() else {}
    verified = {entry['path'].replace('\\', '/'): entry for entry in receipt.get('files', [])}
    for model, item, path, directory in base_files(root):
        previous = verified.get(path.relative_to(root).as_posix(), {})
        current = path.stat() if path.is_file() else None
        if not (current and current.st_size == item['bytes'] and
                previous.get('sha256') == item['sha256'] and
                previous.get('mtime_ns') == current.st_mtime_ns and
                previous.get('bytes') == item['bytes']):
            checked(path, item)
        result[model['repo_id']] = directory
    return result


def run(root, parent, prompt_file, output, seed=42):
    started = time.monotonic()
    root, parent, prompt_file, output = map(Path, (root, parent, prompt_file, output))
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata_path = output.with_suffix(output.suffix + '.json')
    if output.exists() or metadata_path.exists():
        raise ValueError('Choose a new output path; existing inference artifacts are preserved')
    model = read(CONFIG / 'model.json')
    adapter = root / 'adapter/weights/healthmon_epoch10.safetensors'
    identity = validate_adapter(adapter, model)
    commit_file = Path('/opt/healthmon-diffsynth-commit')
    if not commit_file.is_file() or commit_file.read_text().strip() != SOURCE_COMMIT:
        raise ValueError('The pinned HealthMon DiffSynth Docker image is required')
    paths = model_paths(root)
    prompt = prompt_file.read_text(encoding='utf-8').strip()
    if not prompt or not parent.is_file():
        raise ValueError('A parent image and nonempty evolution prompt are required')
    for key, value in {'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
                       'DIFFSYNTH_SKIP_DOWNLOAD': 'True'}.items():
        os.environ[key] = value

    import torch
    from PIL import Image, ImageOps
    from safetensors.torch import load_file
    from diffsynth.pipelines.qwen_image import QwenImagePipeline, ModelConfig
    from diffsynth.core.vram.layers import LoRAHotLoadMixin

    if not torch.cuda.is_available():
        raise RuntimeError('NVIDIA GPU is unavailable in the evolution container')
    # Keep original BF16 precision. Disk-backed weights avoid loading the entire
    # 57.7 GB base into host RAM; only current layers are brought onto the GPU.
    memory = dict(offload_dtype='disk', offload_device='disk',
                  onload_dtype='disk', onload_device='disk',
                  preparing_dtype=torch.bfloat16, preparing_device='cuda',
                  computation_dtype=torch.bfloat16, computation_device='cuda')
    total_gib = torch.cuda.get_device_properties(0).total_memory / 1024**3
    vram_limit = max(1.0, total_gib - 8.0)
    base = paths['Qwen/Qwen-Image']
    transformer = paths[MODEL_ID] / 'transformer'
    print('Loading pinned 2511 base with disk offload (BF16)', flush=True)
    pipe = QwenImagePipeline.from_pretrained(
        torch_dtype=torch.bfloat16, device='cuda', vram_limit=vram_limit,
        model_configs=[
            ModelConfig(path=[str(p) for p in sorted(transformer.glob('*.safetensors'))], **memory),
            ModelConfig(path=[str(p) for p in sorted((base / 'text_encoder').glob('*.safetensors'))], **memory),
            ModelConfig(path=str(base / 'vae/diffusion_pytorch_model.safetensors'), **memory),
        ],
        tokenizer_config=ModelConfig(path=str(base / 'tokenizer')),
        processor_config=ModelConfig(path=str(paths['Qwen/Qwen-Image-Edit'] / 'processor')),
    )
    if any(part is None for part in (pipe.dit, pipe.text_encoder, pipe.vae)):
        raise RuntimeError('A required pinned model component was not loaded')
    # safetensors CUDA handles retain entire shards, including tensors that the
    # layer offloader believes are still on disk. Stage individual tensors via
    # CPU instead; only the active/cached BF16 layers enter VRAM. Keep this
    # explicit for the pinned DiffSynth version instead of changing its vendor
    # code or silently quantizing the trained model.
    maps = {}
    for component in (pipe.dit, pipe.text_encoder, pipe.vae):
        for module in component.modules():
            disk_map = getattr(module, 'disk_map', None)
            if disk_map is not None:
                maps[id(disk_map)] = disk_map
    if len(maps) != 3:
        raise RuntimeError('Expected one disk map per pinned model component')
    for disk_map in maps.values():
        disk_map.device = 'cpu'
        disk_map.buffer_size = 64 * 1024**2
        disk_map.flush_files()
    print('CPU-staged safetensors; GPU layer cache limit %.1f GiB' % vram_limit, flush=True)
    weights = load_file(str(adapter), device='cpu')
    converted = pipe.lora_loader(torch_dtype=torch.bfloat16, device='cuda').convert_state_dict(weights)
    expected = {key.removesuffix('.lora_A.weight') for key in converted if key.endswith('.lora_A.weight')}
    wrappers = {module.name: module for module in pipe.dit.modules() if isinstance(module, LoRAHotLoadMixin)}
    if len(expected) != identity['linear_layer_pairs'] or expected - wrappers.keys():
        raise RuntimeError('Native LoRA does not match every expected transformer layer')
    for name in expected:
        layer = wrappers[name]
        a, b = converted[name + '.lora_A.weight'], converted[name + '.lora_B.weight']
        if a.shape[1] != layer.in_features or b.shape[0] != layer.out_features:
            raise RuntimeError('LoRA dimensions do not match the pinned base: ' + name)
    # Pass BF16 GPU tensors explicitly; load_lora(state_dict=...) does not cast.
    weights = {key: value.to(device='cuda', dtype=torch.bfloat16) for key, value in weights.items()}
    pipe.load_lora(pipe.dit, state_dict=weights, alpha=model['loader_alpha'], hotload=True)
    patched = {name for name, module in wrappers.items()
               if len(module.lora_A_weights) == 1 and len(module.lora_B_weights) == 1}
    if patched != expected:
        raise RuntimeError('Some native LoRA layers were not applied')
    del weights, converted
    settings = model['inference']
    with Image.open(parent) as source:
        source = ImageOps.exif_transpose(source).convert('RGB')
        reference = ImageOps.pad(source, (settings['width'], settings['height']), color='white')
    print(f'Applied {len(patched)} native LoRA layers; running {settings["steps"]} steps', flush=True)
    result = pipe(prompt=prompt, negative_prompt=settings['negative_prompt'],
                  edit_image=[reference], height=settings['height'], width=settings['width'],
                  num_inference_steps=settings['steps'], cfg_scale=settings['cfg_scale'],
                  zero_cond_t=settings['zero_cond_t'], edit_image_auto_resize=settings['edit_image_auto_resize'],
                  seed=seed, rand_device='cpu')
    result.save(output)
    metadata = {
        'status': 'PASS', 'local_inference': True, 'model_id': MODEL_ID, 'model_revision': REVISION,
        'backend': model['backend'], 'adapter': identity, 'lora_layers_applied': len(patched),
        'mode': 'native_image_edit', 'quantization_used': False, 'memory_mode': 'bf16_disk_offload',
        'seed': seed, 'inference': settings, 'parent_sha256': sha256(parent),
        'prompt_sha256': sha256(prompt_file), 'elapsed_seconds': round(time.monotonic() - started, 3),
        'output': {'sha256': sha256(output), 'width': result.width, 'height': result.height},
    }
    temporary = metadata_path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    temporary.replace(metadata_path)
    print(json.dumps(metadata, indent=2), flush=True)
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('model-root', 'parent', 'prompt-file', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    run(args.model_root, args.parent, args.prompt_file, args.output, args.seed)


if __name__ == '__main__':
    main()
