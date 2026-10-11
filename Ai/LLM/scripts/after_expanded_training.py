"""Wait for this run only, then compare two validation-loss candidates; no final-test selection."""
import json,sys,time,subprocess
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parents[1]
run=ROOT/'runs/expanded-20260929'
pid=int((run/'pid').read_text())
try:
 p=psutil.Process(pid)
 assert Path(p.cwd()).resolve()==ROOT and 'scripts/train_lora.py' in ' '.join(p.cmdline())
 while p.is_running():
  try:p.wait(timeout=30)
  except psutil.TimeoutExpired:pass
except psutil.NoSuchProcess:pass
events=[json.loads(l) for l in (run/'metrics.jsonl').read_text().splitlines()]
if events[-1]['event']!='complete':raise RuntimeError('Training did not complete; preserve failure logs')
subprocess.run([sys.executable,'-u','scripts/rescore_validation_loss.py'],cwd=ROOT,check=True)
candidates=sorted(json.loads((ROOT/'runs/improvement-20260929/clean-validation-loss.json').read_text())['results'],key=lambda r:r['loss'])[:2]
selection_cases=json.loads((ROOT/'data/improvement_v1/validation-cases.json').read_text(encoding='utf-8'))
outcases=ROOT/'data/improvement_v2/checkpoint-selection-cases.json'
if outcases.exists():raise RuntimeError('Existing selection cases')
selection_cases['selection_policy']='First 16 curated validation cases, fixed before viewing candidate outputs; NLL uses all 44 validation examples.'
outcases.write_text(json.dumps(selection_cases,ensure_ascii=False,indent=2),encoding='utf-8')
cmd=[sys.executable,'-u','scripts/evaluate_improvement.py','--cases',str(outcases.relative_to(ROOT)),
 '--output','runs/improvement-20260929/checkpoint-dialogue.json','--adapters']+[r['checkpoint'] for r in candidates]
print('Comparing validation candidates',[(r['epoch'],r['loss']) for r in candidates],flush=True)
subprocess.run(cmd,cwd=ROOT,check=True)
print('VALIDATION_REVIEW_READY',flush=True)
