"""Pinned model distribution, shared by installation and runtime checks."""
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
BACKEND = 'dishseg-noisyvit-food2k-fpb-cpu'


def manifest():
    return json.loads((ROOT / 'models/manifest.json').read_text(encoding='utf-8'))


def verify(root=ROOT):
    checked = {}
    for name, spec in manifest().items():
        path = Path(root) / 'models' / name
        if not path.is_file() or path.stat().st_size != spec['size_bytes']:
            raise ValueError('Missing or incomplete multi-food model: ' + name)
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                digest.update(block)
        if digest.hexdigest() != spec['sha256']:
            raise ValueError('Multi-food model checksum mismatch: ' + name)
        checked[name] = {'sha256': spec['sha256'], 'size_bytes': spec['size_bytes']}
    return checked


def download_models():
    from Server.portable.downloads import download
    for name, spec in manifest().items():
        url = ('https://media.githubusercontent.com/media/HealthyMon/healthmon-capstone/'
               + spec['source_revision'] + '/' + quote(spec['source_path'], safe='/'))
        download({'bytes': spec['size_bytes'], 'sha256': spec['sha256'], 'url': url}, ROOT / 'models' / name)
    return verify()
