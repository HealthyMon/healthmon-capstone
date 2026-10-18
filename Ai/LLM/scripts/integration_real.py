"""Real Qwen + PostgreSQL + BGE-M3. Synthetic inputs only, no human approval claim."""
import argparse,copy,json,os,sys,uuid
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
p=argparse.ArgumentParser();p.add_argument('--adapter',required=True);p.add_argument('--output',default='runs/real-integration.json');args=p.parse_args()
os.environ['ADAPTER_PATH']=args.adapter
from fastapi.testclient import TestClient
from src.app import app,backend
from src.agent import respond
from src.rules import RULES
from src.db import connect
import torch
torch.manual_seed(321)
c=TestClient(app);headers={'Authorization':'Bearer '+list(json.loads(os.environ['DEV_TOKENS']))[0]}
pet=c.post('/pets',json={},headers=headers).json()['pet_id'];records=[]
def record(label,data):
    records.append({'case':label,**data})
    (ROOT/args.output).write_text(json.dumps({'pet_id':pet,'records':records,'synthetic_inputs':True,
          'human_review':False,'backend':'real Qwen+LoRA / real PostgreSQL+pgvector / real BGE-M3 CPU'},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'case':label,**data},ensure_ascii=False),flush=True)
def talk(text):
    r=c.post(f'/pets/{pet}/chat',json={'text':text,'request_id':uuid.uuid4().hex},headers=headers)
    if not r.is_success: raise RuntimeError(r.text)
    d=r.json();record(text,d);return d

talk('안녕, 너 이름이 뭐야?')
preference=talk('나는 달리기보다 걷는 게 좋아.')
memory=talk('내가 좋아하는 운동 기억해?')
assert memory['response']['memory_ids'],'Model did not cite retrieved preference'
talk('과제 때문에 너무 힘들어.')
talk('내 과제 코드 전체 대신 만들어줘.')
talk('가볍게 몸 풀 운동 루틴 추천해줘.')
talk('오늘 나 몇 걸음 걸었어?')
talk('오늘은 피곤해서 그냥 쉴래.')
source=preference['source_id']
r=c.patch(f'/pets/{pet}/sources/{source}',json={'expected_revision':1,'text':'나는 걷기보다 수영이 좋아.'},headers=headers);assert r.is_success,r.text
r=c.post(f'/pets/{pet}/memories',json={'source_id':source,'revision':2,'slot':'preference'},headers=headers);assert r.is_success,r.text
talk('지금은 어떤 운동을 좋아한다고 기억해?')
r=c.delete(f'/pets/{pet}/sources/{source}',params={'expected_revision':2},headers=headers);assert r.is_success,r.text
talk('내가 좋아하는 운동을 알고 있어?')

# Second pet isolates quest assessment from the fatigue cooldown in the first flow.
pet=c.post('/pets',json={},headers=headers).json()['pet_id']
q=talk('지금 할 수 있는 운동 퀘스트 하나 추천해줘.')
if q['execution'].get('offer_id'):
    offer=q['execution']['offer_id']
    r=c.post(f'/pets/{pet}/quests/{offer}/decision',json={'decision':'accept'},headers=headers);assert r.is_success,r.text
    event={'event_id':'real-integration-walk','revision':1,'occurred_at':datetime.now(timezone.utc).isoformat(),
           'kind':'walk','amount':500,'unit':'steps','source':'backend','confirmed':True}
    r=c.post(f'/pets/{pet}/activities',json=event,headers={**headers,'X-Producer-Token':os.environ['PRODUCER_TOKEN']});assert r.is_success,r.text
    record('server_confirmed_quest',c.get(f'/pets/{pet}/quests',headers=headers).json())
    talk('방금 기록한 걸음과 퀘스트 결과 알려줘.')
else:record('quest_offer_failure',{'passed':False,'reason':'Model did not offer an eligible quest'})

base={'settings':{'name':'몽글이','speech_level':'casual','profanity':'mild'},'traits':copy.deepcopy(RULES['initial']),
      'mood':{'valence':0,'energy':50},'memories':[],'recent':[],'activities':[],'candidates':[],'active_quests':[]}
for label,traits,settings,text in [
    ('formal',{'courtesy':95,'playfulness':10},{'speech_level':'formal'},'오늘 운동했어.'),
    ('playful',{'playfulness':95,'bond':90},{},'오늘 운동했어.'),
    ('blunt',{'bluntness':95,'courtesy':20},{},'오늘 운동했어.'),
    ('rough',{'roughness':95,'bluntness':60},{},'신발 끈이 또 풀려서 흐름 끊겼어.'),
    ('rough_disabled',{'roughness':95,'bluntness':60},{'profanity':'none'},'신발 끈이 또 풀려서 흐름 끊겼어.')]:
    context=copy.deepcopy(base);context['traits'].update(traits);context['settings'].update(settings)
    output,metrics=respond(backend,context,text)
    record('dev_forced_style_'+label,{'input':text,'output':output.model_dump(),'metrics':metrics,'natural_accumulation':False})
record('complete',{'complete':True})
