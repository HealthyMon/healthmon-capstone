"""Versioned GPU-side HTTP contract, isolated from the shared CPU game API.

Uvicorn factory: Ai.Generation3D.runtime.common_gateway.service:from_env --factory
GPU execution is deliberately not started by this HTTP process.
"""
from dataclasses import dataclass,field
import os
from pathlib import Path
import secrets

from fastapi import Depends,FastAPI,Header,HTTPException
from fastapi.responses import FileResponse

from .contracts import CONTRACT,identifier,validate_request
from .store import Conflict,Store


@dataclass
class Settings:
    work_root: Path
    token: str=field(repr=False)
    supported_stages: frozenset=frozenset({1,2,3})
    max_asset_bytes: int=64*1024*1024

    def __post_init__(self):
        if not self.token: raise ValueError('An explicitly provisioned server-only bearer is required')
        self.work_root=Path(self.work_root).resolve()
        if not self.supported_stages<={1,2,3}: raise ValueError('Invalid supported stages')
        if not 0 < self.max_asset_bytes <= 64*1024*1024: raise ValueError('Asset limit must be at most 64 MiB')


def envelope(job):
    result=job['result'] or {'job_id':job['id'],'stage':job['stage'],'status':job['status'],
                           'model_url':None,'model_sha256':None,'size_bytes':None,'error':job['error']}
    return {'contract_version':CONTRACT,'request_id':job['id'],'provenance':'real','result':result}


def create_app(settings,store=None):
    store=store or Store(settings.work_root)
    app=FastAPI(title='HEALTHMON v2.2 existing GPU adapter')
    app.state.settings=settings;app.state.store=store

    def authenticated(authorization:str=Header(default='')):
        if not authorization.startswith('Bearer ') or not secrets.compare_digest(authorization[7:],settings.token):
            raise HTTPException(401,'Server bearer required')

    @app.get('/health')
    def health():
        return {'status':'ok','contract_version':CONTRACT,'supported_stages':sorted(settings.supported_stages),
                'gpu_worker_started':False,'requires_explicit_gpu_start':True,
                'new_gpu_generation_verified':False}

    @app.put('/v1/evolutions/{job_id}',dependencies=[Depends(authenticated)])
    def put(job_id:str,body:dict):
        try:
            validate_request(job_id,body)
            return envelope(store.submit(job_id,body,settings.supported_stages))
        except Conflict as exc: raise HTTPException(409,str(exc)) from exc
        except (ValueError,TypeError,KeyError) as exc: raise HTTPException(422,'Invalid frozen v2.2 request') from exc

    @app.get('/v1/evolutions/{job_id}',dependencies=[Depends(authenticated)])
    def get(job_id:str):
        try:
            identifier(job_id)
            return envelope(store.get(job_id))
        except (KeyError,ValueError) as exc: raise HTTPException(404,'Unknown stable job') from exc

    @app.get('/v1/assets/{job_id}/model.glb',dependencies=[Depends(authenticated)])
    def asset(job_id:str):
        try: job=store.get(identifier(job_id))
        except (KeyError,ValueError) as exc: raise HTTPException(404,'Unknown asset') from exc
        path=settings.work_root/'work'/job_id/'reconstruction/rigging/final_rigged.glb'
        if job['status']!='succeeded' or not path.is_file(): raise HTTPException(404,'New generated model is not published')
        return FileResponse(path,media_type='model/gltf-binary',headers={'Cache-Control':'private, no-cache'})
    return app


def from_env():
    root=os.environ.get('HEALTHMON_GPU_WORK_ROOT')
    if not root: raise ValueError('Explicit isolated HEALTHMON_GPU_WORK_ROOT required')
    stages=frozenset(int(v) for v in os.environ.get('HEALTHMON_GPU_SUPPORTED_STAGES','1,2,3').split(',') if v)
    return create_app(Settings(Path(root),os.environ.get('AI_SERVER_TOKEN',''),stages,
                               int(os.environ.get('HEALTHMON_GPU_MAX_ASSET_BYTES',str(64*1024*1024)))))
