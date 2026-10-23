import copy,json,os,uuid
import pytest
from fastapi.testclient import TestClient
from src import app as module
from src.agent import respond,validate
from src.prompts import messages
from src.db import connect
from src.embedding import embedder
from src.evidence import memory_slot
from test_agent import CONTEXT,output
from test_postgres import Controlled,auth,pet,chat,event

def test_repair_contains_failed_assistant_and_repeat_second_is_checked():
 c=copy.deepcopy(CONTEXT);c['recent']=[{'user':'안녕','assistant':'반가워.'}]
 class B:
  def generate(self,context,text,repair=None):
   if repair:
    assert json.loads(repair['raw'])['speech']=='반가워.'
    ms=messages(context,text,repair)
    assert ms[-2]['role']=='assistant'
   return output('반가워.')
 final,metrics=respond(B(),c,'안녕')
 assert metrics['fallback'] and metrics['attempts']==2

def test_activity_evidence_is_not_missing_memory_and_unrelated_fact_is_not_nickname():
 c=copy.deepcopy(CONTEXT);c['activities']=[{'kind':'walk','amount':320,'confirmed':True,'source':'backend'}]
 assert validate(output('확인된 걷기 기록은 320걸음이야.'),c,'운동 기록 기억나?')
 c['recent']=[{'user':'나는 수영이 좋아.','assistant':'그렇구나.'}]
 with pytest.raises(ValueError):validate(output('네 별명은 수영이야.'),c,'내 별명 기억해?')

def test_real_retrieval_followup_and_irrelevant_weather(monkeypatch):
 monkeypatch.setattr(module,'backend',Controlled());client=TestClient(module.app);p=pet(client)
 chat(client,p,'나는 걷기보다 수영이 좋아.')
 queries=[('지금은 뭐가 좋다고 알고 있어?',[{'user':'내 운동 취향 기억나?','assistant':'수영이야.'}],True),
          ('오늘 날씨가 좋네',[],False),('내 별명 기억해?',[],False)]
 for text,recent,wanted in queries:
  v=embedder.encode(text)
  with connect() as c:got=module.retrieve(c,p,v,query=text,recent=recent,for_chat=True)
  assert bool(got)==wanted
 with connect() as c:
  m=c.execute('SELECT source_id FROM memories WHERE pet_id=%s AND valid',(p,)).fetchone()
 client.delete(f"/pets/{p}/sources/{m['source_id']}",params={'expected_revision':1},headers=auth())
 with connect() as c:assert not module.retrieve(c,p,embedder.encode('내 취향'),query='내 취향',for_chat=True)

def test_quest_opt_out_drops_candidates(monkeypatch):
 class Capture(Controlled):
  def generate(self,context,text,repair=None):
   assert not context['candidates']
   return output('알겠어. 지금은 조용히 쉬자.')
 monkeypatch.setattr(module,'backend',Capture());client=TestClient(module.app);p=pet(client)
 event(client,p)
 assert chat(client,p,'퀘스트는 됐어. 그냥 쉬자.').status_code==200
