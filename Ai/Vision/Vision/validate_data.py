"""Fail early on missing labels, invalid annotations and exact split leakage."""
import argparse
import hashlib
import math
from pathlib import Path
import yaml
from PIL import Image

def validate(config_path):
    config_path = Path(config_path).resolve()
    cfg = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    root = Path(cfg.get('path', config_path.parent))
    if not root.is_absolute():
        root = config_path.parent / root
    names = cfg['names']
    if isinstance(names, dict) and set(names) != set(range(len(names))):
        raise ValueError('Class names must use contiguous integer IDs starting from zero')
    seen, report = {}, {}
    for split in ('train', 'val'):
        entry = Path(cfg[split])
        entry = entry if entry.is_absolute() else root / entry
        if entry.is_dir():
            images = sorted(p for p in entry.rglob('*') if p.suffix.lower() in ('.jpg', '.jpeg', '.png'))
        else:
            images = [Path(line) if Path(line).is_absolute() else entry.parent / line for line in entry.read_text(encoding='utf-8').splitlines() if line.strip()]
        if not images:
            raise ValueError(f'No images in {split}')
        count, measured = 0, 0
        for path in images:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in seen and seen[digest] != split:
                raise ValueError(f'Identical image appears in train and val: {path}')
            seen[digest] = split
            with Image.open(path) as image:
                image.verify()
            parts = list(path.parts)
            if 'images' not in parts:
                raise ValueError(f'Expected images/labels directory layout: {path}')
            parts[len(parts) - 1 - parts[::-1].index('images')] = 'labels'
            label = Path(*parts).with_suffix('.txt')
            for number, row in enumerate(label.read_text().splitlines(), 1):
                values = list(map(float, row.split()))
                if len(values) != 6 or not all(math.isfinite(v) for v in values):
                    raise ValueError(f'{label}:{number}: need six finite numbers')
                c, x, y, w, h, grams = values
                if c != int(c) or not 0 <= c < len(names) or not (0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1) or (grams <= 0 and grams != -1):
                    raise ValueError(f'{label}:{number}: invalid class, box, or weight')
                count += 1
                measured += grams > 0
        report[split] = {'images': len(images), 'objects': count, 'measured_weight_objects': measured}
    return report

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('data')
    print(validate(p.parse_args().data))
