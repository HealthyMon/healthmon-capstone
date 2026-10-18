"""Create a private local recovery copy and import existing source without overwrites."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / 'backups/natural-baseline-20261010'
TARGET = ROOT / 'HEALTHMON/Ai/LLM'
SOURCE_DIRS = ('src', 'scripts', 'tests', 'config', 'docs', 'web', 'migrations', 'integrations', 'data')
SOURCE_FILES = ('.gitignore', '.env.example', 'compose.yaml', 'requirements.txt', 'requirements.lock.txt',
                'START_HERE.md', 'FINAL_STATUS.json', 'IMPROVEMENT_STATUS.json')


def digest(path):
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            sha.update(chunk)
    return sha.hexdigest()


def main():
    if BACKUP.exists():
        raise RuntimeError('Backup already exists; do not overwrite it')
    if (TARGET / 'src').exists():
        raise RuntimeError('Import target already has source; compare before importing')
    BACKUP.mkdir(parents=True)
    for name in (*SOURCE_DIRS, 'models', 'runs', 'runtime/pgdata'):
        path = ROOT / name
        if not path.exists():
            continue
        print('Preserving ' + name, flush=True)
        shutil.copytree(path, BACKUP / name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pid'))
    for name in (*SOURCE_FILES, '.env'):
        if (ROOT / name).is_file():
            shutil.copy2(ROOT / name, BACKUP / name)
    for name in SOURCE_DIRS:
        shutil.copytree(ROOT / name, TARGET / name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in SOURCE_FILES:
        shutil.copy2(ROOT / name, TARGET / name)
    # Runtime binaries, models, secrets, and private stores remain local only.
    manifest = []
    for path in sorted(BACKUP.rglob('*')):
        if path.is_file():
            relative = path.relative_to(BACKUP).as_posix()
            original = ROOT / relative
            sha = digest(path)
            if original.is_file() and digest(original) != sha:
                raise RuntimeError('Source changed during preservation: ' + relative)
            manifest.append({'path': relative, 'bytes': path.stat().st_size, 'sha256': sha})
    (BACKUP / 'manifest.json').write_text(json.dumps({'source': str(ROOT), 'files': manifest,
        'docker': 'daemon unavailable; no container volumes inspected',
        'database': 'offline pgdata copy; no postmaster.pid present before backup'}, indent=2), encoding='utf-8')
    print(json.dumps({'backup': str(BACKUP), 'files': len(manifest),
                      'bytes': sum(row['bytes'] for row in manifest)}), flush=True)


if __name__ == '__main__':
    main()
