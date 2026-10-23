"""CPU-only starter provisioning, ownership and evolution handover with real PG."""
import hashlib
import json
import struct

import pytest
from fastapi import HTTPException
from psycopg.types.json import Jsonb

from Server.healthmon import rules,service,starters


def test_packaged_starter_bootstraps_new_environment_and_survives_restart(settings,db):
    from dataclasses import replace
    from pathlib import Path
    from fastapi.testclient import TestClient
    from Server.healthmon.app import create_app
    path=Path(__file__).resolve().parents[1]/'assets/starter/lucan/manifest.json'
    config=replace(settings,starter_manifest=path)
    asset_hash='77a7b4d49b6561b7d20206d1c1a405b90e160005a69c81decc806cf9452d269d'
    references=[]
    for _ in range(2):
        with TestClient(create_app(config,db)) as api:
            api.headers['Authorization']='Bearer test-owner-a-token'
            created=api.post('/pets',json={'name':'배포 초기종'});assert created.status_code==200
            state=created.json()['state'];assert state['published_model_stage']==0 and state['asset_status']=='ready'
            asset=api.get(state['model_reference']);assert asset.status_code==200
            assert len(asset.content)==6966452 and hashlib.sha256(asset.content).hexdigest()==asset_hash
            references.append(state['model_reference'].split('/')[-1])
    assert references[0]==references[1]
    with db.connect() as c:
        assert c.execute('SELECT count(*) AS n FROM starter_models').fetchone()['n']==1
        assert c.execute('SELECT count(*) AS n FROM ai_jobs').fetchone()['n']==0


def test_packaged_bootstrap_preserves_operator_default_and_existing_pet(settings,db,tmp_path):
    from dataclasses import replace
    from pathlib import Path
    from fastapi.testclient import TestClient
    from Server.healthmon.app import create_app
    path,_=files(tmp_path)
    with db.connect() as c:chosen=starters.register(c,path,set_default=True)
    packaged=Path(__file__).resolve().parents[1]/'assets/starter/lucan/manifest.json'
    with TestClient(create_app(replace(settings,starter_manifest=packaged),db)) as api:
        api.headers['Authorization']='Bearer test-owner-a-token'
        state=api.post('/pets',json={'name':'기존 선택 유지'}).json()['state']
        assert state['model_reference'].endswith(chosen['starter_id'])
    with db.connect() as c:assert c.execute('SELECT count(*) AS n FROM starter_models').fetchone()['n']==1


def files(tmp_path,species='lucan',variant=0):
    folder=tmp_path/species;folder.mkdir(exist_ok=True)
    doc={'asset':{'version':'2.0','generator':str(variant)},'skins':[{'joints':[0]}],
         'meshes':[{'primitives':[{'attributes':{'JOINTS_0':0,'WEIGHTS_0':1}}]}],
         'nodes':[{'mesh':0,'skin':0}],'images':[{'bufferView':0}],'buffers':[{'byteLength':0}]}
    raw=json.dumps(doc).encode();raw+=b' '*((-len(raw))%4)
    model=struct.pack('<4sIIII',b'glTF',2,20+len(raw),len(raw),0x4E4F534A)+raw
    image=b'\x89PNG\r\n\x1a\nControlled image provenance fixture, no image/model inference'
    (folder/'model.glb').write_bytes(model);(folder/'image.png').write_bytes(image)
    manifest={'stage':0,'species':species,'model_sha256':hashlib.sha256(model).hexdigest(),
              'image_sha256':hashlib.sha256(image).hexdigest()}
    path=folder/'manifest.json';path.write_text(json.dumps(manifest),encoding='utf-8')
    return path,model


def test_configured_starter_is_available_immediately_without_ai_or_evolution_job(client,db,tmp_path):
    path,model=files(tmp_path)
    with db.connect() as c:registered=starters.register(c,path,set_default=True)
    created=client.post('/pets',json={'name':'초기종'});assert created.status_code==200,created.text
    body=created.json();pet=body['pet_id'];state=body['state']
    assert state['level']==1 and state['published_model_stage']==0 and state['evolution_target_stage']==0
    assert state['asset_status']=='ready' and state['previous_evolution'] is None
    assert state['model_reference']==f"/pets/{pet}/assets/{registered['starter_id']}"
    assert client.get(f'/pets/{pet}/state').json()['state_version']==body['state_version']
    response=client.get(state['model_reference']);assert response.status_code==200 and response.content==model
    assert response.headers['etag']==registered['model_sha256']
    manifest=client.get(f"/pets/{pet}/evolutions/{registered['starter_id']}").json()
    assert manifest['stage']==0 and manifest['status']=='succeeded' and manifest['new_generation'] is False
    assert manifest['state_version']==body['state_version'] and manifest['model_url']==state['model_reference']
    with db.connect() as c:
        assert c.execute('SELECT count(*) AS n FROM ai_jobs WHERE pet_id=%s',(pet,)).fetchone()['n']==0
        assert c.execute('SELECT count(*) AS n FROM model_assets').fetchone()['n']==0
        assert c.execute('SELECT count(*) AS n FROM starter_models').fetchone()['n']==1


def test_starter_download_is_owner_and_pet_scoped(client,db,tmp_path):
    path,_=files(tmp_path)
    with db.connect() as c:registered=starters.register(c,path,set_default=True)
    pet=client.post('/pets',json={'name':'소유자A'}).json()['pet_id'];ident=registered['starter_id']
    for endpoint in (f'/pets/{pet}/assets/{ident}',f'/pets/{pet}/evolutions/{ident}'):
        assert client.get(endpoint,headers={'Authorization':'Bearer test-owner-b-token'}).status_code==404
        assert client.get(endpoint,headers={'Authorization':''}).status_code==401
    with db.connect() as c:c.execute('DELETE FROM starter_model_default')
    unbound=client.post('/pets',json={'name':'연결없음'}).json()['pet_id']
    assert client.get(f'/pets/{unbound}/assets/{ident}').status_code==404
    assert client.get(f'/pets/{unbound}/evolutions/{ident}').status_code==404


def test_existing_pet_without_model_gets_starter_when_default_becomes_available(client,db,tmp_path):
    pet=client.post('/pets',json={'name':'기존 캐릭터'}).json()['pet_id']
    initial=client.get(f'/pets/{pet}/state').json()
    assert initial['model_reference'] is None
    path,model=files(tmp_path)
    with db.connect() as c:registered=starters.register(c,path,set_default=True)
    recovered=client.get(f'/pets/{pet}/state').json()
    assert recovered['model_reference']==f"/pets/{pet}/assets/{registered['starter_id']}"
    assert recovered['asset_status']=='ready'
    for key in ('level','total_exp','coin','published_model_stage','evolution_target_stage'):
        assert recovered[key]==initial[key]
    assert client.get(recovered['model_reference']).content==model
    assert client.get(f'/pets/{pet}/state').json()['state_version']==recovered['state_version']
    with db.connect() as c:
        assert c.execute('SELECT count(*) AS n FROM pet_starter_models WHERE pet_id=%s',(pet,)).fetchone()['n']==1
        assert c.execute('SELECT count(*) AS n FROM ai_jobs WHERE pet_id=%s',(pet,)).fetchone()['n']==0


def test_default_update_does_not_replace_existing_pet_starter_or_copy_blob(client,db,tmp_path):
    first,_=files(tmp_path,'lucan',0)
    with db.connect() as c:a=starters.register(c,first,set_default=True)
    p1=client.post('/pets',json={'name':'first'}).json()['pet_id']
    second,_=files(tmp_path,'mora',1)
    with db.connect() as c:b=starters.register(c,second,set_default=True)
    p2=client.post('/pets',json={'name':'second'}).json()['pet_id']
    p3=client.post('/pets',json={'name':'third'}).json()['pet_id']
    assert client.get(f'/pets/{p1}/state').json()['model_reference'].endswith(a['starter_id'])
    for pet in (p2,p3):assert client.get(f'/pets/{pet}/state').json()['model_reference'].endswith(b['starter_id'])
    with db.connect() as c:
        assert c.execute('SELECT count(*) AS n FROM starter_models').fetchone()['n']==2
        assert c.execute('SELECT count(*) AS n FROM pet_starter_models').fetchone()['n']==3


@pytest.mark.parametrize('mutation',('model','image','stage'))
def test_provisioning_rejects_modified_files_or_nonzero_stage_atomically(client,db,tmp_path,mutation):
    path,_=files(tmp_path)
    if mutation=='stage':
        data=json.loads(path.read_text());data['stage']=1;path.write_text(json.dumps(data))
    else:(path.parent/('model.glb' if mutation=='model' else 'image.png')).write_bytes(b'modified')
    with pytest.raises(ValueError):
        with db.connect() as c:starters.register(c,path,set_default=True)
    with db.connect() as c:assert c.execute('SELECT count(*) AS n FROM starter_models').fetchone()['n']==0


def test_starter_retained_during_pending_evolution_and_cannot_replace_evolved_asset(client,db,tmp_path):
    path,_=files(tmp_path)
    with db.connect() as c:registered=starters.register(c,path,set_default=True)
    pet=client.post('/pets',json={'name':'성장'}).json()['pet_id']
    with db.connect() as c:
        exp=sum(rules.required_exp(v) for v in range(1,10))
        c.execute('INSERT INTO game_ledger(pet_id,reward_key,exp,coin,reason) VALUES(%s,%s,%s,0,%s)',(pet,'fixture',exp,'synthetic test'))
    state=client.get(f'/pets/{pet}/state').json()
    assert state['evolution_target_stage']==1 and state['published_model_stage']==0
    assert state['model_reference'].endswith(registered['starter_id'])
    assert client.post(f'/pets/{pet}/evolutions',json={'request_id':'actual-pending'}).status_code==200
    assert client.get(state['model_reference']).status_code==200
    with db.connect() as c:
        c.execute('DELETE FROM pet_starter_models WHERE pet_id=%s',(pet,))
        changed=dict(state,published_model_stage=1,model_reference=f'/pets/{pet}/assets/new-model',asset_status='ready')
        c.execute('UPDATE game_states SET state=%s WHERE pet_id=%s',(Jsonb(changed),pet))
    with pytest.raises(HTTPException) as raised:
        with db.connect() as c:starters.bind_default(c,service.owned(c,'owner-a',pet,True),service.utcnow())
    assert raised.value.status_code==409


def test_pet_deletion_keeps_shared_starter_but_removes_access(client,db,tmp_path):
    path,_=files(tmp_path)
    with db.connect() as c:registered=starters.register(c,path,set_default=True)
    pet=client.post('/pets',json={'name':'삭제'}).json()['pet_id']
    assert client.delete(f'/pets/{pet}').status_code==200
    assert client.get(f"/pets/{pet}/assets/{registered['starter_id']}").status_code==404
    with db.connect() as c:
        assert c.execute('SELECT count(*) AS n FROM starter_models').fetchone()['n']==1
        assert c.execute('SELECT count(*) AS n FROM pet_starter_models').fetchone()['n']==0


def test_first_evolution_transports_exact_registered_parent_and_ai_binds_it_automatically(client,db,tmp_path):
    from Ai.Generation3D.runtime.common_gateway.contracts import validate_request
    from Ai.Generation3D.runtime.common_gateway.store import Store
    path,_=files(tmp_path)
    with db.connect() as c:registered=starters.register(c,path,set_default=True)
    pet=client.post('/pets',json={'name':'자동 부모 연결'}).json()['pet_id']
    with db.connect() as c:
        exp=sum(rules.required_exp(v) for v in range(1,10))
        c.execute('INSERT INTO game_ledger(pet_id,reward_key,exp,coin,reason) VALUES(%s,%s,%s,0,%s)',(pet,'fixture',exp,'synthetic test'))
    queued=client.post(f'/pets/{pet}/evolutions',json={'request_id':'auto-parent'}).json()
    with db.connect() as c:job=c.execute('SELECT * FROM ai_jobs WHERE id=%s',(queued['job_id'],)).fetchone()
    body={'contract_version':'healthmon.ai.v1','request_id':job['id'],'pet_id':pet,'input':job['input']}
    validate_request(job['id'],body)
    parent=body['input']['parent_asset']
    assert parent['revision']==registered['starter_id'] and parent['model_sha256']==registered['model_sha256']
    assert parent['stage']==0 and parent['source_kind']=='common_server_verified_starter'
    store=Store(tmp_path/'isolated-ai-journal')
    assert store.parent(pet) is None
    remote=store.submit(job['id'],body,frozenset({1,2,3}))
    assert remote['status']=='queued'
    bound=store.parent(pet)
    assert bound['revision']==registered['starter_id']
    assert (store.root/bound['image_relative']).read_bytes()==(path.parent/'image.png').read_bytes()
    assert store.submit(job['id'],body,frozenset({1,2,3}))['fingerprint']==remote['fingerprint']


def test_existing_ai_parent_cannot_be_replaced_by_another_server_starter(client,db,tmp_path):
    from Ai.Generation3D.runtime.common_gateway.store import Store,Conflict
    path,_=files(tmp_path)
    with db.connect() as c:starters.register(c,path,set_default=True)
    pet=client.post('/pets',json={'name':'기존 부모 보호'}).json()['pet_id']
    with db.connect() as c:parent=starters.parent_asset(c,pet)
    store=Store(tmp_path/'isolated-ai')
    wrong={k:parent[k] for k in ('stage','revision','species','image_sha256','model_sha256')}
    wrong.update(image_relative='parents/existing.png',model_sha256='f'*64)
    store.bind_parent(pet,wrong)
    body={'pet_id':pet,'input':{'stage':1,'state':{'published_model_stage':0},'parent_asset':parent}}
    with pytest.raises(Conflict):store.submit('different-parent',body,frozenset({1,2,3}))
    assert store.parent(pet)==wrong
    with store.connect() as c:assert c.execute('SELECT count(*) FROM jobs').fetchone()[0]==0


@pytest.mark.parametrize('change',('image','hash','stage','encoded_limit'))
def test_corrupted_or_oversized_starter_transport_fails_before_binding(client,db,tmp_path,change):
    from Ai.Generation3D.runtime.common_gateway.store import Store
    path,_=files(tmp_path)
    with db.connect() as c:starters.register(c,path,set_default=True)
    pet=client.post('/pets',json={'name':'부모 무결성'}).json()['pet_id']
    with db.connect() as c:parent=starters.parent_asset(c,pet)
    if change=='image':parent['image_base64']='not base64'
    if change=='hash':parent['image_sha256']='0'*64
    if change=='stage':parent['stage']=False
    if change=='encoded_limit':parent['image_base64']='A'*1398105
    store=Store(tmp_path/'isolated-ai')
    body={'pet_id':pet,'input':{'stage':1,'state':{'published_model_stage':0},'parent_asset':parent}}
    with pytest.raises(ValueError):store.submit('bad-starter',body,frozenset({1,2,3}))
    assert store.parent(pet) is None
    assert not (store.root/'parents').exists()
