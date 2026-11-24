"""Explicit operator-gated, sequential use of the existing Docker/GPU stack."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time

from .contracts import validate_request
from .runtime import EXECUTION_CACHES,canonical,prepare_runtime,sha
from .store import Conflict

CONTAINER_ROOT='/opt/healthmon/Ai/Generation3D'


def local_phase_command(runtime,root,model_root,vendor_root,phase,job_id,image_model_root):
    """The portable AI container already owns the GPU; no Docker socket needed."""
    if os.name!='posix' or not Path('/.dockerenv').is_file():
        raise ValueError('Process execution is supported only inside the prepared AI container')
    runtime,root=Path(runtime),Path(root)
    links={runtime/'models':Path(model_root),runtime/'vendor':Path(vendor_root),
           runtime/'outputs/common_gateway/work':root/'work',
           runtime/'outputs/common_gateway/parents':root/'parents',
           runtime.parent/'packages/Ai/Generation3D':runtime}
    for target,source in links.items():
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.is_symlink():
            if target.resolve()!=source.resolve(): raise ValueError('Unexpected runtime link')
        elif target.exists():
            raise ValueError('Existing runtime data blocks a required model link')
        else:
            target.symlink_to(source.resolve(),target_is_directory=True)
    environment=dict(os.environ,HEALTHMON_RUNTIME=str(runtime),
        PYTHONPATH=str(runtime.parent/'packages')+os.pathsep+str(Path(__file__).resolve().parents[4]),
        HEALTHMON_MATTING_CHECKPOINT=str(Path(model_root)/'matting/bria-rmbg.onnx'),
        HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',DIFFSYNTH_SKIP_DOWNLOAD='True')
    if image_model_root:
        environment['HEALTHMON_EVOLUTION_MODEL_ROOT']=str(image_model_root)
    stage='evolution2511' if phase=='image' and image_model_root else 'qwen'
    python=f'/opt/healthmon-envs/{stage}/bin/python'
    return ['bash','/usr/local/bin/healthmon-entrypoint',python,
            str(runtime/'runtime/common_gateway/gpu_entry.py'),phase,'--job-id',job_id],environment


def run_local_phase(command,*,stdout,stderr,check,timeout,env):
    import signal
    process=subprocess.Popen(command,stdout=stdout,stderr=stderr,env=env,start_new_session=True)
    try:
        return subprocess.CompletedProcess(command,process.wait(timeout=timeout))
    except BaseException:
        # Include image/reconstruction children before releasing the GPU lease.
        try: os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        process.wait()
        raise


def docker_command(root,model_root,vendor_root,job_id,phase,image='healthmon-3d:3090',*,runtime=None,image_model_root=None):
    root=Path(root).resolve()
    python='/opt/healthmon-envs/qwen/bin/python'
    container='healthmon-v22-'+hashlib.sha256(job_id.encode()).hexdigest()[:24]+'-'+phase
    cache_mounts=[]
    for name in EXECUTION_CACHES:
        cache_mounts.extend(['--mount',f'type=bind,src={root/"cache/trellis"/name},dst={CONTAINER_ROOT}/models/trellis/{name}'])
    if image_model_root is not None and phase=='image':
        image='healthmon-evolution-2511:local'
        python='/opt/healthmon-envs/evolution2511/bin/python'
        cache_mounts.extend(['--mount',f'type=bind,src={Path(image_model_root).resolve()},dst=/opt/healthmon-evolution2511-models,readonly',
                             '-e','HEALTHMON_EVOLUTION_MODEL_ROOT=/opt/healthmon-evolution2511-models'])
    return ['docker','run','--rm','--name',container,'--network','none','--gpus','all','--memory','12g','--memory-swap','14g',
            '--mount',f'type=bind,src={runtime or root/"runtime"},dst={CONTAINER_ROOT}',
            '--mount',f'type=bind,src={Path(model_root).resolve()},dst={CONTAINER_ROOT}/models,readonly',
            '--mount',f'type=bind,src={Path(vendor_root).resolve()},dst={CONTAINER_ROOT}/vendor,readonly',
            *cache_mounts,
            '--mount',f'type=bind,src={root/"work"},dst={CONTAINER_ROOT}/outputs/common_gateway/work',
            '--mount',f'type=bind,src={root/"parents"},dst={CONTAINER_ROOT}/outputs/common_gateway/parents,readonly',
            '-e','HF_HUB_OFFLINE=1','-e','TRANSFORMERS_OFFLINE=1','-e','HF_HUB_DISABLE_IMPLICIT_TOKEN=1',
            '-e','PYTHONDONTWRITEBYTECODE=1',image,
            python,'runtime/common_gateway/gpu_entry.py',phase,'--job-id',job_id]


def run_once(settings,store,model_root,vendor_root,*,allow_gpu=False,runner=None,image_model_root=None,execution_mode='docker'):
    if not allow_gpu: raise PermissionError('GPU execution requires an explicit operator start after the other GPU workload stops')
    if execution_mode not in ('docker','process'): raise ValueError('Unknown evolution execution mode')
    runtime=prepare_runtime(settings.work_root,model_root,vendor_root,versioned=True)
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
        if image_model_root is not None:
            from ..evolution_2511.lineage import require_slime_parent
            require_slime_parent(job['parent'])
            from ..evolution_2511.assets import CONFIG,read,validate_adapter
            validate_adapter(Path(image_model_root)/'adapter/weights/healthmon_epoch10.safetensors',read(CONFIG/'model.json'))
            request['image_backend']='healthmon-2511'
        request_file=folder/'request.json'
        if request_file.exists() and request_file.read_text(encoding='utf-8').strip()!=canonical(request):
            raise ValueError('Frozen GPU execution input changed')
        request_file.write_text(canonical(request)+'\n',encoding='utf-8')
        execution_file=folder/'execution.json'
        execution={'runtime_provenance_sha256':sha(runtime.parent/'runtime-provenance.json'),
                   'image_backend':request.get('image_backend','qwen-2.1'),
                   'execution_mode':execution_mode,
                   'image_model_root':str(Path(image_model_root).resolve()) if image_model_root else None}
        if execution_file.exists() and json.loads(execution_file.read_text(encoding='utf-8'))!=execution:
            raise ValueError('Execution code or model changed; create a new request')
        execution_file.write_text(canonical(execution)+'\n',encoding='utf-8')
        for phase in ('plan','image','evolution_check','reconstruction'):
            if lost.is_set(): raise Conflict('Worker lease lost; do not publish')
            store.update(job['id'],expected_lease=token,phase=phase)
            command=docker_command(settings.work_root,model_root,vendor_root,job['id'],phase,
                                   runtime=runtime,image_model_root=image_model_root)
            options={}
            if execution_mode=='process':
                command,environment=local_phase_command(runtime,settings.work_root,model_root,vendor_root,phase,job['id'],image_model_root)
                options['env']=environment
            log=folder/(phase+'.log')
            with log.open('a',encoding='utf-8') as stream:
                try:
                    execute=runner or (run_local_phase if execution_mode=='process' else subprocess.run)
                    result=execute(command,stdout=stream,stderr=subprocess.STDOUT,check=False,timeout=7200,**options)
                except subprocess.TimeoutExpired:
                    # Killing docker's CLI alone leaves the GPU container alive.
                    # Remove only the uniquely named container owned by this job.
                    if execution_mode=='docker':
                        (runner or subprocess.run)(['docker','rm','-f',command[command.index('--name')+1]],
                                                   stdout=stream,stderr=subprocess.STDOUT,check=False,timeout=30)
                    raise
            if result.returncode: raise RuntimeError('existing_pipeline_'+phase+'_failed')
        model=folder/'reconstruction/rigging/final_rigged.glb';image=folder/'image.png'
        if model.stat().st_size>settings.max_asset_bytes: raise ValueError('Generated original exceeds configured asset limit; no silent compression')
        from Ai.Generation3D.runtime.unity.job_store import inspect_glb
        mesh=inspect_glb(model)
        metadata=json.loads(image.with_suffix('.png.json').read_text(encoding='utf-8'))
        if metadata.get('status')!='PASS' or metadata.get('output',{}).get('sha256')!=sha(image) or metadata.get('local_inference') is not True:
            raise ValueError('Actual new image inference provenance did not pass')
        if image_model_root is not None:
            from ..evolution_2511.provenance import validate_image
            validate_image(metadata,image,folder/'prompt.txt',parent_file)
        elif metadata.get('model_id')!='Qwen/Qwen-Image-2.1' or metadata.get('model_revision')!='d26bb61231c349cf6b7896fa83353113880e1ba3':
            raise ValueError('Unexpected legacy image model')
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
                    'runtime_provenance_sha256':sha(runtime.parent/'runtime-provenance.json'),
                    'planner_implementation':json.loads((folder/'design.json').read_text(encoding='utf-8'))['implementation'],
                    'frozen_state':job['input']['input']['state'],'frozen_profile':job['input']['input']['profile'],
                    'original_parent':job['parent'],'new_image_sha256':image_digest,'new_model_sha256':digest,
                    'mesh':mesh,'models_replaced':image_model_root is not None,'image_inference':metadata,
                    'training_performed':False,'quantization_used':False,
                    'visual_quality':'REQUIRES_REVIEW','animation_quality':'REQUIRES_REVIEW'}
        (folder/'provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return store.publish(job['id'],result,parent,expected_lease=token)
    except Exception as exc:
        # Never publish a historical mesh as a new result or fall back to a mock.
        return store.update(job['id'],expected_lease=token,status='failed',error=str(exc)[:200],lease_until=None)
    finally:
        stopping.set();renewer.join(timeout=2)
