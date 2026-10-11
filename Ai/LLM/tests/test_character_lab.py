"""Synthetic rule/API/SQLite tests. No dummy result is treated as Qwen output."""
import copy
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from src.character_lab_engine import execute, fresh, evolution
from src.character_lab_presets import preview, PRESETS
from src.character_lab_schema import CharacterState, RULES, ROOT
from src.character_lab_store import CharacterLabStore, Conflict
from src.persona_lab import create_app
from src.persona_runtime import PersonaRuntime
from src.persona_store import LabStore

ORIGIN = 'http://127.0.0.1:8001'
HEADERS = {'Origin': ORIGIN, 'X-Persona-Lab': '1'}


def cmd(kind, ident='event', **payload):
    return {'kind': kind, 'event_id': ident, 'payload': payload}


def apply(lab=None, kind='exercise', ident='event', **p):
    return execute(lab or fresh(), [cmd(kind, ident, **p)])


def label(**changes):
    return dict(target='exercise', sentiment='negative', motivation='low',
                character_affection='neutral', acceptance='none', analysis_confidence=1, **changes) if not changes else {
                    **label(), **changes}


@pytest.mark.parametrize('actual,expected', [(60,3),(50,2),(35,1),(20,0),(10,-1),(0,0)])
def test_exercise_thresholds_and_no_goal_no_penalty(actual, expected):
    r = apply(actual=actual, target=50, category='lower')
    assert r['after']['lower_body'] == 50+expected
    assert r['after']['upper_body'] == 50
    assert r['results'][0]['result']['achievement_rate'] == actual/50*100


def test_expired_goal_required_for_verified_zero():
    r=apply(actual=0,target=50,explicit_goal=True,due_date='2026-10-03')
    assert r['after']['lower_body']==48
    for p in ({'explicit_goal':False,'due_date':'2026-10-03'}, {'explicit_goal':True,'due_date':'2026-10-04'},
              {'explicit_goal':True,'due_date':'2026-10-03','verification_status':'unverified'}):
        assert apply(actual=0,target=50,**p)['after']['lower_body']==50


def test_full_body_split_and_sign_separated_daily_caps():
    r=apply(actual=50,target=50,category='full')
    assert r['after']['upper_body']==r['after']['lower_body']==51
    lab=fresh()
    for i in range(4):
        lab=apply(lab,ident=str(i),actual=60,target=50,category='upper')['session']
    assert lab['state']['upper_body']==53
    assert lab['logs'][-1]['result']['daily_cap_applied']
    for i in range(4):
        lab=apply(lab,ident='n'+str(i),actual=10,target=50,category='upper')['session']
    assert lab['state']['upper_body']==51


@pytest.mark.parametrize('bad', [0,-1,float('nan'),float('inf')])
def test_target_validation(bad):
    with pytest.raises(ValueError):
        apply(actual=50,target=bad)


@pytest.mark.parametrize('deviations,expected',[(0,2),(1,1),(2,0),(3,-1),(4,-2),(5,-2)])
def test_food_rules(deviations,expected):
    a=dict.fromkeys(('protein','carbohydrate','fat','vegetable','amount'),'proper')
    for k in list(a)[:deviations]: a[k]='low'
    r=apply(kind='food',analysis=a)
    assert r['after']['nutrition']==50+expected


@pytest.mark.parametrize('amount,severity,expected',[('low','normal',-2),('high','normal',2),('proper','normal',0),('low','extreme',-3),('high','extreme',3)])
def test_energy_rules(amount,severity,expected):
    a=dict.fromkeys(('protein','carbohydrate','fat','vegetable','amount'),'proper');a['amount']=amount
    assert apply(kind='food',analysis=a,amount_severity=severity)['after']['energy_balance']==expected


def test_unknown_food_requires_review_no_automatic_change():
    r=apply(kind='food',analysis={'amount':'high'})
    assert r['after']['nutrition']==50 and r['after']['energy_balance']==0
    assert r['results'][0]['result']['review_required']


def test_subject_and_low_confidence_protection():
    for text,a in [('운동하기 존나 싫다',label(character_affection='negative')),
                   ('존나 좋아!',label(sentiment='positive',motivation='high')),
                   ('너 귀찮아',label(target='character',character_affection='negative',analysis_confidence=0.59))]:
        r=apply(kind='conversation',text=text,analysis=a)
        assert not r['results'][0]['result']['relation_eligible']
        assert r['after']['affection']==50
    r=apply(kind='conversation',text='너 귀찮아',analysis=label(target='character',character_affection='negative'))
    assert r['results'][0]['result']['relation_eligible'] and r['after']['mood']==-5


def test_verified_behavior_priority_and_weekly_personality():
    successful=preview('exercise_7');inactive=preview('inactive_7');complaint=preview('exercise_profanity')
    assert successful['after']['activity']==53
    assert inactive['after']['activity']==49
    assert complaint['after']['activity']==48
    assert complaint['after']['affection']==52  # conversation frequency, no relationship penalty
    assert preview('positive_chat')['after']['affection']==53
    assert preview('reject_proposals')['after']['initiative']==48
    assert inactive['after']['initiative']==50


def test_low_confidence_excluded_from_weekly_relation_counts():
    lab=fresh()
    for i in range(7):
        lab=apply(lab,kind='conversation',ident=f'c{i}',text='너 싫어',analysis=label(target='character',character_affection='negative',analysis_confidence=0.5))['session']
        lab=apply(lab,kind='time',ident=f't{i}',action='advance')['session']
    r=apply(lab,kind='time',ident='weekly',action='weekly')
    assert r['results'][0]['result']['weekly']['conversation_days']==0
    assert r['after']['affection']==49  # inactivity baseline; not repeated-negative -2


def test_intention_never_creates_exercise_activity():
    lab=fresh()
    for i in range(7):
        lab=apply(lab,kind='conversation',ident=f'c{i}',text='매일 운동할 거야',analysis=label(sentiment='positive',motivation='high'))['session']
        lab=apply(lab,kind='time',ident=f't{i}',action='advance')['session']
    r=apply(lab,kind='time',ident='w',action='weekly')
    assert r['after']['activity']==49


@pytest.mark.parametrize('completed,total,delta',[(4,5,3),(3,5,2),(2,5,0),(1,5,-1),(0,5,-2)])
def test_initiative_uses_acceptance_and_actual_completion(completed,total,delta):
    lab=fresh()
    for i in range(total):
        q=f'q{i}'
        commands=[cmd('quest',q+'c',quest_id=q,verification_method='admin_verified')]
        if i<completed:
            commands += [cmd('quest',q+'a',quest_id=q,action='accept'),cmd('quest',q+'p',quest_id=q,action='progress',admin_verified=True),cmd('quest',q+'d',quest_id=q,action='complete',admin_verified=True)]
        else:
            commands += [cmd('quest',q+'r',quest_id=q,action='reject')]
        lab=execute(lab,commands)['session']
    lab=apply(lab,kind='time',ident='time',action='advance',days=7)['session']
    assert apply(lab,kind='time',ident='week',action='weekly')['after']['initiative']==50+delta


def test_weekly_idempotency_overlap_and_full_window():
    with pytest.raises(ValueError,match='complete seven'):
        apply(kind='time',action='weekly')
    lab=preview('exercise_7')['session']
    first=copy.deepcopy(lab['state'])
    r=apply(lab,kind='time',ident='second-update',action='weekly')
    assert r['after']==first and r['results'][0]['result']['weekly_duplicate_or_overlap']
    lab=apply(r['session'],kind='time',ident='advance',action='advance')['session']
    r=apply(lab,kind='time',ident='overlap',action='weekly')
    assert r['results'][0]['result']['weekly_duplicate_or_overlap']


def test_mood_caps_decay_once_and_system_time_unaffected():
    today=datetime.now().date()
    lab=fresh()
    for i in range(6):
        lab=apply(lab,kind='conversation',ident=str(i),text='네가 좋아',analysis=label(target='character',character_affection='positive',motivation='none'))['session']
    assert lab['state']['mood']==15
    r=apply(lab,kind='time',ident='time',action='advance')
    assert r['after']['mood']==10.5
    r=apply(r['session'],kind='time',ident='again',action='decay')
    assert r['after']['mood']==10.5 and datetime.now().date()==today
    lab=fresh()
    for i in range(6):lab=apply(lab,kind='conversation',ident=str(i),text='너 싫어',analysis=label(target='character',character_affection='negative'))['session']
    assert lab['state']['mood']==-15


def test_quest_evidence_transitions_and_reward_once():
    lab=execute(fresh(),[cmd('quest','create',quest_id='q'),cmd('quest','accept',quest_id='q',action='accept')])['session']
    with pytest.raises(ValueError,match='Insufficient'):
        apply(lab,kind='quest',quest_id='q',action='progress')
    with pytest.raises(ValueError,match='Invalid quest'):
        apply(lab,kind='quest',quest_id='q',action='complete')
    lab=apply(lab,ident='e',quest_id='q',actual=50,target=50)['session']
    lab=apply(lab,kind='quest',ident='p',quest_id='q',action='progress')['session']
    r=apply(lab,kind='quest',ident='done',quest_id='q',action='complete')
    assert r['after']['exp']==10 and r['session']['quests']['q']['reward_paid']
    assert apply(r['session'],kind='quest',ident='done',quest_id='q',action='complete')['after']==r['after']
    with pytest.raises(ValueError):apply(r['session'],kind='quest',ident='different-done',quest_id='q',action='complete')


def test_clamp_alias_legacy_preservation_and_level_never_decreases():
    s=CharacterState(upper_body=200,mood=-200,affinity=80,initiative=-5).model_dump()
    assert s['upper_body']==100 and s['mood']==-100 and s['affection']==80 and s['initiative']==0
    assert 'affinity' not in s and 'confidence' in s and 'curiosity' in s
    lab=fresh({'level':10,'exp':0})
    assert apply(lab,kind='manual_override',state=fresh()['state'])['after']['level']==10


def test_record_exp_levels_evolution_and_generation_required():
    s=fresh({'level':9,'exp':178,'upper_body':82,'lower_body':79,'nutrition':80,'energy_balance':5})
    r=apply(s,actual=50,target=50)
    assert r['after']['level']==10 and r['after']['evolution_stage']==1
    assert r['after']['body_type']=='balanced_exercise'
    assert not evolution(r['after'])['generation_required']
    assert preview('evolution_fat')['after']['body_type']=='fat_gain'
    assert preview('evolution_recovery')['after']['body_type']=='recovered'
    lab=preview('evolution_recovery')['session']
    assert not apply(lab,kind='evolution',ident='repeat',apply=True)['evolution']['generation_required']


def test_response_context_preserves_actual_records_and_catalog_successes():
    from src.character_lab_models import response_context
    lab=fresh()
    for i in range(2):
        q=f'walk-{i}'
        day=lab['state']['virtual_test_date']
        commands=[cmd('quest',q+'c',quest_id=q,target='walk',target_value=100,unit='step'),
                  cmd('quest',q+'a',quest_id=q,action='accept'),
                  cmd('exercise',q+'e',quest_id=q,exercise_type='walk',actual=100,target=100,unit='step'),
                  cmd('quest',q+'p',quest_id=q,action='progress'),
                  cmd('quest',q+'d',quest_id=q,action='complete'),
                  cmd('time',q+'t',action='advance')]
        lab=execute(lab,commands)['session']
    state=dict(lab['state'],activity=85,initiative=80)
    context=response_context(lab,state,'운동 퀘스트 추천해 줘',[],'casual')
    assert len(context['activities'])==2 and len(context['completed_quests'])==2
    assert context['activity_summary']['last_7_days']['confirmed_steps']==200
    assert context['candidates'][0]['difficulty']==2


@pytest.mark.parametrize('target,previous_food,record_name,verified_completion', [
    ('food_record', 'Previous meal', 'Current meal', True),
    ('new_food', 'Previous meal', 'Current meal', True),
    ('new_food', 'Same meal', 'Same meal', False),
    ('food_record', None, '', False),
])
def test_food_quest_projection_preserves_evidence_and_catalog_validation(
        target, previous_food, record_name, verified_completion):
    from src.character_lab_models import history_projection
    from src.persona_quests import explain_selection, validate_quest_evidence, catalog_by_id
    analysis = dict(protein='proper', carbohydrate='proper', fat='proper',
                    vegetable='proper', amount='proper', analysis_confidence=1)
    commands = []
    if previous_food:
        commands.append(cmd('food', 'before-accept', raw_text=previous_food, analysis=analysis))
    commands.extend([
        cmd('quest', 'create-food', quest_id='food-test', quest_type='food', target=target,
            target_value=1, unit='record', verification_method='food_record'),
        cmd('quest', 'accept-food', quest_id='food-test', action='accept'),
        cmd('food', 'unknown-food', raw_text='Unknown meal', analysis={}),
        cmd('food', 'food-evidence', raw_text=record_name, analysis=analysis),
        cmd('quest', 'progress-food', quest_id='food-test', action='progress'),
        cmd('quest', 'complete-food', quest_id='food-test', action='complete'),
        cmd('time', 'after-cooldown', action='advance', days=2),
    ])
    lab = execute(fresh(), commands)['session']
    before_projection = copy.deepcopy(lab)
    history = history_projection(lab)
    completion = next(row for row in history if row['event_type'] == 'quest_completed')
    assert completion['payload']['evidence_event_ids'] == ['food-evidence']
    assert 'unknown-food' not in {row['event_id'] for row in history}
    evidence = [row for row in history if row['event_id'] == 'food-evidence']
    earlier = [row for row in history if row['event_id'] == 'before-accept']
    catalog_id = 'food_record_1' if target == 'food_record' else 'new_food_1'
    assert validate_quest_evidence(catalog_by_id()[catalog_id], evidence, earlier) == verified_completion
    state = {'personality': {axis: lab['state'][axis] for axis in
                            ('activity', 'affection', 'curiosity', 'confidence')},
             'short_term': {'mood': 'neutral', 'energy': 70, 'recent_stress': 0, 'recent_motivation': 50}}
    selected = explain_selection(state, history,
                                datetime.fromisoformat(lab['state']['virtual_test_date'] + 'T23:59:59+09:00'),
                                limit=20)
    assert (catalog_id in {q['quest_id'] for q in selected['selected']}) == verified_completion
    assert lab == before_projection


def test_every_preset_traceable_and_dry_run():
    for name in PRESETS:
        r=preview(name)
        assert r['dry_run'] and not r['production_write'] and not r['training_data']
        assert r['commands'] and r['timeline'] and r['session']['logs']


def test_manual_virtual_date_override_and_model_provenance():
    r=apply(kind='manual_override',state={**fresh()['state'],'virtual_test_date':'2026-11-01'})
    assert r['after']['virtual_test_date']=='2026-11-01'
    r=apply(r['session'],kind='conversation',ident='c',text='운동하기 싫다',analysis=label(),
            model_identifier='manual-test-source',prompt_version='test.v1')
    assert r['results'][0]['model_identifier']=='manual-test-source'
    assert r['results'][0]['prompt_version']=='test.v1'


def test_export_actual_local_tokenizer_and_shared_converter(client):
    from transformers import AutoTokenizer
    from scripts.convert_character_dataset import convert_row
    from src.character_lab_models import CONVERSATION_SYSTEM
    from src.contracts import ModelOutput
    tokenizer=AutoTokenizer.from_pretrained(ROOT/'models/qwen3.5-9b',local_files_only=True)
    c,store=client
    a=post(c,'/conversation/analyze',{'text':'운동하기 싫다','mode':'manual','label':label()})
    post(c,'/reviews',{**a['review'],'status':'approved'})
    analysis=json.loads(store.export('analyzer'))
    encoded=convert_row(analysis,'analyzer',tokenizer)
    assert all(x==-100 for x in encoded['labels'][:encoded['prompt_tokens']])
    assert all(x!=-100 for x in encoded['labels'][encoded['prompt_tokens']:])
    assert 'speech' not in json.loads(encoded['messages'][-1]['content'])
    row={'sample_id':'controlled-response-test','reviewer_status':'corrected','prompt_version':'test',
         'prompt':[{'role':'system','content':'JSON speech 객체만 출력한다.'},{'role':'user','content':'오늘은 쉴래'}],
         'response_contract':ModelOutput(speech='fixture',emotion='neutral',animation='idle',
                                         action={'type':'none','target_id':None},memory_ids=[]).model_dump(),
         'response':'오늘은 편하게 쉬자.'}
    encoded=convert_row(row,'response',tokenizer)
    target=json.loads(encoded['messages'][-1]['content'])
    assert target['speech']=='오늘은 편하게 쉬자.' and 'target' not in target and 'analysis_confidence' not in target


def test_sqlite_migration_apply_rollback_reapply(tmp_path):
    path=tmp_path/'migration.sqlite3'
    with sqlite3.connect(path) as c:
        c.execute('CREATE TABLE original(x TEXT)');c.execute("INSERT INTO original VALUES('preserved')")
        c.executescript((ROOT/'migrations/character_lab/001_up.sql').read_text())
        c.executescript((ROOT/'migrations/character_lab/001_down.sql').read_text())
        assert c.execute('SELECT x FROM original').fetchone()[0]=='preserved'
        c.executescript((ROOT/'migrations/character_lab/001_up.sql').read_text())
        c.executescript((ROOT/'migrations/character_lab/001_up.sql').read_text())
        assert c.execute('SELECT COUNT(*) FROM character_lab_schema_version').fetchone()[0]==1


def test_store_transaction_conflict_and_isolation(tmp_path):
    store=CharacterLabStore(tmp_path/'test.sqlite3')
    with pytest.raises(ValueError):store.read('real-pet-id')
    assert not store.path.exists()
    r=store.create();ident=r['session_id']
    r=store.run(ident,[cmd('exercise','one',actual=50,target=50)],0)
    with pytest.raises(Conflict):store.run(ident,[cmd('exercise','two',actual=50,target=50)],0)
    with pytest.raises(ValueError):store.run(ident,[cmd('exercise','two',actual=50,target=50),cmd('exercise','one',actual=60,target=50)],1)
    assert len(store.read(ident)['session']['events'])==1


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('APP_ENV','development');monkeypatch.setenv('PERSONA_LAB_ENABLED','1')
    monkeypatch.delenv('ENVIRONMENT',raising=False);monkeypatch.delenv('NODE_ENV',raising=False)
    import src.db
    monkeypatch.setattr(src.db,'connect',lambda:pytest.fail('Character Lab must not connect to production PostgreSQL'))
    runtime=PersonaRuntime();monkeypatch.setattr(runtime,'_load',lambda:pytest.fail('Unit suite must not use Qwen'))
    application=create_app(runtime,LabStore(tmp_path/'isolated.sqlite3'))
    with TestClient(application,base_url=ORIGIN,client=('127.0.0.1',30000)) as c:
        yield c,application.state.character_lab_store


def post(c,path,body):
    r=c.post('/dev/character-lab'+path,json=body,headers=HEADERS)
    assert r.status_code==200,r.text
    return r.json()


def test_api_dry_run_no_database_writes_and_commit_namespace(client):
    c,store=client
    post(c,'/exercise',{'commands':[cmd('exercise',actual=50,target=50)]})
    post(c,'/presets',{'name':'exercise_7'})
    assert not store.path.exists()
    s=post(c,'/sessions',{})
    digest=hashlib.sha256(store.path.read_bytes()).hexdigest()
    post(c,'/run',{'session_id':s['session_id'],'commands':[cmd('exercise',actual=50,target=50)]})
    assert hashlib.sha256(store.path.read_bytes()).hexdigest()==digest
    committed=post(c,'/run',{'session_id':s['session_id'],'expected_revision':0,'dry_run':False,'commands':[cmd('exercise',actual=50,target=50)]})
    assert committed['target']==s['session_id'] and committed['namespace']=='character-lab-test'
    assert c.post('/dev/character-lab/run',json={'session_id':'real-pet','dry_run':False},headers=HEADERS).status_code==422


def test_analyzer_and_responder_separation_dummy_no_store(client):
    c,store=client
    a=post(c,'/conversation/analyze',{'text':'운동하기 싫다','mode':'dummy'})
    assert a['output_origin']=='dummy' and not a['is_real_model']
    r=post(c,'/conversation/respond',{'text':'오늘 뭘 해볼까?','mode':'dummy','a':{'activity':85,'initiative':80},'b':{'activity':25,'initiative':25}})
    assert r['contexts']['a']['memories']==r['contexts']['b']['memories']
    assert r['contexts']['a']['active_quests']==r['contexts']['b']['active_quests']
    assert r['contexts']['a']['style_profile']!=r['contexts']['b']['style_profile']
    assert r['contexts']['a']['agent_policy']!=r['contexts']['b']['agent_policy']
    assert r['contexts']['a']['candidates'] and not r['contexts']['b']['candidates']
    assert not store.path.exists()


def test_corrected_analysis_reviews_and_export_filters(client):
    c,store=client
    a=post(c,'/conversation/analyze',{'text':'운동하기 존나 싫다','mode':'manual','label':label(character_affection='negative')})
    r=post(c,'/reviews',{**a['review'],'status':'corrected','corrected_label':label(),'reviewer_note':'automated synthetic test; not human approval'})
    rows=store.reviews();assert rows[0]['correction']['character_affection']=='neutral'
    exported=c.get('/dev/character-lab/export?kind=analyzer').text
    assert json.loads(exported)['label']['character_affection']=='neutral'
    post(c,'/reviews',{**a['review'],'expected_revision':r['revision'],'status':'excluded'})
    assert c.get('/dev/character-lab/export?kind=analyzer').text==''
    for status in ('pending','approved'):
        a=post(c,'/conversation/analyze',{'text':'dummy','mode':'dummy'})
        post(c,'/reviews',{**a['review'],'status':status})
    assert c.get('/dev/character-lab/export?kind=analyzer').text==''


def test_corrected_response_persistence_and_export_without_mock_claim(client):
    c,store=client
    r=post(c,'/conversation/respond',{'text':'오늘 쉬고 싶어','mode':'dummy'})
    post(c,'/reviews',{**r['reviews']['a'],'status':'corrected','corrected_response':'오늘은 편하게 쉬자.'})
    assert store.reviews()[0]['correction']=='오늘은 편하게 쉬자.'
    assert c.get('/dev/character-lab/export?kind=response').text=='' # dummy never trains
    # Injected fixture tests the writer format only, explicitly a controlled test origin.
    d=copy.deepcopy(r['reviews']['a']['draft']);d['id']='fixture';d['output_origin']='controlled_test_fixture'
    store.save_review(d,'corrected','오늘은 편하게 쉬자.','automated fixture; not Qwen')
    assert json.loads(store.export('response'))['response']=='오늘은 편하게 쉬자.'


def test_tampered_prediction_and_missing_correction_rejected(client):
    c,_=client
    a=post(c,'/conversation/analyze',{'text':'분석','mode':'dummy'})
    altered=copy.deepcopy(a['review']);altered['draft']['model_identifier']='fake-real-qwen'
    assert c.post('/dev/character-lab/reviews',json={**altered,'status':'approved'},headers=HEADERS).status_code==422
    assert c.post('/dev/character-lab/reviews',json={**a['review'],'status':'corrected'},headers=HEADERS).status_code==422


def test_browser_integer_float_round_trip_review_signatures(client):
    from src.character_lab_schema import canonical_json
    c,_=client
    a=post(c,'/conversation/analyze',{'text':'운동하기 싫다','mode':'manual','label':label()})
    bundle=json.loads(canonical_json(a['review']))
    r=post(c,'/reviews',{**bundle,'status':'corrected','corrected_label':label()})
    post(c,'/reviews',{**bundle,'expected_revision':r['revision'],'status':'excluded'})
    responses=post(c,'/conversation/respond',{'text':'테스트','mode':'dummy'})
    bundle=json.loads(canonical_json(responses['reviews']['a']))
    post(c,'/reviews',{**bundle,'status':'corrected','corrected_response':'브라우저 숫자 round-trip fixture'})


@pytest.mark.parametrize('env,value',[('APP_ENV','production'),('ENVIRONMENT','prod'),('NODE_ENV','production'),('PERSONA_LAB_ENABLED','0')])
def test_production_all_character_routes_disabled(client,monkeypatch,env,value):
    c,_=client;monkeypatch.setenv(env,value)
    for path in ('/state','/presets','/reviews','/export?kind=analyzer'):
        assert c.get('/dev/character-lab'+path).status_code==404
    assert c.post('/dev/character-lab/run',json={},headers=HEADERS).status_code==404
