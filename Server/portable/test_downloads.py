import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

import pytest

from Server.portable import downloads


@pytest.fixture
def endpoint():
    state = {'payload': b'healthmon-verified-fixture-' * 1024, 'ranges': [], 'cut': False,
             'ignore_range': False, 'status': 200}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state['ranges'].append(self.headers.get('Range'))
            if state['status'] != 200:
                self.send_error(state['status'])
                return
            content = state['payload']
            offset = 0
            if self.headers.get('Range') and not state['ignore_range']:
                offset = int(self.headers['Range'].split('=')[1].split('-')[0])
                self.send_response(206)
                self.send_header('Content-Range', f'bytes {offset}-{len(content)-1}/{len(content)}')
            else:
                self.send_response(200)
            self.send_header('Content-Length', str(len(content)-offset))
            self.end_headers()
            end = len(content)
            if state['cut']:
                state['cut'] = False
                end = max(offset + 1, end // 2)
            self.wfile.write(content[offset:end])
            self.wfile.flush()
            self.close_connection = True
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state['url'] = f'http://127.0.0.1:{server.server_port}/model'
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def spec(endpoint):
    return dict(url=endpoint['url'], bytes=len(endpoint['payload']),
                sha256=hashlib.sha256(endpoint['payload']).hexdigest())


def test_first_download_and_offline_cache_reuse(tmp_path, endpoint):
    item = spec(endpoint)
    path = tmp_path / 'model.bin'
    assert downloads.download(item, path) == path
    assert path.read_bytes() == endpoint['payload']
    assert downloads.download(dict(item, url=None), path) == path
    assert len(endpoint['ranges']) == 1


@pytest.mark.parametrize('ignore_range', [False, True])
def test_partial_download_resumes_or_restarts_when_server_ignores_range(tmp_path, endpoint, ignore_range):
    item = spec(endpoint)
    target = tmp_path / 'model.bin'
    partial = target.with_name(target.name + '.' + item['sha256'][:12] + '.partial')
    partial.write_bytes(endpoint['payload'][:1234])
    endpoint['ignore_range'] = ignore_range
    downloads.download(item, target)
    assert endpoint['ranges'] == ['bytes=1234-']
    assert target.read_bytes() == endpoint['payload'] and not partial.exists()


def test_interrupted_response_is_retried_and_verified(tmp_path, endpoint):
    endpoint['cut'] = True
    target = downloads.download(spec(endpoint), tmp_path/'model.bin')
    assert target.read_bytes() == endpoint['payload']
    assert len(endpoint['ranges']) == 2 and endpoint['ranges'][1].startswith('bytes=')


def test_corrupted_response_is_never_published(tmp_path, endpoint):
    item = spec(endpoint)
    endpoint['payload'] = b'x' * len(endpoint['payload'])
    target = tmp_path/'model.bin'
    with pytest.raises(ValueError, match='checksum'):
        downloads.download(item, target)
    assert not target.exists()


def test_existing_different_file_is_preserved(tmp_path, endpoint):
    target = tmp_path/'model.bin'
    target.write_bytes(b'keep this user file')
    with pytest.raises(ValueError, match='preserved'):
        downloads.download(spec(endpoint), target)
    assert target.read_bytes() == b'keep this user file' and not endpoint['ranges']


def test_source_zip_pointer_is_replaced_only_after_verification(tmp_path, endpoint):
    item = spec(endpoint)
    target = tmp_path/'model.bin'
    pointer = f'version https://git-lfs.github.com/spec/v1\noid sha256:{item["sha256"]}\nsize {item["bytes"]}\n'
    target.write_text(pointer)
    downloads.download(item, target, replace_pointer=True)
    assert target.read_bytes() == endpoint['payload']


@pytest.mark.parametrize('status', [401, 403, 404])
def test_unavailable_distribution_has_clear_failure_without_token_prompt(tmp_path, endpoint, status):
    endpoint['status'] = status
    with pytest.raises(RuntimeError, match=f'HTTP {status}'):
        downloads.download(spec(endpoint), tmp_path/'model.bin')
    assert not (tmp_path/'model.bin').exists()


def test_unpublished_bundle_does_not_report_installation_success(tmp_path):
    spec = {'url': None, 'bytes': 10, 'sha256': 'a'*64}
    with pytest.raises(RuntimeError, match='not published'):
        downloads.download(spec, tmp_path/'fixture.zip')


@pytest.mark.parametrize('name', ['../outside', '/outside', 'C:/outside', 'folder/../../outside', 'folder\\outside'])
def test_distribution_paths_cannot_escape_installation(tmp_path, name):
    with pytest.raises(ValueError):
        downloads.inside(tmp_path, name)


def test_asset_manifest_is_pinned_and_matches_food_checksums():
    manifest = json.loads((downloads.HERE/'lfs-assets.json').read_text(encoding='utf-8'))
    assert len(manifest['revision']) == 40
    assert len({s['path'] for s in manifest['files']}) == len(manifest['files'])
    food = json.loads((downloads.HERE.parents[1]/'Ai/Vision/weights-manifest.json').read_text(encoding='utf-8'))
    for entry in manifest['files']:
        assert entry['bytes'] > 0 and len(entry['sha256']) == 64
        if entry['group'] == 'food':
            expected = food[Path(entry['path']).name]
            assert entry['sha256'] == expected['sha256'] and entry['bytes'] == expected['size_bytes']


def test_edited_unity_asset_is_preserved(tmp_path, monkeypatch):
    target = tmp_path/'Client/custom.fbx'
    target.parent.mkdir()
    target.write_bytes(b'user edit')
    manifest = dict(repository='test/repo', revision='a'*40, files=[
        dict(path='Client/custom.fbx', group='client', bytes=50, sha256='b'*64)])
    monkeypatch.setattr(downloads, 'download', lambda *a, **k: pytest.fail('Edited asset must not be replaced'))
    assert downloads.lfs_assets(tmp_path, 'client', manifest) == []
    assert target.read_bytes() == b'user edit'
