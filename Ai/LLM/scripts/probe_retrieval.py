import json,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.embedding import embedder
from src.db import connect
from src.app import retrieve
from psycopg.types.json import Jsonb
pet='retrieval-audit-'+uuid.uuid4().hex
fact='나는 걷기보다 수영이 좋아.';vec=embedder.encode(fact)
with connect() as c:
 c.execute('INSERT INTO pets(id,owner_id,settings) VALUES(%s,%s,%s)',(pet,'local-audit',Jsonb({'timezone':'Asia/Seoul'})))
 c.execute("INSERT INTO sources(pet_id,id,kind,revision,occurred_at,payload) VALUES(%s,'message:probe','message',2,now(),%s)",(pet,Jsonb({'text':fact})))
 c.execute("INSERT INTO memories(pet_id,id,source_id,source_revision,slot,content,embedding,embedding_revision) VALUES(%s,'probe','message:probe',2,'preference',%s,%s::vector,%s)",(pet,fact,str(vec),embedder.revision))
results=[]
for q in ['내 운동 취향 기억나?','지금은 뭐가 좋다고 알고 있어?','내가 좋아하는 운동 기억해?','내 별명도 기억해?','오늘 날씨가 좋네']:
 v=embedder.encode(q)
 with connect() as c:
  score=c.execute('SELECT 1-(embedding <=> %s::vector) AS score FROM memories WHERE pet_id=%s',(str(v),pet)).fetchone()['score']
  got=retrieve(c,pet,v)
 results.append({'query':q,'score':score,'returned':[r['id'] for r in got]})
out={'pet_id':pet,'fact':fact,'threshold':0.5,'results':results,'synthetic':True}
(ROOT/'runs/improvement-20260929/retrieval-before.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False,indent=2))
