"""Local asynchronous evolution bridge. Model inference stays in bounded Docker jobs."""
import argparse
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import secrets
import subprocess
import threading
import time
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from filelock import FileLock
from pydantic import BaseModel, ConfigDict, Field

from job_store import Store, identifier, read, sha


class EvolutionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: str
    level: int = Field(ge=0, le=100, strict=True)
    stats: dict[str, Annotated[float, Field(strict=True)]]
    score_source: str = Field(min_length=1, max_length=128)
    seed: int = Field(default=42, ge=0, lt=2**63, strict=True)


class DockerWorker:
    def __init__(self, runtime, store, quality='original'):
        self.runtime, self.store = Path(runtime).resolve(), store
        self.quality = quality
        self.source = Path(__file__).resolve().parents[2]
        host = self.source.parent / 'LLM' if self.source.parent.name == 'Ai' else self.runtime
        self.gpu_lock = Path(os.getenv('HEALTHMON_GPU_LOCK', str(host / 'runtime/gpu.lock')))

    def compose_command(self, reconstruction=False):
        override = 'compose.reconstruction.yaml' if reconstruction else 'compose.qwen.yaml'
        command = ['docker', 'compose', '-f', 'compose.yaml', '-f', 'runtime/phased/' + override]
        if self.source != self.runtime and (self.source / 'src/healthmon').is_dir():
            # One checked-out source tree; heavy weights/vendor/output data retain their locations.
            destination = '/opt/healthmon/Ai/Generation3D/'
            folders = ('src', 'scripts', 'runtime/phased', 'runtime/lineage', 'runtime/unity', 'configs/evolution')
            overlay = self.runtime / 'outputs/unity_service/source.compose.json'
            overlay.parent.mkdir(parents=True, exist_ok=True)
            overlay.write_text(json.dumps({'services': {'generation3d': {'volumes': [
                {'type': 'bind', 'source': (self.source / folder).as_posix(),
                 'target': destination + folder, 'read_only': True}
                for folder in folders]}}}, indent=2), encoding='utf-8')
            command += ['-f', str(overlay)]
        return command

    def command(self, job, phase, args, reconstruction=False):
        self.store.update(job['job_id'], status='RUNNING', phase=phase)
        folder = self.runtime / 'outputs/unity_service/work' / job['job_id']
        folder.mkdir(parents=True, exist_ok=True)
        command = self.compose_command(reconstruction) + ['run', '--rm', '-T', 'generation3d', *args]
        with (folder / (phase + '.log')).open('a', encoding='utf-8') as log:
            process = subprocess.run(command, cwd=self.runtime, stdout=log, stderr=subprocess.STDOUT)
        if process.returncode:
            raise RuntimeError(f'{phase} failed ({process.returncode}); see {folder / (phase + ".log")}')

    def __call__(self, job):
        # QwenBackend already holds this host lock for its entire CUDA residency.
        # Share it with Docker inference so opening another tab cannot overlap large models.
        self.store.update(job['job_id'], status='RUNNING', phase='waiting_for_gpu')
        self.gpu_lock.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.gpu_lock)):
            return self.generate(job)

    def generate(self, job):
        job_id = job['job_id']
        current = self.store.current(job['pet_id'])
        if current['revision'] == job_id:
            return current  # Crash after publication but before job acknowledgement.
        if current['revision'] != job['source_revision']:
            raise ValueError('The source model changed while this job was queued')
        folder = self.runtime / 'outputs/unity_service/work' / job_id
        folder.mkdir(parents=True, exist_ok=True)
        from job_store import atomic_json
        atomic_json(folder / 'request.json', job)
        relative = folder.relative_to(self.runtime).as_posix()
        python = '/opt/healthmon-envs/qwen/bin/python'
        for phase in ('plan', 'image'):
            self.command(job, phase, ['flock', 'outputs/gpu.lock', python,
                         'runtime/unity/evolution_worker.py', phase, '--job-dir', relative])
        policy = read(folder / 'art_policy.json') if (folder / 'art_policy.json').is_file() else None
        if policy and policy.get('semantic_gate'):
            self.command(job, 'evolution_check', ['flock', 'outputs/gpu.lock', python,
                'runtime/unity/evolution_worker.py', 'evolution_check', '--job-dir', relative])
        self.command(job, 'reconstruction', ['python3', 'runtime/unity/evolution_worker.py',
                     'reconstruction', '--job-dir', relative], reconstruction=True)
        model = folder / 'reconstruction/rigging/final_rigged.glb'
        if self.quality == 'mobile':
            self.command(job, 'mobile_export', ['python3', 'runtime/unity/evolution_worker.py',
                         'mobile_export', '--job-dir', relative], reconstruction=True)
            model = folder / 'mobile/model.glb'
        gate = None
        if policy and policy.get('semantic_gate'):
            import sys
            sys.path.insert(0, str(self.source / 'src'))
            from healthmon.evolution_gate import require_gate
            parent = self.runtime / 'outputs/unity_service/pets' / job['pet_id'] / 'versions' / job['source_revision'] / 'image.png'
            gate = require_gate(folder, parent, policy)
        return self.store.publish(job['pet_id'], job_id, job['target_stage'], folder / 'image.png',
            model, source_revision=job['source_revision'],
            provenance=dict(request_id=job['request_id'], stats=job['stats'],
                score_source=job['score_source'], source_revision=job['source_revision'],
                generation_mode='actual_parent_vision_planning_then_qwen_text_to_image',
                delivery_quality=self.quality, optimized=self.quality != 'original',
                evolution_art_policy=read(folder / 'art_policy.json') if (folder / 'art_policy.json').is_file() else None,
                evolution_check=gate, job_directory=relative, original_model_sha256=sha(folder / 'reconstruction/rigging/final_rigged.glb')))


def create_app(runtime, store=None, worker=None, token=None, quality='original'):
    runtime = Path(runtime).resolve()
    store = store or Store(runtime / 'outputs/unity_service')
    worker = worker or DockerWorker(runtime, store, quality)
    stop = threading.Event()
    worker_thread = None

    def run_queue():
        while not stop.is_set():
            pending = [job for job in store.jobs() if job['status'] in ('QUEUED', 'RUNNING')]
            for job in pending:
                if stop.is_set():
                    break
                try:
                    result = worker(job)
                    store.update(job['job_id'], status='READY', phase='complete', result=result, error=None)
                except Exception as error:
                    store.update(job['job_id'], status='FAILED', phase='failed', error=str(error))
            stop.wait(1)

    @asynccontextmanager
    async def lifespan(app):
        nonlocal worker_thread
        # Prevent two server processes from advancing the same persistent queue.
        lock_file = (store.root / 'worker.lock').open('a+b')
        if os.name == 'nt':
            import msvcrt
            if lock_file.tell() == 0:
                lock_file.write(b'0'); lock_file.flush()
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        worker_thread = threading.Thread(target=run_queue, name='evolution-queue', daemon=True)
        worker_thread.start()
        yield
        stop.set()
        worker_thread.join(timeout=2)
        if not worker_thread.is_alive():
            lock_file.close()

    app = FastAPI(title='HealthMon evolution', version='1.0', lifespan=lifespan)
    app.state.store = store

    def authorized(authorization: str = Header(default='')):
        if token and not secrets.compare_digest(authorization, 'Bearer ' + token):
            raise HTTPException(401, 'Evolution token required')

    @app.get('/health')
    def health():
        return dict(status='ok', worker_alive=bool(worker_thread and worker_thread.is_alive()),
                    milestones=[15, 30, 50], inference='qwen-image-2.1 -> trellis.2 -> riganything')

    @app.get('/v1/pets/{pet}/current', dependencies=[Depends(authorized)])
    def current(pet: str):
        try:
            return store.current(pet)
        except FileNotFoundError as error:
            raise HTTPException(404, str(error))
        except ValueError as error:
            raise HTTPException(422, str(error))

    @app.post('/v1/pets/{pet}/evolutions', status_code=202, dependencies=[Depends(authorized)])
    def submit(pet: str, request: EvolutionRequest):
        try:
            return store.submit(pet, request.model_dump())
        except (ValueError, FileNotFoundError) as error:
            raise HTTPException(409, str(error))

    @app.get('/v1/jobs/{job_id}', dependencies=[Depends(authorized)])
    def job(job_id: str):
        try:
            return store.job(job_id)
        except FileNotFoundError:
            raise HTTPException(404, 'Job not found')
        except ValueError as error:
            raise HTTPException(422, str(error))

    @app.get('/v1/pets/{pet}/versions/{revision}/{filename}', dependencies=[Depends(authorized)])
    def artifact(pet: str, revision: str, filename: str):
        try:
            base = store.pet_dir(pet) / 'versions' / identifier(revision)
        except ValueError as error:
            raise HTTPException(422, str(error))
        if filename not in ('model.glb', 'image.png', 'manifest.json') or not (base / 'manifest.json').exists():
            raise HTTPException(404, 'Published artifact not found')
        return FileResponse(base / filename, headers={'Cache-Control': 'private, max-age=31536000, immutable'})

    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8010)
    parser.add_argument('--ssl-certfile')
    parser.add_argument('--ssl-keyfile')
    parser.add_argument('--delivery-quality', choices=['original', 'mobile'], default='original')
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(create_app(args.runtime_root, token=os.getenv('HEALTHMON_EVOLUTION_TOKEN'), quality=args.delivery_quality),
                host=args.host, port=args.port, ssl_certfile=args.ssl_certfile, ssl_keyfile=args.ssl_keyfile)
