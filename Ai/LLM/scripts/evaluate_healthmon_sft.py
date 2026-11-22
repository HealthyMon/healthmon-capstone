"""Final before/after batch using deployed fast inference and held-out contexts.

Loads candidates for offline evaluation only; never publishes a ready manifest
or opens a server before the results are reviewed.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(REPO))
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false',
                  TRITON_CACHE_DIR=str(REPO/'.runtime/qwen4b-live/cache/triton'))

def fixtures():
    from scripts.prepare_qwen4b_common import make
    from scripts.evaluate_qwen4b_common import fixtures as memory_cases
    rows=[]
    validation=ROOT/'data/healthmon_sft_v1/validation.jsonl'
    for line in validation.read_text(encoding='utf-8').splitlines():
        row=json.loads(line)
        rows.append({'id':row['sample_id'],'group':'source_holdout','text':row['user_text'],
                     'context':row['context'],'reference':row['answer']})
    for scenario,(text,level) in enumerate([
        ('새로운 보드게임을 해 봤어.','casual'),
        ('오늘은 잠깐 한가해서 들렀어요.','formal'),
    ]):
        for axis in ('activity','affinity','initiative'):
            for value in (10,90):
                row=make('eval-only',text,'평가용 정답 없음.',axes={axis:value})
                row['context']['settings']['speech_level']=level
                rows.append({'id':f'axis-{scenario}-{axis}-{value}','group':'paired_axis','axis':axis,'score':value,
                             'scenario':scenario,'text':text,'context':row['context']})
    for activity,initiative in [(10,10),(10,90),(90,10),(90,90)]:
        row=make('cross-only','오늘 새로 나온 만화를 읽었어.','평가용 정답 없음.',axes={'activity':activity,'initiative':initiative})
        rows.append({'id':f'cross-{activity}-{initiative}','group':'cross_axis','text':row['user_text'],'context':row['context']})
    for case in memory_cases():
        if case['id'] in ('memory-revision','memory-number','rest-high'):
            rows.append(dict(case,group='regression'))
    return rows

def load_candidate(adapter,runtime):
    import torch
    from transformers import AutoTokenizer,Qwen3_5ForConditionalGeneration
    from transformers.models.qwen3_5 import modeling_qwen3_5 as kernels
    from peft import PeftModel
    from src.qwen_loading import loading_kwargs,verify_adapter_base
    from Server.local_probe.checkpoint_loading import load_pretrained
    from Server.local_probe.gpu_gateway import LocalModels,adapter_activation_audit
    base=ROOT/'models/qwen3.5-4b';verify_adapter_base(base,adapter)
    assert kernels.chunk_gated_delta_rule is not None and kernels.fused_recurrent_gated_delta_rule is not None
    torch.set_num_threads(1)
    model=load_pretrained(Qwen3_5ForConditionalGeneration,base,**loading_kwargs('nf4'))
    model.model.visual=torch.nn.Identity()
    model.dequantize(dtype=torch.bfloat16)
    torch.cuda.empty_cache()
    model=PeftModel.from_pretrained(model,adapter,adapter_name='evaluation',is_trainable=False)
    audit=adapter_activation_audit(model,expected='evaluation')
    assert audit['verified_expected_adapter_active']
    model=model.merge_and_unload(safe_merge=True,adapter_names=['evaluation']).to(dtype=torch.bfloat16).eval()
    torch.cuda.empty_cache()
    runtime.mkdir(parents=True,exist_ok=True)
    wrapper=LocalModels({'full_personality_facts':True,'release_cuda_cache_after_request':False,
                         'quality_refinement':False},runtime)
    wrapper.model=model;wrapper.tokenizer=AutoTokenizer.from_pretrained(base,local_files_only=True)
    wrapper.model.generation_config.eos_token_id=wrapper.tokenizer.eos_token_id
    wrapper.model.generation_config.pad_token_id=wrapper.tokenizer.pad_token_id
    wrapper.identity={'evaluation_only':True,'adapter_path':str(adapter),'pre_merge_activation':audit}
    return wrapper

def worker(adapter,output):
    from Server.local_probe.gpu_gateway import digest
    model=load_candidate(adapter,REPO/'.runtime/qwen4b-sft-evaluation'/output.stem)
    results=[];cases=fixtures()
    report={'profile':'full-facts','adapter':str(adapter),'adapter_sha256':hashlib.sha256((adapter/'adapter_model.safetensors').read_bytes()).hexdigest(),
            'scope':'offline actual model, deployed inference math, source holdout and controlled axis pairs','nine_b_parity_verified':False}
    try:
        for case in cases:
            started=time.monotonic();payload={'text':case['text'],'context':case['context']}
            try:
                answer,metrics=model.chat(payload);error=None
            except Exception as exc:
                answer=None;metrics=model.last_metrics;error=type(exc).__name__+': '+str(exc)
            results.append({'id':case['id'],'case':case,'raw':json.dumps(answer,ensure_ascii=False) if answer else None,
                            'contract_valid':error is None,'error':error,'metrics':metrics,'seconds':time.monotonic()-started,
                            'payload_sha256':digest(payload)})
            report.update(results=results,count=len(results),contract_valid=sum(r['contract_valid'] for r in results),complete=len(results)==len(cases))
            output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    finally:model.close()

def main():
    p=argparse.ArgumentParser();p.add_argument('--adapter',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--worker',action='store_true');a=p.parse_args()
    if a.worker:return worker(a.adapter.resolve(),a.output.resolve())
    a.output.mkdir(parents=True,exist_ok=True)
    for name,adapter in [('before',ROOT/'runs/qwen4b-natural-v1/checkpoint-epoch-2'),('after',ROOT/'runs/qwen4b-healthmon-sft-v1/checkpoint-epoch-2')]:
        with (a.output/(name+'.log')).open('w',encoding='utf-8') as log:
            subprocess.run([sys.executable,'-X','utf8','-B',__file__,'--worker','--adapter',str(adapter),'--output',str((a.output/(name+'.json')).resolve())],cwd=REPO,stdout=log,stderr=log,check=True)
    print('Final before/after evaluation complete; semantic review required before promotion.',flush=True)

if __name__=='__main__':main()
