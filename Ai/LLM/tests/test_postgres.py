"""Real PostgreSQL/pgvector and real BGE-M3; controlled model for fault injection."""
import json,os,uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import pytest
from fastapi.testclient import TestClient
from src import app as module
from src.db import connect

class Controlled:
    name='controlled-test-model';model=None
    def __init__(self,mode='normal'):self.mode=mode;self.calls=0
    def generate(self,context,text,repair=None):
        self.calls+=1
        if self.mode=='bad':return '{invalid'
        if self.mode=='timeout':raise TimeoutError()
        if self.mode=='oom':raise RuntimeError('CUDA out of memory (fault injection)')
        action={'type':'none','target_id':None}
        if self.mode=='quest' and context['candidates']: action={'type':'offer_quest','target_id':context['candidates'][0]['id']}
        return json.dumps({'speech':'기록을 확인했어. 함께 차근차근 해 보자.','emotion':'neutral','animation':'idle','action':action,'memory_ids':[],'personality_update':None})

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(module,'backend',Controlled())
    return TestClient(module.app)

def auth(n=0):return {'Authorization':'Bearer '+list(json.loads(os.environ['DEV_TOKENS']))[n]}
def pet(c):return c.post('/pets',json={},headers=auth()).json()['pet_id']
def chat(c,p,text='안녕',request_id=None):
    return c.post(f'/pets/{p}/chat',json={'request_id':request_id or uuid.uuid4().hex,'text':text},headers=auth())
def event(c,p,ident='e1',revision=1,amount=500,at=None):
    return c.post(f'/pets/{p}/activities',json={'event_id':ident,'revision':revision,'occurred_at':(at or datetime.now(timezone.utc)).isoformat(),'kind':'walk','amount':amount,'unit':'steps','source':'backend','confirmed':True},
                  headers={**auth(),'X-Producer-Token':os.environ['PRODUCER_TOKEN']})

def test_auth_and_pet_isolation(client):
    p=pet(client)
    assert client.get(f'/pets/{p}/state').status_code==401
    assert client.get(f'/pets/{p}/state',headers=auth(1)).status_code==404
    assert client.get(f'/pets/{p}/memories',params={'query':'취향'},headers=auth(1)).status_code==404

def test_idempotence_and_reused_id(client):
    p=pet(client);rid=uuid.uuid4().hex
    a=chat(client,p,request_id=rid);b=chat(client,p,request_id=rid)
    assert a.status_code==200,a.text
    assert a.json()==b.json() and module.backend.calls==1
    assert chat(client,p,'다른 입력',rid).status_code==409

def test_no_mutation_on_fallback(client,monkeypatch):
    p=pet(client);bad=Controlled('bad');monkeypatch.setattr(module,'backend',bad)
    r=chat(client,p).json()
    assert r['metrics']['fallback'] and r['state_version']==0 and bad.calls==2
    timeout=Controlled('timeout');monkeypatch.setattr(module,'backend',timeout)
    assert chat(client,p).json()['state_version']==0 and timeout.calls==1
    monkeypatch.setattr(module,'backend',Controlled('oom'))
    assert chat(client,p).json()['state_version']==0

def test_concurrent_state_change_during_generation(client,monkeypatch):
    p=pet(client)
    class Interleaved(Controlled):
        def generate(self,context,text,repair=None):
            event(client,p,ident='arrived-during-generation',amount=30)
            return super().generate(context,text,repair)
    monkeypatch.setattr(module,'backend',Interleaved())
    r=chat(client,p)
    assert r.status_code==409
    with connect() as c:
        assert c.execute("SELECT COUNT(*) AS n FROM sources WHERE pet_id=%s AND kind='message'",(p,)).fetchone()['n']==0
    assert client.get(f'/pets/{p}/state',headers=auth()).json()['state_version']==1

def test_database_outage_is_explicit(client,monkeypatch):
    monkeypatch.setenv('DATABASE_URL','postgresql://unused:unused@127.0.0.1:59999/unused')
    r=client.get('/health')
    assert r.status_code==503 and 'Database unavailable' in r.text

def test_memory_correction_and_delete(client):
    p=pet(client)
    r=chat(client,p,'나는 달리기보다 걷는 게 좋아.').json();source=r['source_id']
    memories=client.get(f'/pets/{p}/memories',params={'query':'좋아하는 운동은 걷기'},headers=auth()).json()['memories']
    assert memories and '걷는' in memories[0]['content']
    corrected=client.patch(f'/pets/{p}/sources/{source}',json={'expected_revision':1,'text':'나는 수영이 좋아.'},headers=auth())
    assert corrected.status_code==200
    assert not client.get(f'/pets/{p}/memories',params={'query':'걷기'},headers=auth()).json()['memories']
    assert chat(client,p,'나는 달리기보다 걷는 게 좋아.',r['request_id']).status_code==410
    add=client.post(f'/pets/{p}/memories',json={'source_id':source,'revision':2,'slot':'preference'},headers=auth())
    assert add.status_code==200,add.text
    assert client.delete(f'/pets/{p}/sources/{source}',params={'expected_revision':2},headers=auth()).status_code==200
    assert not client.get(f'/pets/{p}/memories',params={'query':'수영'},headers=auth()).json()['memories']
    with connect() as c:
        row=c.execute('SELECT embedding,content FROM memories WHERE pet_id=%s',(p,)).fetchone()
        assert row['embedding'] is None and row['content']=='[invalidated]'

def test_quest_accept_progress_reward_and_reversal(client,monkeypatch):
    p=pet(client);monkeypatch.setattr(module,'backend',Controlled('quest'))
    r=chat(client,p,'퀘스트 추천해줘').json();offer=r['execution']['offer_id']
    before=client.get(f'/pets/{p}/quests',headers=auth()).json()
    assert before['offers'][0]['status']=='offered' and before['reward_balance']==0
    assert client.post(f'/pets/{p}/quests/{offer}/decision',json={'decision':'accept'},headers=auth()).status_code==200
    at=datetime.now(timezone.utc)
    a=event(client,p,at=at);assert a.status_code==200,a.text
    assert event(client,p,at=at).json()['duplicate']
    quests=client.get(f'/pets/{p}/quests',headers=auth()).json()
    assert quests['reward_balance']==5 and quests['offers'][0]['status']=='completed'
    assert event(client,p,revision=2,amount=100,at=at).status_code==200
    assert client.get(f'/pets/{p}/quests',headers=auth()).json()['reward_balance']==0

def test_reject_stale_and_untrusted_events(client,monkeypatch):
    p=pet(client);monkeypatch.setattr(module,'backend',Controlled('quest'))
    r=chat(client,p,'퀘스트 추천해줘').json();offer=r['execution']['offer_id']
    assert client.post(f'/pets/{p}/quests/{offer}/decision',json={'decision':'reject'},headers=auth()).status_code==200
    assert not client.get(f'/pets/{p}/quests',headers=auth()).json()['candidates']
    p2=pet(client);r=chat(client,p2,'퀘스트 추천해줘').json();offer=r['execution']['offer_id']
    event(client,p2,amount=1)
    assert client.post(f'/pets/{p2}/quests/{offer}/decision',json={'decision':'accept'},headers=auth()).status_code==409
    bad=client.post(f'/pets/{p2}/activities',json={'event_id':'forged','revision':1,'occurred_at':datetime.now(timezone.utc).isoformat(),'kind':'walk','amount':500,'unit':'steps','source':'backend','confirmed':True},headers=auth())
    assert bad.status_code==403

def test_concurrent_activity_and_replay(client):
    p=pet(client);at=datetime.now(timezone.utc)
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda _:event(client,p,at=at),range(2)))
    assert all(r.status_code==200 for r in results)
    assert sum(bool(r.json().get('duplicate')) for r in results)==1
    assert client.get(f'/pets/{p}/state',headers=auth()).json()['state_version']==1
    event(client,p,'e2',at=at-timedelta(days=1));event(client,p,'e3',at=at-timedelta(hours=1))
    assert client.get(f'/pets/{p}/state',headers=auth()).json()['traits']['initiative']==51
    client.delete(f'/pets/{p}/sources/activity:e2',params={'expected_revision':1},headers=auth())
    assert client.get(f'/pets/{p}/state',headers=auth()).json()['traits']['initiative']==50

def test_invalid_activity_time_unit_revision(client):
    p=pet(client)
    assert event(client,p,at=datetime.now(timezone.utc)+timedelta(days=1)).status_code==422
    assert event(client,p,revision=2).status_code==409
    at=datetime.now(timezone.utc)
    assert event(client,p,at=at).status_code==200
    assert event(client,p,amount=99,at=at).status_code==409
    r=client.get(f'/pets/{p}/activities',params={'start':(at-timedelta(seconds=1)).isoformat(),'end':(at+timedelta(seconds=1)).isoformat()},headers=auth())
    assert len(r.json()['records'])==1
    assert client.get(f'/pets/{p}/activities',headers=auth(1)).status_code==404

def test_offline_activity_suggestion_is_persisted_and_not_accepted(client,monkeypatch):
    p=pet(client);monkeypatch.setattr(module,'backend',Controlled('quest'))
    assert event(client,p).status_code==200
    jobs=client.get(f'/pets/{p}/quests',headers=auth()).json()['pending_activity_suggestions']
    assert jobs[0]['source_id']=='activity:e1'
    url=f'/pets/{p}/activity-suggestions/e1?revision=1'
    first=client.post(url,headers=auth());second=client.post(url,headers=auth())
    assert first.status_code==200,first.text
    assert first.json()==second.json()
    q=client.get(f'/pets/{p}/quests',headers=auth()).json()
    assert len(q['offers'])==1 and q['offers'][0]['status']=='offered' and q['reward_balance']==0
    assert client.post(url,headers=auth(1)).status_code==404

def test_natural_forget_clear_target_and_ambiguous_request(client):
    p=pet(client)
    chat(client,p,'나는 달리기보다 걷는 게 좋아.')
    vague=chat(client,p,'그거 기억하지 마.').json()
    assert 'deleted_memory_id' not in vague['execution']
    assert client.get(f'/pets/{p}/memories',params={'query':'좋아하는 운동'},headers=auth()).json()['memories']
    clear=chat(client,p,'방금 말한 걷기 취향은 기억하지 마.').json()
    assert clear['execution']['deleted_memory_id'] and clear['metrics']['attempts']==0
    assert not client.get(f'/pets/{p}/memories',params={'query':'좋아하는 운동'},headers=auth()).json()['memories']
