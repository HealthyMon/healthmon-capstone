"""Real 4B generations using unchanged common-server personality/context prompts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT.parents[1]))
from Server.healthmon.rules import initial_state


def fixtures():
    cases=[]
    def add(ident,text,axes=None,memories=None,recent=None):
        state=initial_state()
        state.update(axes or {})
        cases.append({'id':ident,'text':text,'context':{'state':state,
            'personality':{k:state[k] for k in ('activity','affinity','initiative')},
            'settings':{'name':'몽글이','speech_level':'casual','profanity':'none'},
            'memories':memories or [],'recent':recent or []}})
    for axis in ('activity','affinity','initiative'):
        for score in (10,90):
            add(f'{axis}-{score}','오늘은 너랑 잠깐 수다 떨고 싶어.',{axis:score})
    add('memory-revision','바뀐 걷기 목표 시간대는?',memories=[
        {'id':'goal-v2','content':'걷기 목표를 점심에서 저녁으로 바꿨어.','source_id':'goal','source_revision':2}])
    add('memory-absent','내가 전에 좋아한다고 한 과일이 뭐였지?')
    add('memory-number','내 산책 목표 기억해?',memories=[
        {'id':'goal-5','content':'내 목표는 저녁 식사 뒤 5분 산책이야.','source_id':'goal','source_revision':1}])
    add('exercise-complaint','오늘 운동은 너무 귀찮고 싫어.')
    add('character-affection','몽글아 너랑 이야기하니까 좋아.')
    add('rest-high','너무 피곤해서 오늘은 쉬고 싶어.',{'activity':90,'initiative':90})
    return cases


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--adapter',type=Path)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--profile',choices=['original','full-facts','structured'],default='full-facts')
    a=p.parse_args()
    if a.output.exists():raise ValueError('Choose a new report path')
    os.environ['MODEL_PATH']=str(ROOT/'models/qwen3.5-4b')
    os.environ['MODEL_QUANTIZATION']='nf4'
    if a.adapter:os.environ['ADAPTER_PATH']=str(a.adapter.resolve())
    else:os.environ.pop('ADAPTER_PATH',None)
    import torch
    from src.model import QwenBackend
    from Server.healthmon.gateway import Speech
    from Server.local_probe.gpu_gateway import messages, projected_messages, validate_contract, evaluate_style_quality
    from Server.local_probe.structured_dialogue import structured_messages
    b=QwenBackend()
    b.load()
    adapter_sha256=hashlib.sha256((a.adapter/'adapter_model.safetensors').read_bytes()).hexdigest() if a.adapter else None
    results=[]
    try:
        for index,payload in enumerate(fixtures()):
            if a.profile=='original':prompt,style=messages(payload)
            elif a.profile=='full-facts':prompt,style=projected_messages(payload,full_personality_facts=True)
            else:prompt,style=structured_messages(payload,enabled=True,
                base_builder=lambda v:projected_messages(v,full_personality_facts=True))
            torch.manual_seed(543+index)
            start=time.monotonic()
            raw=b.generate_prompt(prompt,max_new_tokens=440,temperature=.6,
                use_cache=True,cache_implementation='dynamic',past_key_values=None)
            quality=None
            try:
                out=Speech.model_validate_json(raw)
                validate_contract(out,payload)
                quality=evaluate_style_quality(payload,out,style)
                error=None
            except Exception as exc:error=str(exc)
            results.append({'id':payload['id'],'payload':payload,'raw':raw,'contract_valid':error is None,
                            'error':error,'style_quality':quality,'seconds':time.monotonic()-start})
            print(json.dumps(results[-1],ensure_ascii=False),flush=True)
            a.output.parent.mkdir(parents=True,exist_ok=True)
            a.output.write_text(json.dumps({'profile':a.profile,'adapter':str(a.adapter),'adapter_sha256':adapter_sha256,'results':results,
                'contract_valid':sum(r['contract_valid'] for r in results),'count':len(results),
                'complete':len(results)==len(fixtures()),'nine_b_parity_verified':False,
                'scope':'real model; synthetic context fixtures; no DB or Unity APK session'},ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        b.model=None
        torch.cuda.empty_cache()
        b.gpu_lease.release()


if __name__=='__main__':main()
