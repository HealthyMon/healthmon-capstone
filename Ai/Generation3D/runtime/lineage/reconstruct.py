"""Reconstruct only a directly reviewed final descendant with the existing pipeline."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser()
parser.add_argument('--run-dir',type=Path,required=True)
parser.add_argument('--branch',choices=['balanced','athletic','high_reserve'],required=True)
args=parser.parse_args();run=args.run_dir.resolve()
assert run.is_relative_to(ROOT/'outputs')
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
review=read(run/'stage_3_visual_review.json')
folder=run/f'branches/{args.branch}/stage_3';image=folder/'image.png'
metadata=read(folder/'image.png.json')
assert review['status']=='ACCEPTED' and review['cases'][args.branch]['sha256']==sha(image)
assert metadata['status']=='PASS' and metadata['output']['sha256']==sha(image)
assert read(folder/'image_qc.json')['technical_status']=='PASS'
assert read(folder/'compiled.json')['transition']['target_stage']==3
subprocess.run([sys.executable,str(ROOT/'runtime/phased/configure_gpu_runtime.py')],check=True)
form={'balanced':'BALANCED','athletic':'FIT','high_reserve':'HEAVY'}[args.branch]
subprocess.run([sys.executable,str(ROOT/'runtime/lineage/run_image_to_rigged.py'),'--image',str(image),
    '--output-dir',str(folder/'reconstruction'),'--stage','3','--form',form,
    '--seed','42','--size','512'],cwd=ROOT,check=True)
