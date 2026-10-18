import json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ['PYTHONUTF8']='1'
smoke=[json.loads(line) for line in (ROOT/'runs/smoke-20260929/metrics.jsonl').read_text().splitlines()]
assert smoke[-1]['event']=='complete','Smoke must complete first'
commands=[['scripts/evaluate_model.py','--output','runs/baseline-validation.json'],
          ['scripts/train_lora.py','--run','pilot-20260929','--epochs','3']]
for command in commands:
    print('RUN',command,flush=True)
    subprocess.run([sys.executable,'-u',*command],cwd=ROOT,check=True)
selection=json.loads((ROOT/'runs/pilot-20260929/selection.json').read_text())
adapter=selection['selected']['checkpoint']
subprocess.run([sys.executable,'-u','scripts/evaluate_model.py','--output','runs/lora-validation.json','--adapter',adapter],cwd=ROOT,check=True)
print('PIPELINE COMPLETE',flush=True)
