"""Download pinned assets for a clone or GitHub source ZIP, without account tokens."""
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b''):
            digest.update(block)
    return digest.hexdigest()


def checked(path, spec):
    path = Path(path)
    return path.is_file() and path.stat().st_size == spec['bytes'] and sha256(path) == spec['sha256']


def inside(root, name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or not relative.parts or any(p in ('.', '..') or ':' in p or '\\' in p for p in relative.parts):
        raise ValueError('Invalid asset path')
    root = Path(root).resolve()
    path = root.joinpath(*relative.parts).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Asset path escapes installation')
    return path


def is_pointer(path, spec):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 1024:
        return False
    text = path.read_bytes().decode('ascii', errors='replace')
    return (text.startswith('version https://git-lfs.github.com/spec/v1\n') or
            text.startswith('version https://git-lfs.github.com/spec/v1\r\n')) and \
        ('oid sha256:' + spec['sha256']) in text.splitlines() and \
        ('size ' + str(spec['bytes'])) in text.splitlines()


def download(spec, target, *, replace_pointer=False, attempts=3):
    """Reuse valid files; resume transfers; publish only a complete verified file."""
    target = Path(target)
    if checked(target, spec):
        print('Verified, reusing', target.name, flush=True)
        return target
    original_pointer = None
    if target.exists():
        if not replace_pointer or not is_pointer(target, spec):
            raise ValueError('Different existing file preserved: ' + str(target))
        original_pointer = target.read_bytes()
    url = spec.get('url')
    if not url:
        raise RuntimeError('Model download is not published in this checkout yet. '
                           'The maintainer must publish the adapter bundle and set distribution.json; '
                           'no successful installation was reported.')
    parsed = urllib.parse.urlsplit(url)
    try:
        loopback = ipaddress.ip_address(parsed.hostname or '').is_loopback
    except ValueError:
        loopback = parsed.hostname == 'localhost'
    if parsed.username or parsed.password or (parsed.scheme != 'https' and not (parsed.scheme == 'http' and loopback)):
        raise ValueError('Asset downloads require HTTPS')
    if not isinstance(spec.get('bytes'), int) or spec['bytes'] <= 0 or not re.fullmatch('[a-f0-9]{64}', spec.get('sha256', '')):
        raise ValueError('Invalid pinned asset metadata')
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.' + spec['sha256'][:12] + '.partial')
    for attempt in range(attempts):
        offset = temporary.stat().st_size if temporary.exists() else 0
        if offset > spec['bytes']:
            raise ValueError('Oversized partial download preserved: ' + str(temporary))
        if offset == spec['bytes']:
            break
        if shutil.disk_usage(target.parent).free < spec['bytes'] - offset + 64 * 1024**2:
            raise RuntimeError('Not enough disk space for ' + target.name)
        headers = {'User-Agent': 'HealthMon-Installer/1', 'Accept-Encoding': 'identity'}
        if offset:
            headers['Range'] = 'bytes=' + str(offset) + '-'
        print('Downloading', target.name, '(' + str(offset) + '/' + str(spec['bytes']) + ' bytes)', flush=True)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=90) as response:
                if response.status == 206:
                    expected = f'bytes {offset}-{spec["bytes"] - 1}/{spec["bytes"]}'
                    if response.headers.get('Content-Range') != expected:
                        raise ValueError('Unexpected download range')
                    mode = 'ab'
                elif response.status == 200:
                    offset, mode = 0, 'wb'  # Server does not support resuming; start a fresh transfer.
                else:
                    raise ValueError('Unexpected download response')
                transferred = offset
                next_progress = transferred + 64 * 1024**2
                with temporary.open(mode) as stream:
                    while True:
                        block = response.read(1024**2)
                        if not block:
                            break
                        transferred += len(block)
                        if transferred > spec['bytes']:
                            raise ValueError('Download exceeds the pinned size')
                        stream.write(block)
                        if transferred >= next_progress:
                            print(f'{target.name}: {100 * transferred // spec["bytes"]}%', flush=True)
                            next_progress = transferred + 64 * 1024**2
            if transferred != spec['bytes']:
                raise OSError('Download interrupted before the expected size')
            break
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403, 404):
                raise RuntimeError(f'Asset unavailable (HTTP {exc.code}): {target.name}. '
                                   'Check the published download; no account token is requested.') from None
            if attempt + 1 == attempts:
                raise RuntimeError('Download failed; rerun Start to resume ' + target.name) from None
        except (OSError, http.client.HTTPException):
            if attempt + 1 == attempts:
                raise RuntimeError('Download interrupted; rerun Start to resume ' + target.name) from None
    if not checked(temporary, spec):
        raise ValueError('Downloaded checksum mismatch; incomplete file preserved: ' + str(temporary))
    if target.exists() and (original_pointer is None or target.read_bytes() != original_pointer):
        if checked(target, spec):
            return target
        raise ValueError('Destination changed during installation; preserved: ' + str(target))
    temporary.replace(target)
    print('Downloaded and verified', target.name, flush=True)
    return target


def lfs_assets(root, group, manifest=None):
    manifest = manifest or json.loads((HERE / 'lfs-assets.json').read_text(encoding='utf-8'))
    results = []
    for spec in manifest['files']:
        if spec['group'] != group:
            continue
        path = inside(root, spec['path'])
        if group == 'client' and path.is_file() and not is_pointer(path, spec):
            # Preserve edited Unity assets; this restores missing files and LFS pointers only.
            if path.stat().st_size < 1024 and path.read_bytes().startswith(b'version https://git-lfs.github.com/spec/v1'):
                raise ValueError('LFS manifest is out of date for ' + spec['path'])
            continue
        url = ('https://media.githubusercontent.com/media/' + manifest['repository'] + '/' +
               manifest['revision'] + '/' + urllib.parse.quote(spec['path'], safe='/'))
        results.append(download(dict(spec, url=url), path, replace_pointer=True))
    return results
