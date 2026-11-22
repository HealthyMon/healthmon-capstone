"""Controlled parameter comparison against the installed gateway; synthetic inputs only."""
import json
from pathlib import Path
import sys
import time
import uuid
import urllib.request
from prepare_qwen4b_common import make

REPO=Path(__file__).resolve().parents[3]

def main():
    config=json.loads((REPO/'.runtime/qwen4b-live/gateway.json').read_text(encoding='utf-8-sig'))
    base='http://127.0.0.1:18091'
    health=json.load(urllib.request.urlopen(base+'/health',timeout=30))
    cases=[]
    for scene,(text,register) in enumerate([
        ('종이접기로 작은 배를 만들었어.','casual'),
        ('오랜만에 동네 빵집에 다녀왔어요.','formal'),
        ('퍼즐 한 상자를 선물 받았어.','casual'),
    ]):
        for axis in ('activity','affinity','initiative'):
            for value in (0,100):
                axes=dict(activity=50,affinity=50,initiative=50);axes[axis]=value
                row=make('comparison',text,'',axes=axes,recent=[{'speech':'좋아! 어떤 이야기를 해 볼까?','source_id':'synthetic-prior'}])
                row['context']['settings']['speech_level']=register
                cases.append(dict(id=f'{scene}-{axis}-{value}',axis=axis,value=value,text=text,context=row['context']))
    for activity,initiative in [(0,0),(0,100),(100,0),(100,100)]:
        row=make('mixed','작은 화분을 하나 들여왔어.','',axes=dict(activity=activity,affinity=50,initiative=initiative))
        cases.append(dict(id=f'mixed-{activity}-{initiative}',text=row['user_text'],context=row['context']))
    for i,text in enumerate(['오늘은 질문 없이 조용히 내 얘기만 들어줬으면 해.','기억해 둔 내가 좋아하는 차가 뭐였지?']):
        memories=[] if i==0 else [{'id':'test-tea','content':'좋아하는 차를 녹차에서 둥굴레차로 바꿨어.','source_id':'synthetic-memory','source_revision':2}]
        row=make('regression',text,'',axes=dict(activity=100,affinity=100,initiative=100),memories=memories)
        cases.append(dict(id=f'regression-{i}',text=text,context=row['context']))
    report=dict(scope='current installed model, controlled axes; no old-model or 9B comparison',health=health,results=[],complete=False)
    destination=REPO/'Ai/LLM/runs/qwen4b-axis-priority-v1/parameter-comparison.json'
    for case in cases:
        payload=dict(contract_version='healthmon.ai.v1',request_id='axis-review-'+uuid.uuid4().hex,pet_id='synthetic-axis-review',input=dict(text=case['text'],context=case['context']))
        req=urllib.request.Request(base+'/v1/chat',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+config['server_token']})
        started=time.monotonic()
        try:
            with urllib.request.urlopen(req,timeout=180) as response: result=json.load(response)
            error=None
        except Exception as exc: result=None;error=type(exc).__name__+': '+str(exc)
        report['results'].append(dict(case=case,result=result,error=error,seconds=round(time.monotonic()-started,3)))
        report['complete']=len(report['results'])==len(cases)
        destination.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'complete':True,'count':len(cases),'errors':sum(r['error'] is not None for r in report['results'])}))

if __name__=='__main__': main()
