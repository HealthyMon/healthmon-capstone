import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.contracts import ModelOutput
from src.agent import validate
from src.prompts import messages
from transformers import AutoTokenizer
folder=ROOT/'data/pilot_v2';manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
tok=AutoTokenizer.from_pretrained(ROOT/'models/qwen3.5-9b',local_files_only=True)
groups={};ids=set();maximum=0
for split in ['train','validation']:
    path=folder/(split+'.jsonl');assert hashlib.sha256(path.read_bytes()).hexdigest()==manifest['sha256'][path.name]
    for line in path.read_text(encoding='utf-8').splitlines():
        row=json.loads(line);assert row['sample_id'] not in ids;ids.add(row['sample_id'])
        assert groups.setdefault(row['scenario_group'],split)==split
        validate(json.dumps(row['answer'],ensure_ascii=False),row['context'],row['user_text'])
        prefix=tok.apply_chat_template(messages(row['context'],row['user_text']),tokenize=True,enable_thinking=False,add_generation_prompt=True,return_dict=False)
        length=len(prefix)+len(tok.encode(json.dumps(row['answer'],ensure_ascii=False,separators=(',',':'))+'<|im_end|>',add_special_tokens=False))
        assert length==row['token_count'] and length<=1024;maximum=max(maximum,length)
print(json.dumps({'passed':True,'samples':len(ids),'max_tokens':maximum,'truncated':0,'split_leakage':False}))
