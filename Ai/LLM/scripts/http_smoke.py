import json,os,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
import httpx
tokens=list(json.loads(os.environ['DEV_TOKENS']))
c=httpx.Client(base_url='http://127.0.0.1:8000',headers={'Authorization':'Bearer '+tokens[0]},timeout=240)
assert c.get('/health').json()['loaded']
pet=c.post('/pets',json={}).json()['pet_id'];results=[]
def talk(text):
    r=c.post(f'/pets/{pet}/chat',json={'text':text,'request_id':uuid.uuid4().hex});r.raise_for_status()
    d=r.json();results.append({'input':text,**d});print(json.dumps({'input':text,'response':d['response'],'metrics':d['metrics']},ensure_ascii=False),flush=True)
    (ROOT/'runs/http-smoke-final-v3.json').write_text(json.dumps({'pet_id':pet,'results':results,'transport':'real HTTP'},ensure_ascii=False,indent=2),encoding='utf-8')
    return d
unknown=talk('내가 좋아하는 운동을 알고 있어?')
assert not unknown['response']['memory_ids']
assert not unknown['response']['speech'].startswith('알아.')
assert any(s in unknown['response']['speech'] for s in ('없','모르','몰라','못'))
saved=talk('나는 달리기보다 걷는 게 좋아.')
remembered=talk('내가 좋아하는 운동 기억해?')
assert remembered['response']['memory_ids'] and '걷' in remembered['response']['speech']
forgot=talk('방금 말한 걷기 취향은 기억하지 마.')
assert forgot['execution'].get('deleted_memory_id')
after=talk('내가 좋아하는 운동을 알고 있어?')
assert not after['response']['memory_ids'] and any(s in after['response']['speech'] for s in ('없','모르','몰라','못'))
assert not after['response']['speech'].startswith('알아.')
assert c.get(f'/pets/{pet}/state',headers={'Authorization':'Bearer '+tokens[1]}).status_code==404
print('HTTP_SMOKE_COMPLETE',flush=True)
