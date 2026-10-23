#!/usr/bin/env python3
"""One command: numeric scores -> milestone decision -> local Qwen images.

Changed inputs/implementation create a new run, preserving prior evidence.
A successful inference is never committed as a visually accepted lineage here.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from prepare_numeric_evolution import ROOT, prepare_profiles, prepare_individual_profiles
from run_selected_3d import load_runtime


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profiles',type=Path,required=True)
    parser.add_argument('--run-dir',type=Path)
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--version',choices=('v1','v2','legacy'),default='v2',help='v1: preserved fixed assets; v2: individual inference; legacy: old 25-level experiments')
    args=parser.parse_args()
    profiles=args.profiles.resolve()
    if args.version=='v1':
        from healthmon.individual_evolution import stage_for_level
        document=json.loads(profiles.read_text()); rows=[]
        for p in document['profiles']:
            stage=stage_for_level(p['level']); stats=p['stats']
            history=p.get('history',[])
            days=sum(r['days'] for r in history)
            form='starter' if stage==0 else ('heavy' if stats['Activity']<25 and stats['EnergyBalance']>.2 and days>=14 else 'healthy')
            image=ROOT/f"web/fixed/assets/{p['species']}/s{stage}_{form}.png"
            rows.append(dict(case_id=p['case_id'],version='v1',image=str(image),sha256=hashlib.sha256(image.read_bytes()).hexdigest(),inference=False))
        run=(args.run_dir or ROOT/'outputs/v1_lookup').resolve();run.mkdir(parents=True,exist_ok=True)
        (run/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(rows,ensure_ascii=False));return 0
    digest=hashlib.sha256(profiles.read_bytes())
    code_files=('src/healthmon/individual_evolution.py','scripts/prepare_numeric_evolution.py','scripts/qwen_branch_worker.py') if args.version=='v2' else ('src/healthmon/numeric_evolution.py','src/healthmon/branch_evolution.py','scripts/prepare_numeric_evolution.py','scripts/qwen_branch_worker.py')
    for code in code_files: digest.update((ROOT/code).read_bytes())
    run=(args.run_dir or ROOT/'outputs'/f"{args.version}_{digest.hexdigest()[:16]}").resolve()
    if (run/'STOP').exists():
        raise SystemExit(f'Run was intentionally stopped: {run}. Use a new run directory to resume explicitly.')
    summary=(prepare_individual_profiles if args.version=='v2' else prepare_profiles)(profiles,run)
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    if args.prepare_only or summary['prepared']==0:
        return 0
    python=load_runtime(ROOT/'configs/runtime.json')['qwen_python']
    code=subprocess.call([str(python),str(ROOT/'scripts/qwen_branch_worker.py'),
                          '--run-dir',str(run),'--idle-timeout','0'],cwd=ROOT)
    if code:return code
    failed=[];completed=[]
    for queue_path in sorted((run/'queue').glob('*.json')):
        task=json.loads(queue_path.read_text())
        output=Path(task['output']);metadata=Path(str(output)+'.json')
        if not output.is_file() or not metadata.is_file():
            failed.append(task['case_id']);continue
        record=json.loads(metadata.read_text())
        if record.get('status')!='COMPLETED' or record['output']['sha256']!=hashlib.sha256(output.read_bytes()).hexdigest():
            failed.append(task['case_id'])
        else:completed.append(task['case_id'])
    print(json.dumps({'actual_completed':completed,'failed_or_missing':failed,
        'visual_quality':'REQUIRES_REVIEW','automatically_committed_lineages':0},ensure_ascii=False),flush=True)
    return 2 if failed else 0

if __name__=='__main__':
    raise SystemExit(main())
