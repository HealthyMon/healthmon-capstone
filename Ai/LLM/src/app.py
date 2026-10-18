"""Local API: authenticated pet scope, short transactions, authoritative events."""
import hashlib, json, os, re, secrets, time, uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Depends, Header, HTTPException,Query,Request
from fastapi.responses import JSONResponse
import psycopg
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field
from .contracts import ChatInput, ActivityInput, SettingsInput, MemoryInput, SourceEdit, Decision, SCHEMA_VERSION,ModelOutput,Action
from .db import connect, owned, sources, bump, snapshot
from .rules import replay, RULES, tags
from .model_runtime import OnDemandEmbedder, OnDemandQwen, runtime as model_runtime, ModelBusy
from .agent import respond
from .evidence import memory_slot
from .beta import browser_identity, install_beta
from .food import install_food

app=FastAPI(title='Healthmon local AI',version=SCHEMA_VERSION)
backend=OnDemandQwen()
embedder=OnDemandEmbedder()

def now(): return datetime.now(timezone.utc)

def vectorize(text):
    try:return embedder.encode(text)
    except ValueError as error:raise HTTPException(422,str(error))

def forget_target(c,pet,text):
    requested=bool(re.search(r'기억하지\s*마[.!? ]*$|기억에서\s*지워\s*줘[.!? ]*$|취향.*지우고\s*싶어[.!? ]*$',text))
    if not requested:return None
    rows=c.execute('''SELECT m.id,m.source_id,m.source_revision,m.slot,m.content FROM memories m
      JOIN sources s ON s.pet_id=m.pet_id AND s.id=m.source_id
      WHERE m.pet_id=%s AND m.valid AND s.valid AND s.revision=m.source_revision''',(pet,)).fetchall()
    slot='preference' if '취향' in text else ('goal' if '목표' in text else None)
    matches=[r for r in rows if slot and r['slot']==slot]
    named=[stem for stem in ('걷','달리','수영','자전거','요가','축구') if stem in text]
    matches=[r for r in matches if all(stem in r['content'] for stem in named)]
    # Explicit slot + exactly one active source is resolvable. Bare '그거' is ambiguous.
    return {'target':matches[0] if len(matches)==1 else None}

def time_window(text,tz):
    local=now().astimezone(ZoneInfo(tz));start=local.replace(hour=0,minute=0,second=0,microsecond=0)
    if '어제' in text:return start-timedelta(days=1),start,'yesterday'
    if '지난주' in text:
        week=start-timedelta(days=start.weekday());return week-timedelta(days=7),week,'previous_calendar_week'
    if '이번주' in text or '이번 주' in text:return start-timedelta(days=start.weekday()),start+timedelta(days=1),'this_week'
    return start,start+timedelta(days=1),'today'
def identity(request:Request,authorization:str=Header(default='')):
    if not authorization:return browser_identity(request)
    token=authorization.removeprefix('Bearer ')
    mapping=json.loads(os.getenv('DEV_TOKENS','{}'))
    for secret,user in mapping.items():
        if secrets.compare_digest(token,secret): return user
    raise HTTPException(401,'Authentication required')

@app.exception_handler(psycopg.Error)
async def database_error(request,exc):
    return JSONResponse(status_code=503,content={'detail':'Database unavailable; retry with same request ID'})

@app.exception_handler(ModelBusy)
async def model_busy(request,exc):
    return JSONResponse(status_code=503,content={'detail':str(exc)})

def current(c,p): return replay(sources(c,p['id']),tz=p['settings']['timezone'])

def refreshed(c,p):
    version=bump(c,p['id']); state=current(c,p); snapshot(c,p['id'],state,version)
    return state,version

def reconcile_quests(c,p):
    for q in c.execute("SELECT * FROM quest_offers WHERE pet_id=%s AND status IN ('active','completed','revoked') ORDER BY accepted_at,id",(p['id'],)).fetchall():
        total=c.execute("SELECT COALESCE(SUM((payload->>'amount')::float),0) AS total FROM sources WHERE pet_id=%s AND valid AND kind='activity' AND payload->>'kind'=%s AND payload->>'confirmed'='true' AND payload->>'source' IN ('sensor','backend') AND occurred_at>=%s AND occurred_at<%s",
                        (p['id'],q['template']['kind'],q['accepted_at'],q['expires_at'])).fetchone()['total']
        done=total>=q['template']['target']
        status='completed' if done else ('revoked' if q['status'] in ('completed','revoked') else 'active')
        c.execute('UPDATE quest_offers SET progress=%s,status=%s WHERE pet_id=%s AND id=%s',(total,status,p['id'],q['id']))
        awarded=c.execute('SELECT COALESCE(SUM(amount),0) AS n FROM reward_ledger WHERE pet_id=%s AND offer_id=%s',(p['id'],q['id'])).fetchone()['n']
        delta=(q['template']['reward'] if done else 0)-awarded
        if delta:
            version=c.execute('SELECT version FROM pets WHERE id=%s',(p['id'],)).fetchone()['version']
            c.execute('INSERT INTO reward_ledger(pet_id,offer_id,state_version,amount) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING',(p['id'],q['id'],version,delta))

def candidates(c,p,text=''):
    time=now(); tz=ZoneInfo(p['settings']['timezone']); today=time.astimezone(tz).date()
    offers=c.execute('SELECT * FROM quest_offers WHERE pet_id=%s ORDER BY created_at DESC',(p['id'],)).fetchall()
    if tags(text)['tired'] or re.search(r'쉬고 싶|쉬자|권하지|추천하지|퀘스트.{0,12}(싫|됐|거절|안 할)',text): return []
    if any(q['status']=='active' and q['expires_at']>time for q in offers): return []
    if any(q['status']=='completed' and q['accepted_at'].astimezone(tz).date()==today for q in offers): return []
    explicit='퀘스트' in text
    if not explicit and not c.execute("SELECT 1 FROM sources WHERE pet_id=%s AND valid AND kind='activity' AND payload->>'kind'='walk' AND payload->>'confirmed'='true' AND payload->>'source' IN ('backend','sensor') LIMIT 1",(p['id'],)).fetchone():return []
    if not explicit and offers and time-offers[0]['created_at']<timedelta(minutes=RULES['quest_cooldown_minutes']): return []
    rejected={q['template']['id'] for q in offers if q['status']=='rejected' and q['created_at'].astimezone(tz).date()==today}
    pending={q['template']['id'] for q in offers if q['status']=='offered' and q['expires_at']>time and q['state_version']==p['version']}
    return [q for q in RULES['quest_templates'][:1] if q['id'] not in rejected|pending]

def offer(c,p,target):
    valid={q['id']:q for q in candidates(c,p,'퀘스트')}
    if target not in valid: raise HTTPException(409,'Quest no longer eligible')
    ident=uuid.uuid4().hex
    c.execute("INSERT INTO quest_offers(pet_id,id,template,status,state_version,expires_at) VALUES(%s,%s,%s,'offered',%s,%s)",
              (p['id'],ident,Jsonb(valid[target]),p['version'],now()+timedelta(minutes=RULES['quest_expiry_minutes'])))
    return ident

def invalidate(c,pet,source_id,revision):
    ids=[r['id'] for r in c.execute('SELECT id FROM memories WHERE pet_id=%s AND source_id=%s',(pet,source_id))]
    c.execute('UPDATE memories SET valid=false,embedding=NULL,content=%s WHERE pet_id=%s AND source_id=%s',('[invalidated]',pet,source_id))
    c.execute("UPDATE suggestion_jobs SET status='invalidated',result=NULL WHERE pet_id=%s AND source_id=%s",(pet,source_id))
    # Purge all derived response caches for this pet. Never resurrect deleted text via retry/history.
    c.execute("UPDATE requests SET result=NULL,status='invalidated' WHERE pet_id=%s",(pet,))
    c.execute("UPDATE exchanges SET valid=false,speech='',state_used='{}',state_after='{}' WHERE pet_id=%s",(pet,))
    c.execute('DELETE FROM state_snapshots WHERE pet_id=%s',(pet,))
    c.execute('INSERT INTO outbox(pet_id,source_id,revision) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(pet,source_id,revision))
    # Recompute is synchronous; the durable outbox records that the operation completed.
    c.execute("UPDATE outbox SET status='done' WHERE pet_id=%s AND source_id=%s AND revision=%s",(pet,source_id,revision))

@app.get('/health')
def health():
    with connect() as c: version=c.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()
    return {'status':'ok','ready':True,'backend':backend.name,'loaded':backend.model is not None,
            'model_lifecycle':'conversation_session','adapter':os.getenv('ADAPTER_PATH'),'pgvector':version['extversion']}

class ConversationKey(BaseModel):
    session_id:str=Field(pattern=r'^[a-f0-9]{32}$')

class ConversationIntent(ConversationKey):
    active:bool

@app.post('/pets/{pet}/chat-session')
def conversation_session(pet:str,body:ConversationIntent,user=Depends(identity)):
    with connect() as c:owned(c,user,pet)
    key=(user,pet,body.session_id)
    try:
        return backend.open_session(key) if body.active else backend.close_session(key)
    except TimeoutError as error:
        raise HTTPException(504,'Conversation model startup timed out') from error
    except ModelBusy:
        raise
    except RuntimeError as error:
        raise HTTPException(503,'Conversation model could not load') from error

@app.post('/pets/{pet}/chat-session/heartbeat')
def conversation_heartbeat(pet:str,body:ConversationKey,user=Depends(identity)):
    with connect() as c:owned(c,user,pet)
    return backend.heartbeat((user,pet,body.session_id))

@app.post('/pets')
def create_pet(settings:SettingsInput,user=Depends(identity)):
    try: ZoneInfo(settings.timezone)
    except Exception: raise HTTPException(422,'Invalid timezone')
    ident=uuid.uuid4().hex
    with connect() as c:
        c.execute('INSERT INTO pets(id,owner_id,settings) VALUES(%s,%s,%s)',(ident,user,Jsonb(settings.model_dump())))
    return {'pet_id':ident,'state_version':0}

@app.get('/pets/{pet}/state')
def get_state(pet:str,user=Depends(identity)):
    with connect() as c:
        p=owned(c,user,pet)
        return {'state_version':p['version'],'settings':p['settings'],**current(c,p)}

@app.put('/pets/{pet}/settings')
def settings(pet:str,body:SettingsInput,user=Depends(identity)):
    try: ZoneInfo(body.timezone)
    except Exception: raise HTTPException(422,'Invalid timezone')
    with connect() as c:
        p=owned(c,user,pet,True)
        if p['settings']==body.model_dump():return {'state_version':p['version'],'duplicate':True}
        c.execute('UPDATE pets SET settings=%s WHERE id=%s',(Jsonb(body.model_dump()),pet))
        version=bump(c,pet)
    return {'state_version':version}

@app.post('/pets/{pet}/activities')
def activity(pet:str,body:ActivityInput,user=Depends(identity),x_producer_token:str=Header(default='')):
    if body.occurred_at>now()+timedelta(seconds=30): raise HTTPException(422,'Future event')
    if (body.confirmed or body.source in ('sensor','backend')) and not (os.getenv('PRODUCER_TOKEN') and secrets.compare_digest(x_producer_token,os.environ['PRODUCER_TOKEN'])):
        raise HTTPException(403,'Trusted producer required for confirmed events')
    payload=body.model_dump(mode='json'); ident='activity:'+body.event_id
    with connect() as c:
        p=owned(c,user,pet,True)
        old=c.execute('SELECT * FROM sources WHERE pet_id=%s AND id=%s',(pet,ident)).fetchone()
        if old:
            if old['valid'] and old['revision']==body.revision and old['payload']==payload:
                return {'event_id':body.event_id,'state_version':p['version'],'duplicate':True}
            if body.revision!=old['revision']+1: raise HTTPException(409,'Revision conflict')
            invalidate(c,pet,ident,body.revision)
            c.execute('UPDATE sources SET payload=%s,revision=%s,occurred_at=%s,valid=true,received_at=now() WHERE pet_id=%s AND id=%s',
                      (Jsonb(payload),body.revision,body.occurred_at,pet,ident))
        else:
            if body.revision!=1: raise HTTPException(409,'First revision must be 1')
            c.execute("INSERT INTO sources(pet_id,id,kind,revision,occurred_at,payload) VALUES(%s,%s,'activity',1,%s,%s)",(pet,ident,body.occurred_at,Jsonb(payload)))
        state,version=refreshed(c,p); reconcile_quests(c,p)
        available=candidates(c,p)
        if body.confirmed and body.source in ('sensor','backend') and available:
            c.execute('INSERT INTO suggestion_jobs(pet_id,source_id,revision) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(pet,ident,body.revision))
        return {'event_id':body.event_id,'source_id':ident,'state_version':version,'state':state,'available_quests':available}

@app.delete('/pets/{pet}/sources/{source_id}')
def delete_source(pet:str,source_id:str,expected_revision:int,user=Depends(identity)):
    with connect() as c:
        p=owned(c,user,pet,True)
        row=c.execute('SELECT * FROM sources WHERE pet_id=%s AND id=%s',(pet,source_id)).fetchone()
        if not row: raise HTTPException(404,'Source not found')
        if not row['valid']: return {'deleted':True,'state_version':p['version']}
        if row['revision']!=expected_revision: raise HTTPException(409,'Revision conflict')
        c.execute("UPDATE sources SET valid=false,payload='{}',revision=revision+1 WHERE pet_id=%s AND id=%s",(pet,source_id))
        invalidate(c,pet,source_id,expected_revision+1)
        state,version=refreshed(c,p); reconcile_quests(c,p)
        return {'deleted':True,'state_version':version,'state':state}

@app.get('/pets/{pet}/activities')
def activity_records(pet:str,start:datetime | None=None,end:datetime | None=None,user=Depends(identity)):
    if (start and start.tzinfo is None) or (end and end.tzinfo is None):raise HTTPException(422,'Timezone required')
    if start and end and start>=end:raise HTTPException(422,'Invalid time interval')
    with connect() as c:
        owned(c,user,pet)
        records=c.execute("SELECT id,revision,occurred_at,payload FROM sources WHERE pet_id=%s AND kind='activity' AND valid AND (%s::timestamptz IS NULL OR occurred_at>=%s) AND (%s::timestamptz IS NULL OR occurred_at<%s) ORDER BY occurred_at DESC LIMIT 100",(pet,start,start,end,end)).fetchall()
        return {'records':records,'limit':100}

@app.patch('/pets/{pet}/sources/{source_id}')
def edit_source(pet:str,source_id:str,body:SourceEdit,user=Depends(identity)):
    with connect() as c:
        p=owned(c,user,pet,True)
        row=c.execute('SELECT * FROM sources WHERE pet_id=%s AND id=%s AND valid',(pet,source_id)).fetchone()
        if not row: raise HTTPException(404,'Source not found')
        if row['kind']!='message': raise HTTPException(422,'Use versioned activity endpoint')
        if row['revision']!=body.expected_revision: raise HTTPException(409,'Revision conflict')
        revision=row['revision']+1
        c.execute('UPDATE sources SET payload=%s,revision=%s WHERE pet_id=%s AND id=%s',(Jsonb({'text':body.text}),revision,pet,source_id))
        invalidate(c,pet,source_id,revision); state,version=refreshed(c,p)
    return {'revision':revision,'state_version':version,'state':state}

@app.post('/pets/{pet}/memories')
def add_memory(pet:str,body:MemoryInput,user=Depends(identity)):
    with connect() as c:
        owned(c,user,pet)
        s=c.execute('SELECT * FROM sources WHERE pet_id=%s AND id=%s AND valid',(pet,body.source_id)).fetchone()
        if not s or s['revision']!=body.revision: raise HTTPException(409,'Missing or stale source')
        content=s['payload'].get('text',json.dumps(s['payload'],ensure_ascii=False))
    vec=vectorize(content)
    ident=hashlib.sha256((body.source_id+':'+str(body.revision)).encode()).hexdigest()[:24]
    with connect() as c:
        p=owned(c,user,pet,True)
        s=c.execute('SELECT * FROM sources WHERE pet_id=%s AND id=%s AND valid',(pet,body.source_id)).fetchone()
        if not s or s['revision']!=body.revision: raise HTTPException(409,'Source changed')
        existing=c.execute('SELECT valid FROM memories WHERE pet_id=%s AND id=%s',(pet,ident)).fetchone()
        if existing and existing['valid']:return {'memory_id':ident,'state_version':p['version'],'duplicate':True}
        if body.slot in ('preference','goal'):
            c.execute('UPDATE memories SET valid=false WHERE pet_id=%s AND slot=%s',(pet,body.slot))
        c.execute('INSERT INTO memories(pet_id,id,source_id,source_revision,slot,content,embedding,embedding_revision) VALUES(%s,%s,%s,%s,%s,%s,%s::vector,%s) ON CONFLICT(pet_id,id) DO UPDATE SET valid=true',
                  (pet,ident,body.source_id,body.revision,body.slot,content,str(vec),embedder.revision))
        version=bump(c,pet)
    return {'memory_id':ident,'state_version':version}

def wants_memory_lookup(text,recent=()):
    return bool(memory_slot(text,recent) or re.search(r'기억|지난|예전|경험',text))

def durable_memory_slot(text):
    if re.search(r'나는 .*(좋아|싫어)|보다 .*좋아',text):return 'preference'
    if re.search(r'내 목표는|목표로 정했',text):return 'goal'
    return None

def retrieve(c,pet,vec,start=None,end=None,query=None,recent=(),for_chat=False):
    slot=memory_slot(query or '',recent)
    if for_chat and not wants_memory_lookup(query or '',recent):return []
    return c.execute('''SELECT m.id,m.content,m.source_id,m.source_revision,m.slot,1-(m.embedding <=> %s::vector) AS score
      FROM memories m JOIN sources s ON s.pet_id=m.pet_id AND s.id=m.source_id
      WHERE m.pet_id=%s AND m.valid AND s.valid AND s.revision=m.source_revision AND m.embedding IS NOT NULL
      AND (%s::timestamptz IS NULL OR s.occurred_at>=%s) AND (%s::timestamptz IS NULL OR s.occurred_at<%s)
      AND (%s::text IS NULL OR m.slot=%s)
      AND (%s::text IS NOT NULL OR 1-(m.embedding <=> %s::vector)>=%s) ORDER BY score DESC,m.created_at DESC LIMIT 3''',
      (str(vec),pet,start,start,end,end,slot,slot,slot,str(vec),RULES['memory_threshold'])).fetchall()

@app.get('/pets/{pet}/memories')
def get_memories(pet:str,query:str=Query(min_length=1,max_length=1500),start:datetime | None=None,end:datetime | None=None,user=Depends(identity)):
    if (start and start.tzinfo is None) or (end and end.tzinfo is None):raise HTTPException(422,'Timezone required')
    if start and end and start>=end:raise HTTPException(422,'Invalid time interval')
    with connect() as c: owned(c,user,pet)
    vec=vectorize(query)
    with connect() as c:
        owned(c,user,pet); return {'memories':retrieve(c,pet,vec,start,end,query=query)}

@app.delete('/pets/{pet}/memories/{memory_id}')
def forget(pet:str,memory_id:str,expected_revision:int,user=Depends(identity)):
    with connect() as c:
        owned(c,user,pet)
        m=c.execute('SELECT source_id FROM memories WHERE pet_id=%s AND id=%s',(pet,memory_id)).fetchone()
        if not m:raise HTTPException(404,'Memory not found')
    return delete_source(pet,m['source_id'],expected_revision,user)

@app.get('/pets/{pet}/quests')
def get_quests(pet:str,user=Depends(identity)):
    with connect() as c:
        p=owned(c,user,pet)
        return {'offers':c.execute('SELECT * FROM quest_offers WHERE pet_id=%s ORDER BY created_at DESC',(pet,)).fetchall(),
                'candidates':candidates(c,p,'퀘스트'),
                'pending_activity_suggestions':c.execute("SELECT source_id,revision FROM suggestion_jobs WHERE pet_id=%s AND status='pending' ORDER BY created_at",(pet,)).fetchall(),
                'reward_balance':c.execute('SELECT COALESCE(SUM(amount),0) AS n FROM reward_ledger WHERE pet_id=%s',(pet,)).fetchone()['n']}

@app.post('/pets/{pet}/activity-suggestions/{event_id}')
def activity_suggestion(pet:str,event_id:str,revision:int,user=Depends(identity)):
    source_id='activity:'+event_id
    with connect() as c:
        p=owned(c,user,pet,True)
        source=c.execute("SELECT * FROM sources WHERE pet_id=%s AND id=%s AND revision=%s AND valid AND payload->>'confirmed'='true' AND payload->>'source' IN ('backend','sensor')",(pet,source_id,revision)).fetchone()
        if not source:raise HTTPException(404,'Confirmed activity revision not found')
        job=c.execute('SELECT * FROM suggestion_jobs WHERE pet_id=%s AND source_id=%s AND revision=%s',(pet,source_id,revision)).fetchone()
        if job and job['status']=='done':return job['result']
        choices=candidates(c,p)
        if not choices:return {'status':'skipped','reason':'No eligible quest'}
        state=current(c,p);version=p['version']
        context={'settings':p['settings'],'traits':state['traits'],'mood':state['mood'],'recent':[],
                 'memories':[],'activities':[source['payload']],'candidates':choices,'active_quests':[],
                 'trigger':{'kind':'activity','id':source_id,'revision':revision}}
    text='확인된 활동 기록을 보고 적절하면 가능한 퀘스트를 제안해.'
    if isinstance(backend,OnDemandQwen):output,metrics=backend.respond(context,text,owner=user,pet=pet)
    else:output,metrics=respond(backend,context,text)
    with connect() as c:
        p=owned(c,user,pet,True)
        # Concurrent duplicate requests return the first committed result.
        job=c.execute('SELECT * FROM suggestion_jobs WHERE pet_id=%s AND source_id=%s AND revision=%s',(pet,source_id,revision)).fetchone()
        if job and job['status']=='done':return job['result']
        if p['version']!=version:raise HTTPException(409,'Activity or state changed during suggestion')
        result={'response':output.model_dump(),'metrics':metrics,'execution':{},'state_version':version}
        if not metrics['fallback'] and output.action.type=='offer_quest':
            result['execution']['offer_id']=offer(c,p,output.action.target_id)
        c.execute("INSERT INTO suggestion_jobs(pet_id,source_id,revision,status,result) VALUES(%s,%s,%s,'done',%s) ON CONFLICT(pet_id,source_id,revision) DO UPDATE SET status='done',result=EXCLUDED.result",
                  (pet,source_id,revision,Jsonb(result)))
        return result

@app.post('/pets/{pet}/quests/{offer_id}/decision')
def decide(pet:str,offer_id:str,body:Decision,user=Depends(identity)):
    with connect() as c:
        p=owned(c,user,pet,True)
        q=c.execute('SELECT * FROM quest_offers WHERE pet_id=%s AND id=%s',(pet,offer_id)).fetchone()
        if not q: raise HTTPException(404,'Offer not found')
        target='active' if body.decision=='accept' else 'rejected'
        if q['status']==target: return {'status':target,'duplicate':True}
        if q['status']!='offered' or q['expires_at']<now(): raise HTTPException(409,'Inactive or expired offer')
        if q['state_version']!=p['version']: raise HTTPException(409,'State changed; request a fresh offer')
        c.execute("UPDATE quest_offers SET status='expired' WHERE pet_id=%s AND status='active' AND expires_at<now()",(pet,))
        if target=='active' and c.execute("SELECT 1 FROM quest_offers WHERE pet_id=%s AND status='active'",(pet,)).fetchone():
            raise HTTPException(409,'Quest already active')
        c.execute('UPDATE quest_offers SET status=%s,accepted_at=%s WHERE pet_id=%s AND id=%s',(target,now() if target=='active' else None,pet,offer_id))
        version=bump(c,pet)
        return {'status':target,'state_version':version}

@app.post('/pets/{pet}/chat')
def chat(pet:str,body:ChatInput,user=Depends(identity)):
    try:
        with model_runtime.reserve('llm'):
            return chat_request(pet,body,user)
    except ModelBusy as error:
        raise HTTPException(503,str(error)) from error
    except TimeoutError as error:
        raise HTTPException(504,'Model request timed out; retry with the same request ID') from error
    except RuntimeError as error:
        raise HTTPException(503,'Model worker failed; retry with the same request ID') from error

def chat_request(pet,body,user):
    started=time.monotonic()
    fingerprint=hashlib.sha256(body.text.encode()).hexdigest()
    with connect() as c:
        p=owned(c,user,pet,True)
        request=c.execute('SELECT * FROM requests WHERE pet_id=%s AND id=%s',(pet,body.request_id)).fetchone()
        if request:
            if request['fingerprint']!=fingerprint: raise HTTPException(409,'Request ID reused with different text')
            if request['status']=='done': return request['result']
            if request['status']=='invalidated': raise HTTPException(410,'Cached response invalidated by correction/deletion')
            if request['status']=='running' and now()-request['started_at']<timedelta(minutes=5): raise HTTPException(409,'Request in progress')
        if body.state_version is not None and body.state_version!=p['version']: raise HTTPException(409,'State version conflict')
        c.execute("INSERT INTO requests(pet_id,id,fingerprint,status) VALUES(%s,%s,%s,'running') ON CONFLICT(pet_id,id) DO UPDATE SET status='running',started_at=now()",(pet,body.request_id,fingerprint))
        version=p['version']
    try:
        # No DB connection or row lock remains open during embedding/LLM generation.
        with connect() as c:
            p=owned(c,user,pet)
            if p['version']!=version: raise HTTPException(409,'State changed')
            state=current(c,p)
            recent=c.execute('''SELECT s.payload->>'text' AS "user",e.speech AS assistant FROM exchanges e JOIN sources s ON s.pet_id=e.pet_id AND s.id=e.source_id
              WHERE e.pet_id=%s AND e.valid AND s.valid ORDER BY e.created_at DESC LIMIT 6''',(pet,)).fetchall()[::-1]
            acts=[{'id':s['id'],'revision':s['revision'],**s['payload']} for s in sources(c,pet) if s['kind']=='activity'][-6:]
            local_today=now().astimezone(ZoneInfo(p['settings']['timezone'])).date()
            todays=[s for s in sources(c,pet) if s['kind']=='activity' and s['occurred_at'].astimezone(ZoneInfo(p['settings']['timezone'])).date()==local_today and s['payload']['kind']=='walk']
            activity_summary={'local_date':str(local_today),'timezone':p['settings']['timezone'],
                'has_walk_record':bool(todays),
                'confirmed_steps':sum(s['payload']['amount'] for s in todays if s['payload']['confirmed'] and s['payload']['source'] in ('backend','sensor')),
                'self_reported_steps':sum(s['payload']['amount'] for s in todays if s['payload']['source']=='user')}
            start,end,period=time_window(body.text,p['settings']['timezone'])
            scoped=[s for s in sources(c,pet) if s['kind']=='activity' and start<=s['occurred_at']<end]
            activity_summary['requested_period']={'label':period,'start':start.isoformat(),'end_exclusive':end.isoformat(),
                'record_count':len(scoped),'confirmed_steps':sum(s['payload']['amount'] for s in scoped if s['payload']['kind']=='walk' and s['payload']['confirmed'] and s['payload']['source'] in ('backend','sensor')),
                'evidence_refs':[{'id':s['id'],'revision':s['revision']} for s in scoped]}
            active=c.execute("SELECT id,template,progress FROM quest_offers WHERE pet_id=%s AND status='active' AND expires_at>now()",(pet,)).fetchall()
            quest_history=c.execute('SELECT id,template,status,progress FROM quest_offers WHERE pet_id=%s ORDER BY created_at DESC LIMIT 3',(pet,)).fetchall()
            reward=c.execute('SELECT COALESCE(SUM(amount),0) AS balance FROM reward_ledger WHERE pet_id=%s',(pet,)).fetchone()['balance']
            context={'settings':p['settings'],'traits':state['traits'],'mood':state['mood'],'recent':recent,
                     'memories':[],'activities':acts,'activity_summary':activity_summary,'candidates':candidates(c,p,body.text),'active_quests':active,
                     'quest_history':quest_history,'reward_balance':reward}
            forget_request=forget_target(c,pet,body.text)
            slot=durable_memory_slot(body.text) if forget_request is None else None
            lookup=forget_request is None and wants_memory_lookup(body.text,recent) and bool(c.execute('''
                SELECT 1 FROM memories m JOIN sources s ON s.pet_id=m.pet_id AND s.id=m.source_id
                WHERE m.pet_id=%s AND m.valid AND s.valid AND s.revision=m.source_revision
                  AND m.embedding IS NOT NULL LIMIT 1''',(pet,)).fetchone())
        # Ordinary chat and food facts already have their context. Load BGE only for
        # a durable memory write or a lookup that actually has valid stored vectors.
        embedding_started=time.monotonic()
        vec=vectorize(body.text) if slot or lookup else None
        embedding_seconds=time.monotonic()-embedding_started
        if lookup:
            with connect() as c:
                p=owned(c,user,pet)
                if p['version']!=version:raise HTTPException(409,'State changed during embedding')
                context['memories']=retrieve(c,pet,vec,query=body.text,recent=recent,for_chat=True)
        if forget_request is not None:
            speech='말한 취향이나 목표의 원본과 기억을 삭제했어.' if forget_request['target'] else '어떤 취향이나 목표를 지울지 구체적으로 알려 줄래?'
            if p['settings']['speech_level']=='formal':speech='말씀하신 취향이나 목표의 원본과 기억을 삭제했어요.' if forget_request['target'] else '어떤 취향이나 목표를 지울지 구체적으로 알려 주실래요?'
            out=ModelOutput(speech=speech,emotion='neutral',animation='idle',action=Action(),memory_ids=[])
            metrics={'attempts':0,'raw_valid':None,'repaired':False,'fallback':False,'errors':[],'latency_seconds':0,'handler':'authenticated_memory_command'}
        elif isinstance(backend,OnDemandQwen):out,metrics=backend.respond(context,body.text,owner=user,pet=pet)
        else:out,metrics=respond(backend,context,body.text)
        metrics.setdefault('timings',{}).update(embedding_seconds=embedding_seconds,
                                              embedding_loaded=vec is not None)
        with connect() as c:
            p=owned(c,user,pet,True)
            if p['version']!=version: raise HTTPException(409,'State changed during generation; retry')
            result={'schema_version':SCHEMA_VERSION,'request_id':body.request_id,'response':out.model_dump(),
                    'state_version':version,'state_used':state,'state_after':state,'execution':{},'metrics':metrics}
            if not metrics['fallback']:
                if forget_request and forget_request['target']:
                    target=forget_request['target']
                    c.execute("UPDATE sources SET valid=false,payload='{}',revision=revision+1 WHERE pet_id=%s AND id=%s AND revision=%s",(pet,target['source_id'],target['source_revision']))
                    invalidate(c,pet,target['source_id'],target['source_revision']+1)
                    result['execution']['deleted_memory_id']=target['id']
                last=c.execute("SELECT session_id,occurred_at FROM sources WHERE pet_id=%s AND kind='message' AND valid ORDER BY occurred_at DESC LIMIT 1",(pet,)).fetchone()
                session=last['session_id'] if last and now()-last['occurred_at']<timedelta(minutes=30) else uuid.uuid4().hex
                source_id='message:'+body.request_id
                c.execute("INSERT INTO sources(pet_id,id,kind,revision,occurred_at,session_id,payload) VALUES(%s,%s,'message',1,%s,%s,%s)",(pet,source_id,now(),session,Jsonb({'text':body.text})))
                # Explicit durable preferences/goals only. Never promote assistant text.
                if slot:
                    c.execute('UPDATE memories SET valid=false WHERE pet_id=%s AND slot=%s',(pet,slot))
                    mem_id=hashlib.sha256((source_id+':1').encode()).hexdigest()[:24]
                    c.execute('INSERT INTO memories(pet_id,id,source_id,source_revision,slot,content,embedding,embedding_revision) VALUES(%s,%s,%s,1,%s,%s,%s::vector,%s)',
                              (pet,mem_id,source_id,slot,body.text,str(vec),embedder.revision))
                state_after,new_version=refreshed(c,p); p['version']=new_version
                if out.action.type=='offer_quest': result['execution']['offer_id']=offer(c,p,out.action.target_id)
                result.update(source_id=source_id,source_revision=1,state_version=new_version,state_after=state_after)
                c.execute('INSERT INTO exchanges(pet_id,request_id,source_id,speech,memory_ids,state_used,state_after) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                          (pet,body.request_id,source_id,out.speech,Jsonb(out.memory_ids),Jsonb(state),Jsonb(state_after)))
            metrics['timings']['server_seconds']=time.monotonic()-started
            c.execute("UPDATE requests SET status='done',result=%s WHERE pet_id=%s AND id=%s",(Jsonb(result),pet,body.request_id))
        return result
    except Exception:
        with connect() as c:
            c.execute("UPDATE requests SET status='failed' WHERE pet_id=%s AND id=%s AND status='running'",(pet,body.request_id))
        raise

install_food(app, identity, refreshed, reconcile_quests, current)
install_beta(app,identity)
