#!/usr/bin/env python3
"""Creative evolution branch queue; same pinned Qwen model, configurable official inference arguments."""
from __future__ import annotations

import argparse
import inspect
import fcntl
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import time
import traceback
import shutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from healthmon.qwen_runner import MODEL_ID, MODEL_REVISION, sha256, write_json, git_revision
from healthmon.quality import inspect_image
from run_selected_3d import load_runtime


def stamp():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--idle-timeout', type=int, default=3600)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    queue = run / 'queue'
    queue.mkdir(parents=True, exist_ok=True)
    runtime = load_runtime(ROOT / 'configs/runtime.json')
    pipe = None
    (ROOT/'outputs').mkdir(exist_ok=True)
    gpu_lock = (ROOT/'outputs/gpu.lock').open('a')
    fcntl.flock(gpu_lock, fcntl.LOCK_EX)
    completed = set()
    idle_since = time.monotonic()
    worker = {'status': 'WAITING', 'started_at': stamp(), 'model_id': MODEL_ID,
              'pid': os.getpid(),
              'model_revision': MODEL_REVISION, 'command': sys.argv,
              'purpose': 'Creative branching evolution; image-only, no TRELLIS or rigging'}
    state = run / 'worker.json'
    write_json(state, worker)
    try:
        from PIL import Image
        import torch
        import diffusers
        from diffusers import QwenImage21Pipeline
        while True:
            if (run / 'STOP').exists():
                break
            pending = [p for p in sorted(queue.glob('*.json')) if p.name not in completed]
            ready = None
            for task_path in pending:
                task = json.loads(task_path.read_text())
                if all(Path(p).is_file() for p in task['images']+task.get('planning_images',[])):
                    ready = (task_path, task)
                    break
            if ready is None:
                worker.update(status='WAITING', completed=len(completed), last_update=stamp(),
                              pending=[p.name for p in pending])
                write_json(state, worker)
                if time.monotonic() - idle_since > args.idle_timeout:
                    worker['idle_timeout'] = True
                    break
                time.sleep(2)
                continue
            idle_since = time.monotonic()
            task_path, task = ready
            output = Path(task['output'])
            output.parent.mkdir(parents=True, exist_ok=True)
            metadata_path = Path(str(output) + '.json')
            prompt_path = Path(task['prompt_path'])
            prompt = prompt_path.read_text().strip()
            roles = task['roles']
            if len(roles) != len(task['images']) or not 0 <= len(roles) <= 10:
                raise ValueError('Invalid ordered reference roles')
            refs = [{'index': i, 'path': str(Path(p).resolve()), 'role': role, 'sha256': sha256(Path(p))}
                    for i, (p, role) in enumerate(zip(task['images'], roles), 1)]
            effective = ('Identity reference images (actual order):\n' + '\n'.join(
                f'Image {i}: {role}.' for i, role in enumerate(roles, 1)) + '\n\n' + prompt) if roles else prompt
            requested = task.get('parameters', {})
            params = dict(seed=task.get('seed', 42), width=requested.get('width', 1024),
                          height=requested.get('height', 1024), num_inference_steps=requested.get('num_inference_steps', 40),
                          output_resolution=requested.get('output_resolution', 1024), torch_dtype='bfloat16',
                          true_cfg_scale=requested.get('true_cfg_scale', 1.0), use_kv_cache=True,
                          num_images_per_prompt=1, generator_device='cuda', memory_mode='cuda', vae_tiling=False,
                          negative_prompt=task.get('negative_prompt'))
            if params['true_cfg_scale'] > 1 and params['negative_prompt'] is None:
                raise ValueError('CFG>1 requires an explicit negative prompt')
            for dim in ('width', 'height'):
                if params[dim] < 512 or params[dim] % 32:
                    raise ValueError('Image dimensions must be >=512 and multiples of32')
            fingerprint = {'worker_sha256': sha256(Path(__file__)),
                           'pipeline_sha256': sha256(Path(inspect.getfile(QwenImage21Pipeline))),
                           'diffusers_commit': git_revision('diffusers'), 'model_id': MODEL_ID, 'model_revision': MODEL_REVISION,
                           'queue_task_sha256': sha256(task_path)}
            planner_impl=dict(model_id=MODEL_ID,model_revision=MODEL_REVISION,
                              worker_sha256=fingerprint['worker_sha256'],
                              planner_sha256=sha256(ROOT/'src/healthmon/individual_evolution.py'))
            # Verify immutable completed output BEFORE loading either GPU model.
            if output.is_file():
                if not metadata_path.is_file():
                    raise RuntimeError(f'Existing output lacks provenance; preserve it and use a new run: {output}')
                old=json.loads(metadata_path.read_text())
                same=(old.get('status')=='COMPLETED' and old.get('implementation_fingerprint')==fingerprint
                      and old.get('ordered_references')==refs and old.get('parameters')==params
                      and old.get('source_prompt_sha256')==sha256(prompt_path)
                      and old.get('output',{}).get('sha256')==sha256(output))
                if task.get('design_planning'):
                    from healthmon.individual_evolution import digest
                    design_path=output.with_suffix('.design.json')
                    design=json.loads(design_path.read_text()) if design_path.is_file() else {}
                    planning_refs=[dict(path=str(Path(p)),sha256=sha256(Path(p))) for p in task.get('planning_images',[])]
                    expected=digest(dict(request=task['design_planning'],implementation=planner_impl,visual_references=planning_refs))
                    same=same and design.get('key')==expected and design.get('prompt_sha256')==digest_prompt(design.get('prompt',''))
                else:
                    same=same and old.get('prompt')==effective
                if same:
                    completed.add(task_path.name)
                    print(f'REUSE {task["case_id"]}',flush=True)
                    continue
                raise RuntimeError(f'Refusing to overwrite changed existing evaluation output: {output}')
            if metadata_path.exists():
                archive=run/'interrupted_metadata'
                archive.mkdir(exist_ok=True)
                shutil.copy2(metadata_path,archive/f'{task["case_id"]}_{time.time_ns()}.json')
            if task.get('design_planning'):
                from healthmon.individual_evolution import infer_design_brief
                worker.update(status='PLANNING',current_case=task['case_id'],last_update=stamp())
                write_json(state,worker)
                if pipe is None:
                    if not torch.cuda.is_available():raise RuntimeError('CUDA unavailable')
                    started=time.monotonic()
                    print('Loading existing Qwen pipeline for recorded language design + image inference',flush=True)
                    pipe=QwenImage21Pipeline.from_pretrained(MODEL_ID,revision=MODEL_REVISION,torch_dtype=torch.bfloat16,
                        cache_dir=str(runtime.get('qwen_cache',ROOT/'models/huggingface')),local_files_only=True).to('cuda')
                    worker['loading_seconds']=round(time.monotonic()-started,3);worker['gpu']=torch.cuda.get_device_name(0)
                try:
                    planned=infer_design_brief(pipe,task['design_planning'],output.with_suffix('.design.json'),
                        planner_impl,visual_references=task.get('planning_images',[]))
                except Exception as exc:
                    write_json(metadata_path,dict(status='FAIL',phase='DESIGN_PLANNING',error=str(exc),
                        case_id=task['case_id'],model_id=MODEL_ID,model_revision=MODEL_REVISION,
                        implementation_fingerprint=fingerprint,finished_at=stamp(),image_generated=False))
                    traceback.print_exc();completed.add(task_path.name)
                    continue
                prefix=('Ordered reference roles:\n'+'\n'.join(f'Image {j}: {role}.' for j,role in enumerate(roles,1))+'\n\n') if roles else ''
                effective=prefix+planned+'\nArt direction: ONE original iconic mythical game creature, bold simple graphic shapes and large color blocks, smooth simplified surfaces, polished cel-shaded animation design. Fantasy anatomy and immense scale are allowed. Recognizable charcoal, ivory and gold thunder lineage; amber eyes. No photorealistic fur strands or wildlife photography. Not a realistic animal with surface decoration. Deliberate coherent connected body, no random grotesque protrusions or unexplained aquatic paddles. Entire creature occupies the central 60 percent of canvas, every extremity inside frame with wide EMPTY white margins on ALL four sides. Plain white studio background, no text or diagram.'
            effective_path = output.with_suffix('.effective_prompt.txt')
            effective_path.write_text(effective + '\n')
            metadata = {'status': 'RUNNING', 'started_at': stamp(), 'case_id': task['case_id'],
                        'model_id': MODEL_ID, 'model_revision': MODEL_REVISION,
                        'implementation': 'diffusers.QwenImage21Pipeline', 'local_inference': True,
                        'ordered_references': refs, 'prompt': effective,
                        'implementation_fingerprint': fingerprint, 'source_prompt_file': str(prompt_path), 'source_prompt_sha256': sha256(prompt_path),
                        'design_planning_record': str(output.with_suffix('.design.json')) if task.get('design_planning') else None,
                        'design_planning_sha256': sha256(output.with_suffix('.design.json')) if task.get('design_planning') else None,
                        'planning_references': task.get('conditions',{}).get('planning_references',[]),
                        'effective_prompt_file': str(effective_path), 'parameters': params,
                        'evaluation_conditions': task.get('conditions', {}),
                        'versions': {'python': sys.version, 'platform': platform.platform(),
                                     'diffusers_commit': git_revision('diffusers'),
                                     'qwen_repository_commit': git_revision('Qwen-Image-2.1')},
                        'license': 'Qwen RESEARCH LICENSE AGREEMENT: noncommercial research/evaluation only',
                        'command': sys.argv, 'queue_task': str(task_path), 'visual_quality': 'REQUIRES_REVIEW'}
            write_json(metadata_path, metadata)
            worker.update(status='RUNNING', current_case=task['case_id'], last_update=stamp())
            write_json(state, worker)
            try:
                if pipe is None:
                    if not torch.cuda.is_available():
                        raise RuntimeError('CUDA unavailable')
                    print(f'Loading existing pinned {MODEL_ID} locally', flush=True)
                    started = time.monotonic()
                    pipe = QwenImage21Pipeline.from_pretrained(
                        MODEL_ID, revision=MODEL_REVISION, torch_dtype=torch.bfloat16,
                        cache_dir=str(runtime.get('qwen_cache', ROOT / 'models/huggingface')), local_files_only=True).to('cuda')
                    worker['loading_seconds'] = round(time.monotonic() - started, 3)
                    worker['gpu'] = torch.cuda.get_device_name(0)
                metadata['loading_seconds'] = worker['loading_seconds']
                metadata['versions'].update(torch=torch.__version__, cuda=torch.version.cuda,
                                            diffusers=diffusers.__version__,
                                            transformers=importlib.metadata.version('transformers'))
                metadata['scheduler'] = dict(pipe.scheduler.config)
                references = []
                for p in task['images']:
                    with Image.open(p) as im:
                        references.append(im.convert('RGBA'))
                print(f'GENERATE {task["case_id"]}: {params}', flush=True)
                torch.cuda.reset_peak_memory_stats()
                started = time.monotonic()
                step_trace = []
                def on_step(pipeline, index, timestep, callback_kwargs):
                    entry = {'step': int(index), 'timestep': float(timestep)}
                    if index in (0, params['num_inference_steps']-1):
                        sample = callback_kwargs['latents'].float()
                        entry.update(latent_shape=list(sample.shape), finite=bool(torch.isfinite(sample).all()),
                                     latent_mean=float(sample.mean()), latent_std=float(sample.std()))
                    step_trace.append(entry)
                    return callback_kwargs
                call_args = dict(prompt=effective, image=references or None,
                                 width=params['width'], height=params['height'],
                                 output_resolution=params['output_resolution'],
                                 num_inference_steps=params['num_inference_steps'],
                                 true_cfg_scale=params['true_cfg_scale'], negative_prompt=params['negative_prompt'],
                                 generator=torch.Generator('cuda').manual_seed(params['seed']),
                                 use_kv_cache=True, callback_on_step_end=on_step,
                                 callback_on_step_end_tensor_inputs=['latents'])
                metadata['actual_call_arguments'] = {k:v for k,v in call_args.items()
                    if k not in ('image','generator','callback_on_step_end')}
                metadata['actual_call_arguments']['image'] = [ref['path'] for ref in refs] or None
                metadata['actual_call_arguments']['generator'] = {'device':'cuda','seed':params['seed']}
                write_json(metadata_path, metadata)
                with torch.inference_mode():
                    result = pipe(**call_args).images[0]
                metadata['actual_steps'] = step_trace
                result.save(output)
                metadata.update(status='COMPLETED', generation_seconds=round(time.monotonic() - started, 3),
                                output={'path': str(output), 'sha256': sha256(output),
                                        'size': list(result.size), 'mode': result.mode},
                                peak_cuda_allocated_gb=torch.cuda.max_memory_allocated()/1e9)
                qc = inspect_image(output, output_report=output.with_suffix('.qc.json'),
                                   rejected_dir=run/'rejected'/task['case_id'])
                metadata['technical_image_qc'] = qc['technical_status']
                del references, result
                print(f'COMPLETED {task["case_id"]}, technicalQC {qc["technical_status"]}, semanticREVIEW_REQUIRED', flush=True)
            except Exception as exc:
                metadata.update(status='FAIL', error=str(exc), traceback=traceback.format_exc())
                traceback.print_exc()
                torch.cuda.empty_cache()
            metadata['finished_at'] = stamp()
            write_json(metadata_path, metadata)
            completed.add(task_path.name)
            idle_since = time.monotonic()
    finally:
        worker.update(status='STOPPED', finished_at=stamp(), completed=len(completed))
        write_json(state, worker)
        if pipe is not None:
            del pipe
        gpu_lock.close()
    return 0


def digest_prompt(prompt):
    import hashlib
    return hashlib.sha256(prompt.encode()).hexdigest()


if __name__ == '__main__':
    raise SystemExit(main())
