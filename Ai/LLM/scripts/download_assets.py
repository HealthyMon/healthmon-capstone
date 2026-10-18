"""Official assets, immutable model revisions, restart-safe HF downloads."""
import argparse, hashlib, json, os, re, urllib.request, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ['HF_HOME'] = str(ROOT / 'runtime' / 'hf')
os.environ['HF_HUB_DISABLE_XET'] = '1'

def hf_model(repo, name):
    from huggingface_hub import HfApi, snapshot_download
    dest = ROOT / 'models' / name
    lock = ROOT / 'config' / (name + '.json')
    if lock.exists():
        revision = json.loads(lock.read_text())['revision']
    else:
        revision = HfApi().model_info(repo).sha
        lock.write_text(json.dumps({'repo': repo, 'revision': revision, 'path': str(dest)}, indent=2))
    print(f'Downloading {repo}@{revision} into {dest}', flush=True)
    snapshot_download(repo, revision=revision, local_dir=dest, max_workers=3,
                      allow_patterns=['*.json','*.safetensors','pytorch_model.bin','*.model','*.txt','*.jinja','README.md','LICENSE'])
    print(f'COMPLETE {repo}', flush=True)

def postgres():
    page = urllib.request.urlopen('https://www.enterprisedb.com/download-postgresql-binaries').read().decode()
    urls = re.findall(r'https?[^\s"<>]+windows[^\s"<>]+', page)
    print('Official links:', urls[:12], flush=True)
    version = '17.11-3'
    url = f'https://get.enterprisedb.com/postgresql/postgresql-{version}-windows-x64-binaries.zip'
    dest = ROOT / 'runtime' / 'postgres.zip'
    if not dest.exists():
        urllib.request.urlretrieve(url, dest)
    if not (ROOT / 'runtime' / 'pgsql' / 'bin' / 'postgres.exe').exists():
        with zipfile.ZipFile(dest) as z:
            # pgAdmin is unnecessary; preserve only the server and build SDK.
            for info in z.infolist():
                if info.filename.startswith(('pgsql/bin/','pgsql/lib/','pgsql/share/','pgsql/include/')):
                    z.extract(info, ROOT / 'runtime')
    (ROOT/'config'/'postgres.json').write_text(json.dumps({'version': version, 'url': url,
        'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()},indent=2))
    print('COMPLETE postgres',flush=True)

if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('asset',choices=['qwen','bge','postgres']); args=p.parse_args()
    if args.asset=='qwen': hf_model('Qwen/Qwen3.5-9B','qwen3.5-9b')
    elif args.asset=='bge': hf_model('BAAI/bge-m3','bge-m3')
    else: postgres()
