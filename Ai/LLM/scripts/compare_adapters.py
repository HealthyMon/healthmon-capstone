"""Paired current-runtime validation, reset RNG immediately before EVERY example."""
import json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.pop('ADAPTER_PATH',None)
from src.model import QwenBackend
from src.agent import validate
from peft import PeftModel
import torch
backend=QwenBackend(runtime_guidance=True);backend.load()
rows=[json.loads(s) for s in (ROOT/'data/pilot_v2/validation.jsonl').read_text(encoding='utf-8').splitlines()]
reports=[]
for epoch in [0,1,2,3]:
    if epoch:
        path=ROOT/f'runs/pilot-20260929/checkpoint-epoch-{epoch}'
        if epoch==1:backend.model=PeftModel.from_pretrained(backend.model,path,adapter_name='epoch1')
        else:backend.model.load_adapter(path,adapter_name=f'epoch{epoch}')
        backend.model.set_adapter(f'epoch{epoch}');backend.model.eval()
    results=[]
    for i,row in enumerate(rows):
        torch.manual_seed(123+i)
        start=time.monotonic();raw=backend.generate(row['context'],row['user_text']);syntax=True;valid=True;error=None
        try:json.loads(raw)
        except ValueError:syntax=False
        try:validate(raw,row['context'],row['user_text'])
        except ValueError as e:valid=False;error=str(e)
        item={'group':row['scenario_group'],'input':row['user_text'],'raw':raw,'json_parse':syntax,
              'contract_valid':valid,'error':error,'latency_seconds':time.monotonic()-start}
        results.append(item);print(json.dumps({'epoch':epoch,**item},ensure_ascii=False),flush=True)
    reports.append({'epoch':epoch,'results':results,'json_parse':sum(r['json_parse'] for r in results),
                    'contract_valid':sum(r['contract_valid'] for r in results),'count':len(rows)})
    (ROOT/'runs/paired-validation.json').write_text(json.dumps({'runtime_guidance':True,'seed_per_example':'123 + index, reset after model load',
        'same_context_and_generation':True,'frozen_test':False,'human_review':False,'models':reports},ensure_ascii=False,indent=2),encoding='utf-8')
print('PAIRED_COMPARISON_COMPLETE',flush=True)

# Memory ablation is separate from adapter comparison and uses synthetic facts.
import copy
from src.rules import RULES
base={'settings':{'name':'몽글이','speech_level':'casual','profanity':'mild'},'traits':copy.deepcopy(RULES['initial']),
      'mood':{'valence':0,'energy':50},'recent':[],'memories':[],'activities':[],'candidates':[],'active_quests':[]}
ablation=[]
cases=[('나는 달리기보다 걷는 게 좋아.','내가 좋아하는 운동 기억해?','preference'),
       ('내 목표는 이번 주 산책을 세 번 하는 거야.','이번 주 내 목표 기억해?','goal'),
       ('어제 처음으로 공원 한 바퀴를 걸어서 뿌듯했어.','어제 왜 뿌듯했는지 기억해?','experience')]
for i,(fact,query,slot) in enumerate(cases):
    for use_memory in [False,True]:
        context=copy.deepcopy(base)
        if use_memory:context['memories']=[{'id':f'synthetic-{i}','content':fact,'source_id':f'message:synthetic-{i}','source_revision':1,'slot':slot,'score':0.9}]
        torch.manual_seed(700+i)
        raw=backend.generate(context,query)
        ablation.append({'query':query,'with_memory':use_memory,'synthetic_fact':fact,'raw':raw})
        print(json.dumps({'ablation':ablation[-1]},ensure_ascii=False),flush=True)
(ROOT/'runs/memory-ablation.json').write_text(json.dumps({'adapter_epoch':3,'same_seed_and_prompt_except_memory':True,'cases':ablation,'human_review':False},ensure_ascii=False,indent=2),encoding='utf-8')
