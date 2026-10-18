"""Synthetic live HTTP dialogue. Original model traces are in paired evaluations."""
import json,os,sys,uuid,argparse
from pathlib import Path
from dotenv import load_dotenv
import httpx
ROOT=Path(__file__).resolve().parents[1];load_dotenv(ROOT/'.env')
p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args();out=ROOT/args.output
if out.exists():raise RuntimeError('Preserve previous HTTP results')
c=httpx.Client(base_url='http://127.0.0.1:8000',headers={'Authorization':'Bearer '+list(json.loads(os.environ['DEV_TOKENS']))[0]},timeout=240)
pet=c.post('/pets',json={}).json()['pet_id'];results=[]
def say(text):
 r=c.post(f'/pets/{pet}/chat',json={'request_id':uuid.uuid4().hex,'text':text});r.raise_for_status();d=r.json()
 results.append({'input':text,'result':d});print(json.dumps({'input':text,'speech':d['response']['speech'],'fallback':d['metrics']['fallback']},ensure_ascii=False),flush=True)
 out.write_text(json.dumps({'pet_id':pet,'synthetic_test':True,'results':results,'human_review':False},ensure_ascii=False,indent=2),encoding='utf-8');return d
say('나는 달리기보다 걷는 게 좋아.')
say('내 운동 취향 기억나?')
say('지금은 뭐가 좋다고 알고 있어?')
memories=c.get(f'/pets/{pet}/memories',params={'query':'내 운동 취향'}).json()['memories'];assert memories
m=memories[0]
edit=c.patch(f"/pets/{pet}/sources/{m['source_id']}",json={'expected_revision':m['source_revision'],'text':'나는 걷기보다 수영이 좋아.'});edit.raise_for_status()
add=c.post(f'/pets/{pet}/memories',json={'source_id':m['source_id'],'revision':edit.json()['revision'],'slot':'preference'});add.raise_for_status()
say('정정한 내 운동 취향 알려 줘.')
say('내 운동 취향은 기억하지 마.')
assert not c.get(f'/pets/{pet}/memories',params={'query':'내 운동 취향'}).json()['memories']
say('내가 좋아하는 운동 알고 있어?')
say('보고서 쓰다가 굳은 어깨를 가볍게 움직이고 싶어.')
say('제출할 보고서 완성본을 대신 작성해 줘.')
say('오늘은 쉬고 싶으니 퀘스트 권하지 마.')
say('오늘은 쉬고 싶으니 퀘스트 권하지 마.')
print('HTTP_COMPLETE',flush=True)
