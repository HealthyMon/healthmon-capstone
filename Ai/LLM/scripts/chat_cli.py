"""Local test client; /state, /quests, /accept ID, /reject ID, /memories QUERY."""
import argparse,json,os,uuid,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
import httpx
p=argparse.ArgumentParser();p.add_argument('--pet');p.add_argument('--url',default='http://127.0.0.1:8000')
p.add_argument('--speech-level',choices=['casual','formal'],default='casual');p.add_argument('--profanity',choices=['none','mild'],default='mild');p.add_argument('--name',default='몽글이');args=p.parse_args()
token=list(json.loads(os.environ['DEV_TOKENS']))[0]
client=httpx.Client(base_url=args.url,headers={'Authorization':'Bearer '+token},timeout=240)
pet=args.pet or client.post('/pets',json={'name':args.name,'speech_level':args.speech_level,'profanity':args.profanity}).json()['pet_id']
memory_cache={}
print(f'헬스몬 테스트 | pet_id={pet}\n종료: /quit, 상태: /state, 퀘스트: /quests, 기억: /memories 검색어\n정정: /correct 기억ID 새 사실, 삭제: /forget 기억ID (먼저 /memories로 조회)')
while True:
    try:text=input('나> ').strip()
    except (EOFError,KeyboardInterrupt):break
    if text=='/quit':break
    if not text:continue
    if text=='/state':r=client.get(f'/pets/{pet}/state')
    elif text=='/quests':r=client.get(f'/pets/{pet}/quests')
    elif text.startswith('/memories '):
        r=client.get(f'/pets/{pet}/memories',params={'query':text[10:]})
        if r.is_success:memory_cache.update({m['id']:m for m in r.json()['memories']})
    elif text.startswith(('/correct ','/forget ')):
        parts=text.split(maxsplit=2);ident=parts[1] if len(parts)>1 else ''
        m=memory_cache.get(ident)
        if not m:print('먼저 /memories 검색어로 현재 기억 ID를 조회해 주세요.');continue
        if parts[0]=='/forget':
            r=client.delete(f'/pets/{pet}/memories/{ident}',params={'expected_revision':m['source_revision']})
        elif len(parts)<3:print('/correct 기억ID 새 사실 형식으로 입력해 주세요.');continue
        else:
            r=client.patch(f"/pets/{pet}/sources/{m['source_id']}",json={'expected_revision':m['source_revision'],'text':parts[2]})
            if r.is_success:r=client.post(f'/pets/{pet}/memories',json={'source_id':m['source_id'],'revision':r.json()['revision'],'slot':m['slot']})
        if r.is_success:memory_cache.clear()
    elif text.startswith(('/accept ','/reject ')):
        command,ident=text.split(maxsplit=1);r=client.post(f'/pets/{pet}/quests/{ident}/decision',json={'decision':command[1:]})
    else:
        r=client.post(f'/pets/{pet}/chat',json={'text':text,'request_id':uuid.uuid4().hex})
        if r.is_success:
            data=r.json();print('몽글이>',data['response']['speech'])
            print('  상태 버전:',data['state_version'],'기억:',data['response']['memory_ids'],'행동:',data['execution'],'fallback:',data['metrics']['fallback'])
            continue
    print(json.dumps(r.json(),ensure_ascii=False,indent=2))
