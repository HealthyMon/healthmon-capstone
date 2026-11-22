"""Rebuild all five lost LoRA stages sequentially without overwriting old runs."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[1]
OUT=ROOT/'runs/recovery-20261121'
STAGES=[('candidate','qwen4b_candidate_v1',1,5e-5),
        ('common','qwen4b_common_v2',2,5e-5),
        ('natural','qwen4b_natural_v1',2,3e-5),
        ('healthmon-sft','healthmon_sft_v1',2,4e-5),
        ('axis-priority','qwen4b_axis_priority_v1',2,6e-5)]

def main():
    OUT.mkdir(parents=True,exist_ok=False)
    state={'pid':os.getpid(),'started':time.time(),'status':'training','stages':[],
           'scope':'new training from recovered data; not bit-identical recovery',
           'validation_policy':'defer validation to final stage; no intermediate response comparisons'}
    def save():
        temp=OUT/'status.tmp'
        temp.write_text(json.dumps(state,indent=2),encoding='utf-8')
        temp.replace(OUT/'status.json')
    adapter=None
    try:
        for name,data,epochs,lr in STAGES:
            run=OUT/name
            state['current_stage']=name;save()
            cmd=[sys.executable,'-X','utf8','-B',str(ROOT/'scripts/train_qwen4b.py'),
                 '--data',str(ROOT/'data'/data),'--run',str(run),'--epochs',str(epochs),'--lr',str(lr),
                 '--final-only-validation' if name=='axis-priority' else '--skip-validation']
            if adapter:cmd+=['--init-adapter',str(adapter)]
            with (OUT/(name+'.stdout.log')).open('w',encoding='utf-8') as log, (OUT/(name+'.stderr.log')).open('w',encoding='utf-8') as err:
                subprocess.run(cmd,cwd=REPO,stdout=log,stderr=err,check=True)
            selection=json.loads((run/'selection.json').read_text())
            if not selection.get('trained'):raise RuntimeError('Incomplete stage '+name)
            adapter=Path(selection['selected']['path'])
            state['stages'].append({'name':name,'adapter':str(adapter),'epochs':epochs,'lr':lr});save()
        state['status']='evaluating';save()
        with (OUT/'evaluation.log').open('w',encoding='utf-8') as log:
            subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'scripts/evaluate_healthmon_sft.py'),
                            '--worker','--adapter',str(adapter),'--output',str(OUT/'final-evaluation.json')],
                           cwd=REPO,stdout=log,stderr=log,check=True)
        state['status']='awaiting_semantic_review';state['completed']=time.time();save()
    except Exception as exc:
        state.update(status='failed',error=str(exc));save();raise

if __name__=='__main__':main()
