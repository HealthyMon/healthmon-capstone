#!/usr/bin/env python3
"""One selected image -> official TRELLIS.2 -> RigAnything, with verified resume."""
from pathlib import Path
import argparse, fcntl, json, os, shutil, subprocess, sys, time
from prepare_3d_input import prepare
from run_selected_3d import (ROOT, CODE_FILES, load_runtime, sha256, write_json,
    utc_now, commands_for, stage_artifacts, blender_environment)


def run(image, directory, seed=42, stage=2, form='FIT', size=512):
    image, directory = Path(image).resolve(), Path(directory).resolve()
    if not image.is_file():
        raise FileNotFoundError(image)
    config = load_runtime(ROOT / 'configs/runtime.json')
    case = dict(case_id=directory.name, image=str(image), input_sha256=sha256(image),
                seed=seed, target_stage=stage, form=form, rig=True, front_azimuth=0)
    signature = dict(case=case, runtime=config, size=size,
        code={str(p):sha256(p) for p in (*CODE_FILES, Path(__file__), ROOT/'scripts/prepare_3d_input.py', ROOT/'scripts/background_matte.py')})
    import hashlib
    fingerprint = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    state_file = directory / 'case_result.json'
    state = json.loads(state_file.read_text()) if state_file.exists() else dict(
        case=case, fingerprint=fingerprint, started_utc=utc_now(), stages={},
        visual_quality='REVIEW_REQUIRED')
    if state['fingerprint'] != fingerprint:
        raise ValueError('Existing job inputs/code changed; use a new output directory')
    state.update(status='WAITING_GPU', updated_utc=utc_now())
    write_json(state_file,state)
    (ROOT/'outputs').mkdir(parents=True,exist_ok=True)
    lock_path=ROOT/'outputs/gpu.lock'
    with lock_path.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        config_path=directory/'runtime.resolved.json'
        write_json(config_path,config)
        original=directory/('original_input'+image.suffix.lower())
        if not original.exists(): shutil.copyfile(image,original)
        if sha256(original) != case['input_sha256']: raise ValueError('Original input hash mismatch')
        selected=directory/('selected_input'+image.suffix.lower())
        if not selected.exists():
            subprocess.run([str(config.get('qwen_python',sys.executable)), '-c',
                'from prepare_3d_input import prepare; import sys; prepare(sys.argv[1],sys.argv[2])',
                str(original),str(selected)],env={**os.environ,'PYTHONPATH':str(ROOT/'scripts')},check=True)
        matte=json.loads(selected.with_suffix('.matte.json').read_text())
        if sha256(selected)!=matte['output_sha256'] or matte['input_sha256']!=case['input_sha256']:
            raise ValueError('Prepared matte hash mismatch')
        commands=commands_for(case,directory,config_path,config,size)
        state.update(status='RUNNING',updated_utc=utc_now())
        write_json(state_file,state)
        current=None
        try:
            for name,command in commands.items():
                current=name
                old=state['stages'].get(name,{})
                records=old.get('artifacts',[])
                if old.get('status')=='PASS' and records and all(Path(a['path']).is_file() and sha256(a['path'])==a['sha256'] for a in records):
                    print(f'{name}: verified existing artifacts',flush=True)
                    continue
                entry=dict(status='RUNNING',started_utc=utc_now(),argv=command)
                state['stages'][name]=entry
                state.update(current_stage=name,updated_utc=utc_now())
                write_json(state_file,state)
                log=directory/f'logs/{name}.log'
                log.parent.mkdir(parents=True,exist_ok=True)
                record=dict(argv=command,cwd=str(ROOT),started_utc=utc_now())
                write_json(log.with_suffix('.command.json'),record)
                env=os.environ.copy()
                env.update(PYTHONUNBUFFERED='1',PYTHONPATH=str(ROOT/'src'))
                if name in ('validate_unrigged','render_unrigged'):
                    env=blender_environment(config['blender'],extra=config.get('blender_environment'))
                start=time.monotonic()
                print(f'{name}: {log}',flush=True)
                with log.open('w') as stream:
                    result=subprocess.run(command,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
                record.update(returncode=result.returncode,duration_seconds=time.monotonic()-start,finished_utc=utc_now())
                write_json(log.with_suffix('.command.json'),record)
                entry.update(record)
                if result.returncode: raise RuntimeError(f'{name} exited {result.returncode}; {log}')
                entry.update(status='PASS',artifacts=stage_artifacts(name,directory))
                write_json(state_file,state)
            state.update(status='PASS',current_stage='complete',finished_utc=utc_now())
        except BaseException as e:
            state.update(status='INTERRUPTED' if isinstance(e,KeyboardInterrupt) else 'FAIL',error=str(e),finished_utc=utc_now())
            if current: state['stages'][current].update(status=state['status'],error=str(e))
            raise
        finally:
            write_json(state_file,state)
    return state

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image',required=True,type=Path)
    p.add_argument('--output-dir',required=True,type=Path)
    p.add_argument('--seed',type=int,default=42)
    p.add_argument('--stage',type=int,choices=(0,1,2,3),default=2)
    p.add_argument('--form',default='FIT')
    p.add_argument('--size',type=int,default=512)
    a=p.parse_args()
    run(a.image,a.output_dir,a.seed,a.stage,a.form,a.size)
