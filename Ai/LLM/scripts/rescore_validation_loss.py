import json,os,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ.pop('ADAPTER_PATH',None)
import torch
from peft import PeftModel
from src.model import QwenBackend
from src.prompts import messages
b=QwenBackend();b.load();b.model.config.use_cache=False
rows=[json.loads(l) for l in (ROOT/'data/improvement_v3/validation.jsonl').read_text(encoding='utf-8').splitlines()]
batches=[]
for r in rows:
 prefix=b.tokenizer.apply_chat_template(messages(r['context'],r['user_text']),tokenize=True,enable_thinking=False,add_generation_prompt=True,return_dict=False)
 target=b.tokenizer.encode(json.dumps(r['answer'],ensure_ascii=False,separators=(',',':'))+'<|im_end|>',add_special_tokens=False)
 batches.append({'input_ids':torch.tensor([prefix+target],device='cuda'),'labels':torch.tensor([[-100]*len(prefix)+target],device='cuda')})
events=[json.loads(l) for l in (ROOT/'runs/expanded-20260929/metrics.jsonl').read_text().splitlines()]
result=[]
for r in [e for e in events if e['event']=='validation']:
 name='e'+str(r['epoch'])
 if not isinstance(b.model,PeftModel):b.model=PeftModel.from_pretrained(b.model,r['checkpoint'],adapter_name=name)
 else:b.model.load_adapter(r['checkpoint'],adapter_name=name)
 b.model.set_adapter(name);b.model.eval();losses=[]
 with torch.no_grad():
  for batch in batches:
   loss=b.model(**batch,use_cache=False).loss;losses.append(float(loss));del loss;torch.cuda.empty_cache()
 result.append({'epoch':r['epoch'],'checkpoint':r['checkpoint'],'loss':sum(losses)/len(losses),'count':len(rows)})
 print(json.dumps(result[-1]),flush=True)
(ROOT/'runs/improvement-20260929/clean-validation-loss.json').write_text(json.dumps({'data_sha256':hashlib.sha256((ROOT/'data/improvement_v3/validation.jsonl').read_bytes()).hexdigest(),'results':result},indent=2),encoding='utf-8')
