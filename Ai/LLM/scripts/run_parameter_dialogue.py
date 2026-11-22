"""Train parameter-conditioned dialogue and evaluate separate test topics once."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1]
DATA=ROOT/'data/parameter_dialogue_20261121'
OUT=ROOT/'runs/parameter-dialogue-20261121'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--evaluate',action='store_true');args=parser.parse_args()
    if args.evaluate:
        import evaluate_healthmon_sft as evaluator
        rows=[json.loads(l) for l in (DATA/'test.jsonl').read_text(encoding='utf-8').splitlines()]
        evaluator.fixtures=lambda:[dict(id=r['sample_id'],text=r['user_text'],context=r['context'],reference=r['answer'],group=r['scenario_group']) for r in rows]
        selection=json.loads((OUT/'training/selection.json').read_text())
        return evaluator.worker(Path(selection['selected']['path']),OUT/'final-evaluation.json')
    OUT.mkdir(parents=True,exist_ok=False)
    state={'status':'training','pid':os.getpid(),'started':time.time(),'data':str(DATA),'server_promoted':False}
    def save():
        p=OUT/'status.tmp';p.write_text(json.dumps(state,indent=2),encoding='utf-8');p.replace(OUT/'status.json')
    save()
    try:
        with (OUT/'training.stdout.log').open('w',encoding='utf-8') as log,(OUT/'training.stderr.log').open('w',encoding='utf-8') as err:
            subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'scripts/train_qwen4b.py'),
                '--data',str(DATA),'--run',str(OUT/'training'),'--init-adapter',str(ROOT/'runs/balanced-repair-20261121/training/checkpoint-epoch-2'),
                '--epochs','2','--lr','0.00002','--final-only-validation'],cwd=REPO,stdout=log,stderr=err,check=True)
        state['status']='evaluating';save()
        with (OUT/'evaluation.log').open('w',encoding='utf-8') as log:
            subprocess.run([sys.executable,'-X','utf8','-B',__file__,'--evaluate'],cwd=REPO,stdout=log,stderr=log,check=True)
        state.update(status='awaiting_semantic_review',completed=time.time());save()
    except Exception as exc:
        state.update(status='failed',error=str(exc));save();raise

if __name__=='__main__':main()
