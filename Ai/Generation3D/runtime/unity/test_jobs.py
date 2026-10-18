import json
import os
from unittest.mock import patch
from pathlib import Path
import struct
import tempfile
import time
import threading
import unittest

from fastapi.testclient import TestClient
from job_store import AXES, Store, inspect_glb
from service import create_app, DockerWorker
from filelock import FileLock


def tiny_glb(path):
    doc = dict(asset={'version': '2.0'}, skins=[{'joints': [0]}], images=[{'bufferView': 0}],
        meshes=[{'primitives': [{'attributes': {'POSITION': 0, 'JOINTS_0': 1, 'WEIGHTS_0': 2}, 'indices': 3}]}],
        accessors=[{'count': 3}, {}, {}, {'count': 3}])
    data = json.dumps(doc).encode()
    data += b' ' * (-len(data) % 4)
    path.write_bytes(struct.pack('<4sIIII', b'glTF', 2, 20 + len(data), len(data), 0x4E4F534A) + data)


class Jobs(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        isolated_lock = patch.dict(os.environ, {'HEALTHMON_GPU_LOCK': str(self.root / 'host-gpu.lock')})
        isolated_lock.start()
        self.addCleanup(isolated_lock.stop)
        self.store = Store(self.root / 'state')
        self.model = self.root / 'source.glb'
        tiny_glb(self.model)
        self.image = self.root / 'image.png'
        self.image.write_bytes(b'fixture image')
        self.store.publish('pet', 'starter', 0, self.image, self.model)
        self.body = dict(request_id='event1', level=15,
            stats={a: 0 if a == 'EnergyBalance' else 50 for a in AXES}, score_source='synthetic_test')

    def test_idempotent_conflict_and_milestones(self):
        first = self.store.submit('pet', self.body)
        self.assertEqual(first, self.store.submit('pet', self.body))
        with self.assertRaises(ValueError):
            self.store.submit('pet', {**self.body, 'level': 16})
        with self.assertRaises(ValueError):
            self.store.submit('pet', {**self.body, 'request_id': 'event2'})
        self.assertEqual(self.store.current('pet')['revision'], 'starter')

    def test_failure_keeps_previous_and_restart_resumes(self):
        job = self.store.submit('pet', self.body)
        self.store.update(job['job_id'], status='RUNNING', phase='image')
        def failed(job):
            raise RuntimeError('Injected reconstruction failure')
        with TestClient(create_app(self.root, self.store, failed)) as client:
            for _ in range(100):
                state = client.get('/v1/jobs/' + job['job_id']).json()
                if state['status'] == 'FAILED':
                    break
                time.sleep(.02)
            self.assertEqual(state['status'], 'FAILED')
            self.assertEqual(client.get('/v1/pets/pet/current').json()['revision'], 'starter')

    def test_atomic_publish_and_immutable_versions(self):
        new = self.store.publish('pet', 'new', 1, self.image, self.model, source_revision='starter')
        with self.assertRaises(ValueError):
            self.store.publish('pet', 'stale', 1, self.image, self.model, source_revision='starter')
        self.model.write_bytes(b'broken')
        with self.assertRaises((ValueError, struct.error)):
            self.store.publish('pet', 'bad', 2, self.image, self.model, source_revision='new')
        self.assertEqual(self.store.current('pet'), new)
        self.assertTrue((self.store.pet_dir('pet') / 'versions/starter/model.glb').is_file())

    def test_validation_auth_and_download(self):
        with TestClient(create_app(self.root, self.store, lambda _: None, token='test')) as client:
            self.assertEqual(client.get('/v1/pets/pet/current').status_code, 401)
            headers = {'Authorization': 'Bearer test'}
            self.assertEqual(client.get('/v1/pets/pet/current', headers=headers).status_code, 200)
            self.assertEqual(client.get('/v1/pets/pet/versions/starter/model.glb', headers=headers).content, self.model.read_bytes())
            self.assertEqual(client.get('/v1/pets/pet/versions/starter/unknown', headers=headers).status_code, 404)
            for body in ({**self.body, 'level': 14}, {**self.body, 'stats': {'Mood': 50}},
                         {**self.body, 'stats': {**self.body['stats'], 'EnergyBalance': 50}}):
                self.assertEqual(client.post('/v1/pets/pet/evolutions', json=body, headers=headers).status_code, 409)
        with self.assertRaises(ValueError):
            self.store.current('../outside')

    def test_level_jump_stays_sequential(self):
        job = self.store.submit('pet', {**self.body, 'level': 50})
        self.assertEqual(job['target_stage'], 1)

    def test_recovered_job_reaches_ready_once(self):
        job = self.store.submit('pet', self.body)
        self.store.update(job['job_id'], status='RUNNING', phase='image')
        def complete(job):
            return self.store.publish('pet', job['job_id'], 1, self.image, self.model, source_revision='starter')
        with TestClient(create_app(self.root, self.store, complete)) as client:
            for _ in range(100):
                state = client.get('/v1/jobs/' + job['job_id']).json()
                if state['status'] == 'READY': break
                time.sleep(.02)
            self.assertEqual(state['status'], 'READY')
            self.assertEqual(self.store.current('pet')['stage'], 1)
            self.assertEqual(client.post('/v1/pets/pet/evolutions', json=self.body).json()['job_id'], job['job_id'])

    def test_default_delivery_preserves_original_quality(self):
        job = self.store.submit('pet', self.body)
        worker = DockerWorker(self.root, self.store)
        phases = []
        def command(job, phase, args, reconstruction=False):
            phases.append(phase)
            folder = self.root / 'outputs/unity_service/work' / job['job_id']
            (folder / 'reconstruction/rigging').mkdir(parents=True, exist_ok=True)
            (folder / 'image.png').write_bytes(self.image.read_bytes())
            (folder / 'reconstruction/rigging/final_rigged.glb').write_bytes(self.model.read_bytes())
        worker.command = command
        result = worker(job)
        self.assertNotIn('mobile_export', phases)
        self.assertEqual(result['provenance']['delivery_quality'], 'original')
        self.assertFalse(result['provenance']['optimized'])

    def test_busy_host_gpu_waits_before_starting_docker(self):
        job = self.store.submit('pet', self.body)
        worker = DockerWorker(self.root, self.store)
        worker.gpu_lock.parent.mkdir(parents=True, exist_ok=True)
        started = threading.Event()
        worker.generate = lambda _: started.set()
        with FileLock(str(worker.gpu_lock)):
            thread = threading.Thread(target=worker, args=(job,))
            thread.start()
            self.assertFalse(started.wait(.15))
            self.assertEqual(self.store.job(job['job_id'])['phase'], 'waiting_for_gpu')
        thread.join(timeout=2)
        self.assertTrue(started.is_set())
        self.assertFalse(thread.is_alive())


if __name__ == '__main__':
    unittest.main()
