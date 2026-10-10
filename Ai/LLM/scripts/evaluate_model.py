"""Identical held-out validation contexts; raw/final validity kept distinct."""
import argparse,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.model import QwenBackend
from src.agent import validate
import torch
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--adapter');p.add_argument('--runtime-guidance',action='store_true');args=p.parse_args()
if args.adapter:os.environ['ADAPTER_PATH']=args.adapter
else:os.environ.pop('ADAPTER_PATH',None)
torch.manual_seed(123)
backend=QwenBackend(runtime_guidance=args.runtime_guidance);backend.load()
rows=[json.loads(s) for s in (ROOT/'data/pilot_v2/validation.jsonl').read_text(encoding='utf-8').splitlines()]
results=[]
for index,row in enumerate(rows):
    torch.manual_seed(123+index)
    start=time.monotonic();raw=backend.generate(row['context'],row['user_text']);valid=True;error=None
    try:out=validate(raw,row['context'],row['user_text'])
    except Exception as e:valid=False;error=str(e)
    result={'sample_id':row['sample_id'],'scenario_group':row['scenario_group'],'input':row['user_text'],'raw':raw,
            'raw_valid':valid,'error':error,'latency_seconds':time.monotonic()-start}
    results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
report={'backend':backend.name,'adapter':args.adapter,'split':'validation (development exposed, NOT frozen test)',
        'generation':{'seed':123,'temperature':0.7,'top_p':0.9,'max_new_tokens':240,'runtime_guidance':args.runtime_guidance},'raw_contract_valid':sum(r['raw_valid'] for r in results),
        'count':len(results),'peak_allocated_gib':torch.cuda.max_memory_allocated()/2**30,
        'results':results,'human_review':False,'semantic_pass_rate':None}
(ROOT/args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
