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
from prepare_numeric_evolution import ROOT, prepare_profiles


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profiles',type=Path,required=True)
    parser.add_argument('--run-dir',type=Path)
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args()
    profiles=args.profiles.resolve()
    digest=hashlib.sha256(profiles.read_bytes())
    for code in ('src/healthmon/numeric_evolution.py','src/healthmon/branch_evolution.py',
                 'src/healthmon/prompts.py','src/healthmon/design_contract.py','src/healthmon/numeric_source_guard.py',
                 'src/healthmon/numeric_router.py','src/healthmon/biped_evolution.py',
                 'scripts/prepare_numeric_evolution.py',
                 'scripts/qwen_branch_worker.py','src/healthmon/qwen_runner.py',
                 'configs/evolution_art_direction.json',
                 'vendor/diffusers/src/diffusers/pipelines/qwenimage21/pipeline_qwenimage21.py'):
        digest.update((ROOT/code).read_bytes())
    profile_rows=json.loads(profiles.read_text())['profiles']
    from healthmon.numeric_evolution import IDENTITIES
    from healthmon.biped_evolution import load_biped_species
    for species in sorted({item['species'] for item in profile_rows}):
        if species not in IDENTITIES:
            _,species_config=load_biped_species(species)
            digest.update(species_config.read_bytes())
    for item in profile_rows:
        parent=ROOT/item['previous_image']
        digest.update(parent.read_bytes())
        digest.update(Path(str(parent)+'.json').read_bytes())
    run=(args.run_dir or ROOT/'outputs'/('numeric_auto_'+digest.hexdigest()[:16])).resolve()
    if (run/'STOP').exists():
        raise SystemExit(f'Run was intentionally stopped: {run}. Use a new run directory to resume explicitly.')
    summary=prepare_profiles(profiles,run)
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    if args.prepare_only or summary['prepared']==0:
        return 0
    python=ROOT/'.venvs/qwen/bin/python'
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
