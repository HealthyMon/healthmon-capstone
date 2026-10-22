"""Explicit operator-gated, sequential use of the existing Docker/GPU stack."""
import json
import hashlib
from pathlib import Path
import shutil
import subprocess
import threading
import time

from .contracts import validate_request
from .runtime import EXECUTION_CACHES,canonical,prepare_runtime,sha
from .store import Conflict

CONTAINER_ROOT='/opt/healthmon/Ai/Generation3D'


def docker_command(root,model_root,vendor_root,job_id,phase,image='healthmon-3d:3090'):
    root=Path(root).resolve()
    container='healthmon-v22-'+hashlib.sha256(job_id.encode()).hexdigest()[:24]+'-'+phase
    cache_mounts=[]
    for name in EXECUTION_CACHES:
        cache_mounts.extend(['--mount',f'type=bind,src={root/"cache/trellis"/name},dst={CONTAINER_ROOT}/models/trellis/{name}'])
    return ['docker','run','--rm','--name',container,'--network','none','--gpus','all','--memory','12g','--memory-swap','14g',
            '--mount',f'type=bind,src={root/"runtime"},dst={CONTAINER_ROOT}',
            '--mount',f'type=bind,src={Path(model_root).resolve()},dst={CONTAINER_ROOT}/models,readonly',
            '--mount',f'type=bind,src={Path(vendor_root).resolve()},dst={CONTAINER_ROOT}/vendor,readonly',
            *cache_mounts,
            '--mount',f'type=bind,src={root/"work"},dst={CONTAINER_ROOT}/outputs/common_gateway/work',
            '--mount',f'type=bind,src={root/"parents"},dst={CONTAINER_ROOT}/outputs/common_gateway/parents,readonly',
            '-e','HF_HUB_OFFLINE=1','-e','TRANSFORMERS_OFFLINE=1','-e','HF_HUB_DISABLE_IMPLICIT_TOKEN=1',
            '-e','PYTHONDONTWRITEBYTECODE=1',image,
            '/opt/healthmon-envs/qwen/bin/python','runtime/common_gateway/gpu_entry.py',phase,'--job-id',job_id]


def run_once(settings,store,model_root,vendor_root,*,allow_gpu=False,runner=None):
    if not allow_gpu: raise PermissionError('GPU execution requires an explicit operator start after the other GPU workload stops')
    runtime=prepare_runtime(settings.work_root,model_root,vendor_root)
    job=store.claim()
    if job is None: return None
    token=job['lease_token'];stopping=threading.Event();lost=threading.Event()
    def heartbeat():
        while not stopping.wait(15):
            try: store.update(job['id'],expected_lease=token,lease_until=time.time()+90)
            except Exception: lost.set();return
    renewer=threading.Thread(target=heartbeat,daemon=True);renewer.start()
    folder=settings.work_root/'work'/job['id'];folder.mkdir(parents=True,exist_ok=True)
    try:
        stats=validate_request(job['id'],job['input'])
        parent_file=settings.work_root/job['parent']['image_relative']
        if sha(parent_file)!=job['parent']['image_sha256']: raise ValueError('Frozen parent image changed')
        request={'input':job['input'],'parent':job['parent'],'stats':stats}
        request_file=folder/'request.json'
        if request_file.exists() and request_file.read_text(encoding='utf-8').strip()!=canonical(request):
            raise ValueError('Frozen GPU execution input changed')
        request_file.write_text(canonical(request)+'\n',encoding='utf-8')
        for phase in ('plan','image','evolution_check','reconstruction'):
            if lost.is_set(): raise Conflict('Worker lease lost; do not publish')
            store.update(job['id'],expected_lease=token,phase=phase)
            command=docker_command(settings.work_root,model_root,vendor_root,job['id'],phase)
            log=folder/(phase+'.log')
            with log.open('a',encoding='utf-8') as stream:
                result=(runner or subprocess.run)(command,stdout=stream,stderr=subprocess.STDOUT,check=False,timeout=7200)
            if result.returncode: raise RuntimeError('existing_pipeline_'+phase+'_failed')
        model=folder/'reconstruction/rigging/final_rigged.glb';image=folder/'image.png'
        if model.stat().st_size>settings.max_asset_bytes: raise ValueError('Generated original exceeds configured asset limit; no silent compression')
        from Ai.Generation3D.runtime.unity.job_store import inspect_glb
        mesh=inspect_glb(model)
        metadata=json.loads(image.with_suffix('.png.json').read_text(encoding='utf-8'))
        if metadata.get('status')!='PASS' or metadata.get('output',{}).get('sha256')!=sha(image) or metadata.get('local_inference') is not True or metadata.get('model_id')!='Qwen/Qwen-Image-2.1' or metadata.get('model_revision')!='d26bb61231c349cf6b7896fa83353113880e1ba3':
            raise ValueError('Actual new image inference provenance did not pass')
        reconstruction=json.loads((folder/'reconstruction/case_result.json').read_text(encoding='utf-8'))
        trellis=json.loads((folder/'reconstruction/trellis/model.trellis.json').read_text(encoding='utf-8'))
        rig=json.loads((folder/'reconstruction/rigging/validation.json').read_text(encoding='utf-8'))
        if reconstruction.get('status')!='PASS' or trellis.get('actual_inference_called') is not True or rig.get('status')!='PASS':
            raise ValueError('Actual TRELLIS/rigging provenance did not pass')
        digest=sha(model);image_digest=sha(image)
        parent_relative=f"parents/{job['pet_id']}/{image_digest}.png"
        parent_copy=settings.work_root/parent_relative
        parent_copy.parent.mkdir(parents=True,exist_ok=True)
        if not parent_copy.exists(): shutil.copyfile(image,parent_copy)
        parent=dict(job['parent'],stage=job['stage'],revision=job['id'],image_sha256=image_digest,
                    model_sha256=digest,image_relative=parent_relative,source_kind='new_gpu_generation')
        result={'job_id':job['id'],'stage':job['stage'],'status':'succeeded',
                'model_url':f"/v1/assets/{job['id']}/model.glb",'model_sha256':digest,'size_bytes':model.stat().st_size,'error':None}
        provenance={'generation_kind':'new_gpu_generation','request_sha256':job['fingerprint'],
                    'runtime_provenance_sha256':sha(settings.work_root/'runtime-provenance.json'),
                    'planner_implementation':json.loads((folder/'design.json').read_text(encoding='utf-8'))['implementation'],
                    'frozen_state':job['input']['input']['state'],'frozen_profile':job['input']['input']['profile'],
                    'original_parent':job['parent'],'new_image_sha256':image_digest,'new_model_sha256':digest,
                    'mesh':mesh,'models_replaced':False,'training_performed':False,'quantization_used':False,
                    'visual_quality':'REQUIRES_REVIEW','animation_quality':'REQUIRES_REVIEW'}
        (folder/'provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return store.publish(job['id'],result,parent,expected_lease=token)
    except Exception as exc:
        # Never publish a historical mesh as a new result or fall back to a mock.
        return store.update(job['id'],expected_lease=token,status='failed',error=str(exc)[:200],lease_until=None)
    finally:
        stopping.set();renewer.join(timeout=2)
