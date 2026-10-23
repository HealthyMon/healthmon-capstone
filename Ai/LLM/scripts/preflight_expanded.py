"""Only training-invalidating checks: masking, inputs, split membership/leakage."""
import json,hashlib,sys,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from transformers import AutoTokenizer
from src.prompts import messages
D=ROOT/'data/improvement_v2'
tok=AutoTokenizer.from_pretrained(ROOT/'models/qwen3.5-9b',local_files_only=True)
data={s:[json.loads(l) for l in (D/(s+'.jsonl')).read_text(encoding='utf-8').splitlines()] for s in ['train','validation']}
groups={};keys={};report=[]
for split,rows in data.items():
 for r in rows:
  assert groups.setdefault(r['scenario_group'],split)==split
  c=r['context'];assert all(k in c for k in ['settings','traits','mood','memories','recent','candidates','active_quests'])
  assert all(k in c['traits'] for k in ['courtesy','bluntness','roughness','playfulness','bond','initiative','sociability'])
  msgs=messages(c,r['user_text']);parsed=json.loads(msgs[1]['content'])
  assert parsed['context']==c
  prefix=tok.apply_chat_template(msgs,tokenize=True,add_generation_prompt=True,enable_thinking=False,return_dict=False)
  answer=json.dumps(r['answer'],ensure_ascii=False,separators=(',',':'))+'<|im_end|>'
  target=tok.encode(answer,add_special_tokens=False);labels=[-100]*len(prefix)+target
  assert tok.decode([t for t in labels if t!=-100])==answer
  assert all(t==-100 for t in labels[:len(prefix)]) and len(labels)<=1024
  key=json.dumps([c,r['user_text']],sort_keys=True,ensure_ascii=False)
  assert keys.setdefault(key,split)==split
  report.append({'sample_id':r['sample_id'],'split':split,'prompt_tokens_masked':len(prefix),'target_tokens':len(target),'total_tokens':len(labels),'all_context_fields_present':True})
final=json.loads((D/'final-frozen.json').read_text(encoding='utf-8'))
assert hashlib.sha256((D/'final-frozen.json').read_bytes()).hexdigest()==json.loads((D/'final-freeze.json').read_text())['sha256']
for c in final['cases']:
 assert json.dumps([c['context'],c['user_text']],sort_keys=True,ensure_ascii=False) not in keys
result={'masking_pass':True,'input_pass':True,'group_split_pass':True,'exact_context_query_cross_split_duplicates':0,
 'semantic_split_review':'Codex reviewed concrete event/source families; broad task types deliberately recur. No human review.',
 'counts':{s:len(r) for s,r in data.items()},'final_count':len(final['cases']),'rows':report}
(ROOT/'runs/improvement-20260929/training-preflight.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False))
