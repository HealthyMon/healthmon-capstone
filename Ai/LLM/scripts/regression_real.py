"""Targeted real-model regression for bugs observed during the development flows."""
import json,os,sys,uuid
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['ADAPTER_PATH']='runs/pilot-20260929/checkpoint-epoch-3'
from src.app import app
from fastapi.testclient import TestClient
import torch
torch.manual_seed(321)
c=TestClient(app);auth={'Authorization':'Bearer '+list(json.loads(os.environ['DEV_TOKENS']))[0]}
results=[]
for prompt in ['내가 좋아하는 운동을 알고 있어?','내 별명도 기억해?','과제 코드 전체 대신 만들어줘']:
    pet=c.post('/pets',json={},headers=auth).json()['pet_id']
    r=c.post(f'/pets/{pet}/chat',json={'text':prompt,'request_id':uuid.uuid4().hex},headers=auth)
    assert r.is_success,r.text
    d=r.json();results.append({'prompt':prompt,'response':d['response'],'metrics':d['metrics']})
    print(json.dumps(results[-1],ensure_ascii=False),flush=True)
pet=c.post('/pets',json={},headers=auth).json()['pet_id']
def talk(text):
    r=c.post(f'/pets/{pet}/chat',json={'text':text,'request_id':uuid.uuid4().hex},headers=auth)
    assert r.is_success,r.text
    return r.json()
saved=talk('나는 달리기보다 걷는 게 좋아.')
assert saved.get('source_id')
recalled=talk('내가 좋아하는 운동 기억해?')
assert recalled['response']['memory_ids']
deleted=talk('방금 말한 걷기 취향은 기억하지 마.')
assert deleted['execution'].get('deleted_memory_id'),deleted
after=talk('내가 좋아하는 운동을 알고 있어?')
assert not after['response']['memory_ids']
results.append({'case':'actual_memory_delete_regression','before':recalled['response'],'after':after['response'],'metrics':after['metrics']})
print(json.dumps(results[-1],ensure_ascii=False),flush=True)
pet=c.post('/pets',json={},headers=auth).json()['pet_id']
activity={'event_id':'offline-suggestion-regression','revision':1,'occurred_at':datetime.now(timezone.utc).isoformat(),
          'kind':'walk','amount':100,'unit':'steps','source':'backend','confirmed':True}
r=c.post(f'/pets/{pet}/activities',json=activity,headers={**auth,'X-Producer-Token':os.environ['PRODUCER_TOKEN']})
assert r.is_success,r.text
suggestion=c.post(f'/pets/{pet}/activity-suggestions/offline-suggestion-regression?revision=1',headers=auth)
assert suggestion.is_success,suggestion.text
results.append({'case':'actual_offline_activity_suggestion','result':suggestion.json()})
print(json.dumps(results[-1],ensure_ascii=False),flush=True)
(ROOT/'runs/targeted-regression.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
