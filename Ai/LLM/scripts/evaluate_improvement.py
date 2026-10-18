"""Sequential GPU comparisons. Raw attempts recorded only for authored test cases."""
import argparse,contextlib,hashlib,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--cases',required=True);p.add_argument('--output',required=True)
p.add_argument('--stack',choices=['legacy','current'],default='current');p.add_argument('--adapters',nargs='+',default=['base','runs/pilot-20260929/checkpoint-epoch-3']);args=p.parse_args()
out=ROOT/args.output
if out.exists():raise RuntimeError('Output exists; choose new path')
sys.path.insert(0,str(ROOT/'runs/improvement-20260929/original' if args.stack=='legacy' else ROOT))
os.environ.pop('ADAPTER_PATH',None);os.environ['MODEL_PATH']=str(ROOT/'models/qwen3.5-9b')
from src.model import QwenBackend
from src.agent import respond
from src import db
# Snapshot code's db ROOT points into the preserved tree. Use the real GPU lock and model.
import src.model as mm
mm.ROOT=ROOT
from peft import PeftModel
import torch
casepath=ROOT/args.cases;payload=json.loads(casepath.read_text(encoding='utf-8'));cases=payload['cases']
b=QwenBackend();b.load();real_generate=b.generate;trace=[]
def traced(context,text,repair=None):
 start=time.monotonic()
 try:
  raw=real_generate(context,text,repair);trace.append({'raw':raw,'repair_input':repair,'latency_seconds':time.monotonic()-start});return raw
 except Exception as e:
  trace.append({'exception':type(e).__name__,'latency_seconds':time.monotonic()-start});raise
b.generate=traced
report={'stack':args.stack,'case_file':args.cases,'case_sha256':hashlib.sha256(casepath.read_bytes()).hexdigest(),
 'seed':'9100 + case index; reset after model/adapter load','generation':{'max_new_tokens':240,'temperature':0.7,'top_p':0.9,'repetition_penalty':1.05},
 'source_sha256':{n:hashlib.sha256(Path(mm.__file__).with_name(n+'.py').read_bytes()).hexdigest() for n in ['model','agent','prompts']},
 'human_review':False,'models':[]}
for index,adapter in enumerate(args.adapters):
 if adapter!='base':
  if not isinstance(b.model,PeftModel):b.model=PeftModel.from_pretrained(b.model,ROOT/adapter,adapter_name=f'a{index}')
  else:b.model.load_adapter(ROOT/adapter,adapter_name=f'a{index}')
  b.model.set_adapter(f'a{index}');b.model.eval()
 results=[];entry={'adapter':adapter,'results':results};report['models'].append(entry)
 scope=b.model.disable_adapter() if adapter=='base' and isinstance(b.model,PeftModel) else contextlib.nullcontext()
 with scope:
  for i,c in enumerate(cases):
   trace.clear();torch.manual_seed(9100+i)
   final,metrics=respond(b,c['context'],c['user_text'])
   row={'id':c['id'],'input':c['user_text'],'context':c['context'],'expect':c['expect'],'attempts':list(trace),'final':final.model_dump(),'metrics':metrics}
   results.append(row);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
   print(json.dumps({'adapter':adapter,'case':c['id'],'speech':final.speech,'fallback':metrics['fallback']},ensure_ascii=False),flush=True)
print('COMPLETE',flush=True)
