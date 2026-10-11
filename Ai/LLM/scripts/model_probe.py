import json, os, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from filelock import FileLock
gpu_lease=FileLock(str(ROOT/'runtime/gpu.lock'),timeout=0)
gpu_lease.acquire()
os.environ['HF_HUB_OFFLINE']='1'
import torch
from transformers import AutoTokenizer, Qwen3_5ForConditionalGeneration
path=ROOT/'models/qwen3.5-9b'
print('load start',time.time(),flush=True)
tok=AutoTokenizer.from_pretrained(path)
model=Qwen3_5ForConditionalGeneration.from_pretrained(path,dtype=torch.bfloat16,device_map='cuda:0',attn_implementation='sdpa')
print('loaded',torch.cuda.memory_allocated()/2**30,flush=True)
mods=[n for n,m in model.named_modules() if isinstance(m,torch.nn.Linear)]
(ROOT/'runs/model_linear_modules.json').write_text(json.dumps(mods,indent=2))
from src.prompts import messages
from src.rules import RULES
context={'settings':{'name':'몽글이','speech_level':'casual','profanity':'mild'},'traits':RULES['initial'],'mood':{'valence':0,'energy':50},'memories':[],'candidates':[],'recent':[],'activities':[]}
inputs=tok.apply_chat_template(messages(context,'안녕, 너는 누구야?'),tokenize=True,add_generation_prompt=True,enable_thinking=False,return_tensors='pt',return_dict=True).to(model.device)
start=time.time()
with torch.inference_mode():
    out=model.generate(**inputs,max_new_tokens=220,do_sample=False)
raw=tok.decode(out[0,inputs['input_ids'].shape[1]:],skip_special_tokens=True)
report={'raw':raw,'seconds':time.time()-start,'input_tokens':inputs['input_ids'].shape[1],
        'peak_allocated_gib':torch.cuda.max_memory_allocated()/2**30,'peak_reserved_gib':torch.cuda.max_memory_reserved()/2**30}
(ROOT/'runs/base_probe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False),flush=True)
