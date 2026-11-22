"""Install exact model files without changing an existing model installation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import struct
from concurrent.futures import ThreadPoolExecutor

CONFIG = Path(__file__).resolve().parents[2] / 'configs/evolution_2511'
MODEL_ID = 'Qwen/Qwen-Image-Edit-2511'
REVISION = '6f3ccc0b56e431dc6a0c2b2039706d7d26f22cb9'
SOURCE_COMMIT = '08fdc0da8f41426885d9432e9007e6e460a4c30d'
ADAPTER_SHA256 = '9bc8cf6752972b0035a787cba3f2d21a27d501902e9edd199ae7fc02de57350e'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def contained(root, name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or not relative.parts or any(p in ('..', '.') or ':' in p or '\\' in p for p in relative.parts):
        raise ValueError('Unsafe model file path')
    root = Path(root).resolve()
    target = root.joinpath(*relative.parts).resolve()
    if not target.is_relative_to(root):
        raise ValueError('Model file escapes its installation directory')
    return target


def checked(path, item):
    path = Path(path)
    if not path.is_file() or path.stat().st_size != item['bytes']:
        raise ValueError('Missing or incomplete model file: ' + str(path))
    if sha256(path) != item['sha256']:
        raise ValueError('Model checksum mismatch: ' + str(path))
    return path


def validate_adapter(path, model):
    if model['base_model_id'] != MODEL_ID or model['base_revision'] != REVISION:
        raise ValueError('This adapter requires the pinned Qwen-Image-Edit-2511 base')
    if model['adapter_sha256'] != ADAPTER_SHA256 or model['backend']['commit'] != SOURCE_COMMIT:
        raise ValueError('Unrecognized HealthMon checkpoint or loader')
    if model['rank'] != 32 or model['training_alpha_div_rank'] != 1.0 or model['loader_alpha'] != 1.0:
        raise ValueError('Unexpected LoRA rank or scaling')
    checked(path, {'bytes': model['adapter_bytes'], 'sha256': ADAPTER_SHA256})
    with Path(path).open('rb') as stream:
        length = struct.unpack('<Q', stream.read(8))[0]
        if length > 16 * 1024 * 1024:
            raise ValueError('Invalid safetensors header size')
        header = json.loads(stream.read(length))
    tensors = {k: v for k, v in header.items() if k != '__metadata__'}
    if len(tensors) != model['tensor_count']:
        raise ValueError('Incomplete LoRA tensors')
    pairs = 0
    for key, value in tensors.items():
        if value['dtype'] != 'F32' or len(value['shape']) != 2:
            raise ValueError('Unexpected LoRA tensor format')
        if '.lora_A.default.weight' in key:
            other = tensors.get(key.replace('.lora_A.default.weight', '.lora_B.default.weight'))
            if other is None or value['shape'][0] != 32 or other['shape'][1] != 32:
                raise ValueError('Incomplete or mismatched LoRA pair')
            pairs += 1
    if pairs != model['linear_layer_pairs'] or pairs * 2 != len(tensors):
        raise ValueError('Unexpected LoRA target count')
    return {'sha256': ADAPTER_SHA256, 'tensor_count': len(tensors), 'linear_layer_pairs': pairs}


def import_adapter(source, root):
    source, root = Path(source), Path(root)
    manifest = read(CONFIG / 'upload_manifest.json')
    target_root = root / 'adapter'
    sources = []
    for item in manifest['files']:
        candidate = contained(source, item['path'])
        if not candidate.is_file():
            candidate = contained(source, PurePosixPath(item['path']).name)
        sources.append((checked(candidate, item), contained(target_root, item['path']), item))
    for original, target, item in sources:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            checked(target, item)  # Never overwrite a different existing file.
        else:
            shutil.copyfile(original, target)
            checked(target, item)
    return validate_adapter(target_root / 'weights/healthmon_epoch10.safetensors', read(CONFIG / 'model.json'))


def base_files(root):
    for model in read(CONFIG / 'base_models.json')['models']:
        directory = Path(root) / 'base' / model['repo_id'].replace('/', '--') / model['revision']
        for item in model['files']:
            yield model, item, contained(directory, item['name']), directory


def download_base(root):
    from huggingface_hub import hf_hub_download
    root = Path(root).resolve()
    files = list(base_files(root))
    root.mkdir(parents=True, exist_ok=True)
    missing = sum(item['bytes'] for _, item, path, _ in files if not path.exists())
    if shutil.disk_usage(root).free < missing + 2 * 1024**3:
        raise ValueError('Not enough free disk space for the pinned base models')

    def download(entry):
        model, item, path, directory = entry
        if not path.exists():
            print('Downloading ' + model['repo_id'] + '/' + item['name'], flush=True)
            hf_hub_download(repo_id=model['repo_id'], filename=item['name'], revision=model['revision'],
                            local_dir=str(directory), token=False)
        checked(path, item)
        print('Verified ' + model['repo_id'] + '/' + item['name'], flush=True)
        return {'path': path.relative_to(root).as_posix(), 'sha256': item['sha256'],
                'bytes': item['bytes'], 'mtime_ns': path.stat().st_mtime_ns}

    with ThreadPoolExecutor(max_workers=2) as pool:
        verified = list(pool.map(download, files))
    receipt = {'schema': 'healthmon.evolution2511.base.v1', 'files': verified, 'inference_verified': False}
    (root / 'base-verification.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return receipt


def verify(root):
    root = Path(root)
    adapter = validate_adapter(root / 'adapter/weights/healthmon_epoch10.safetensors', read(CONFIG / 'model.json'))
    for _, item, path, _ in base_files(root):
        checked(path, item)
    return {'adapter': adapter, 'base_file_count': len(list(base_files(root))), 'inference_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['import', 'download', 'verify'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--source', type=Path)
    args = parser.parse_args()
    if args.action == 'import':
        if not args.source:
            parser.error('--source is required for import')
        result = import_adapter(args.source, args.root)
    elif args.action == 'download':
        result = download_base(args.root)
    else:
        result = verify(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
