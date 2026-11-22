"""Download official FPB assets, preserving its six-column weight annotations."""
import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from huggingface_hub import HfApi, hf_hub_download
import yaml

ROOT = Path(__file__).resolve().parent
REPO = 'issai/Food_Portion_Benchmark'
WEIGHT_SHA256 = '35cde167ab11e4d62a5d87bcf69f88e937972cebaf1a85869b1874e9fbe0eb1c'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--full', action='store_true', help='Download all train/val images; otherwise 24 per split')
    parser.add_argument('--limit', type=int, default=24)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error('--limit must be positive')
    api = HfApi()
    revision_file = ROOT / 'dataset_revision.txt'
    revision = revision_file.read_text().strip() if revision_file.exists() else api.dataset_info(REPO).sha
    revision_file.write_text(revision)
    def fetch(name):
        return Path(hf_hub_download(REPO, name, repo_type='dataset', revision=revision, local_dir=ROOT / 'assets'))
    weights = fetch('Model Weights/YOLOv12S.pt')
    if hashlib.sha256(weights.read_bytes()).hexdigest() != WEIGHT_SHA256:
        raise ValueError('Official checkpoint SHA256 mismatch; do not load it')
    source_config = fetch('FPB_Dataset/RGB/data.yaml')
    selected = []
    for split in ('train', 'val'):
        prefix = f'FPB_Dataset/RGB/{split}'
        images = sorted(x.path for x in api.list_repo_tree(REPO, path_in_repo=prefix + '/images', repo_type='dataset', revision=revision) if x.path.lower().endswith(('.jpg', '.jpeg', '.png')))
        if not args.full:
            # Spread across the sorted list rather than downloading a single adjacent capture group.
            images = [images[i * len(images) // min(args.limit, len(images))] for i in range(min(args.limit, len(images)))]
        names = images + [prefix + '/labels/' + Path(x).stem + '.txt' for x in images]
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(fetch, names))
        manifest = ROOT / 'assets' / f'{split}_{"full" if args.full else "sample"}.txt'
        manifest.write_text('\n'.join((ROOT / 'assets' / x).as_posix() for x in images) + '\n', encoding='utf-8')
        selected.append((split, str(manifest.resolve())))
        print(f'{split}: {len(images)} image/label pairs', flush=True)
    config = yaml.safe_load(source_config.read_text())
    config.update(dict(selected))
    config['path'] = str((ROOT / 'assets' / 'FPB_Dataset' / 'RGB').resolve())
    config.pop('test', None)  # official test labels are hidden
    target = ROOT / ('data_full.yaml' if args.full else 'data_sample.yaml')
    target.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding='utf-8')
    (ROOT / 'assets' / 'provenance.json').write_text(json.dumps({'repo': REPO, 'revision': revision, 'weight_sha256': WEIGHT_SHA256, 'full': args.full}, indent=2))
    print(f'Ready: {target}')

if __name__ == '__main__':
    main()
