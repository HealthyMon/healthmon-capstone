"""CPU-only adapter contracts. No model loading, Docker execution or generated assets."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import importlib.util
import json
import sys
import subprocess
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from Server.healthmon import rules
from Ai.Generation3D.runtime.common_gateway.contracts import validate_request
from Ai.Generation3D.runtime.common_gateway.service import Settings,create_app
from Ai.Generation3D.runtime.common_gateway.store import Store,Conflict
from Ai.Generation3D.runtime.common_gateway.worker import docker_command,run_once
from Ai.Generation3D.src.healthmon.individual_evolution import compile_individual
from Ai.Generation3D.runtime.common_gateway.appearance import BODY_CONDITIONS,body_condition,apply_to_prompt


def request(stage=1,published=0,pet='adapter-test-pet'):
    level=(0,10,20,30)[stage]
    total=sum(rules.required_exp(v) for v in range(1,level))
    state={**rules.initial_state(),**rules.exp_progress(total),'pet_id':pet,'state_version':7,
           'published_model_stage':published}
    profile=rules.evolution_profile(state)
    return {'contract_version':'healthmon.ai.v1','request_id':'stable-fixture-id','pet_id':pet,
            'input':{'stage':stage,'state':state,'profile':profile,'rule_version':rules.RULE_VERSION,
                     'adapter_version':'healthmon.evolution.v2.2','source_contract':'new_common_gateway_contract',
                     'legacy_compatibility':{'original_energy_balance':0,'energy_balance_normalized':0,
                                             'mood':None,'stage_skip_requires_explicit_support':True}}}


def fixture_parent(stage=0):
    # Deliberately no mesh: this fixture checks only CPU contract/job durability.
    return {'stage':stage,'revision':'historical-fixture','species':'lucan','species_contract':None,
            'image_sha256':'a'*64,'model_sha256':'b'*64,'image_relative':'parents/fixture.png',
            'source_kind':'historical_parent'}


@pytest.fixture
def adapter(tmp_path):
    settings=Settings(tmp_path/'isolated-ai-journal','adapter-contract-fixture')
    store=Store(settings.work_root)
    store.bind_parent('adapter-test-pet',fixture_parent())
    with TestClient(create_app(settings,store)) as client:
        client.headers['Authorization']='Bearer adapter-contract-fixture'
        yield client,store,settings


def test_put_get_is_durable_frozen_and_never_launches_gpu(adapter):
    client,store,settings=adapter
    body=request()
    first=client.put('/v1/evolutions/stable-fixture-id',json=body)
    assert first.status_code==200,first.text
    assert first.json()['result']['status']=='queued'
    assert first.json()['result']['model_url'] is None
    assert client.put('/v1/evolutions/stable-fixture-id',json=body).json()==first.json()
    body['input']['state']['upper_body']=99
    assert store.get('stable-fixture-id')['input']['input']['state']['upper_body']==50
    restarted=TestClient(create_app(settings,Store(settings.work_root)))
    with restarted:
        restarted.headers['Authorization']='Bearer adapter-contract-fixture'
        assert restarted.get('/v1/evolutions/stable-fixture-id').json()==first.json()
    assert client.get('/health').json()['gpu_worker_started'] is False
    assert not (settings.work_root/'work').exists()
    assert client.get('/v1/assets/stable-fixture-id/model.glb').status_code==404


def test_concurrent_same_id_and_conflicting_payload(adapter):
    client,store,_=adapter
    body=request()
    with ThreadPoolExecutor(max_workers=5) as executor:
        result=list(executor.map(lambda _:client.put('/v1/evolutions/stable-fixture-id',json=body),range(10)))
    assert all(r.status_code==200 for r in result)
    changed=deepcopy(body)
    changed['input']['state']['upper_body']=70
    changed['input']['profile']=rules.evolution_profile(changed['input']['state'])
    assert client.put('/v1/evolutions/stable-fixture-id',json=changed).status_code==409
    assert store.get('stable-fixture-id')['input']==body


@pytest.mark.parametrize('mutation',[
    lambda b:b['input']['state'].update(Mood=50),
    lambda b:b['input']['state'].update(lower_body=None),
    lambda b:b['input']['state'].update(upper_body=True),
    lambda b:b['input']['state'].update(level=9),
    lambda b:b['input']['profile'].update(appearance='adipose'),
    lambda b:b['input']['legacy_compatibility'].update(mood=50),
    lambda b:b.update(request_id='another-id'),
])
def test_invalid_or_fabricated_state_is_rejected(adapter,mutation):
    client,_,_=adapter
    body=request();mutation(body)
    assert client.put('/v1/evolutions/stable-fixture-id',json=body).status_code==422


def test_unverified_stage_and_skipped_stage_are_explicitly_unsupported(tmp_path):
    for stage,published,supported,error in [(2,1,{1},'stage_not_validated_by_this_adapter'),(3,0,{1,2,3},'stage_skip_not_supported')]:
        store=Store(tmp_path/str(stage));store.bind_parent('adapter-test-pet',fixture_parent(published))
        settings=Settings(store.root,'fixture',frozenset(supported))
        with TestClient(create_app(settings,store)) as client:
            response=client.put('/v1/evolutions/stable-fixture-id',json=request(stage,published),headers={'Authorization':'Bearer fixture'})
            assert response.status_code==200,response.text
            assert response.json()['result']['status']=='unsupported'
            assert response.json()['result']['error']==error
            assert response.json()['result']['model_url'] is None


def test_default_adapter_accepts_each_verified_parent_transition(tmp_path):
    for stage in (1,2,3):
        store=Store(tmp_path/str(stage))
        store.bind_parent('adapter-test-pet',fixture_parent(stage-1))
        settings=Settings(store.root,'fixture')
        assert settings.supported_stages==frozenset({1,2,3})
        with TestClient(create_app(settings,store)) as client:
            response=client.put('/v1/evolutions/stable-fixture-id',json=request(stage,stage-1),headers={'Authorization':'Bearer fixture'})
            assert response.status_code==200,response.text
            assert response.json()['result']['status']=='queued'
            assert client.get('/health').json()['supported_stages']==[1,2,3]
            assert store.get('stable-fixture-id')['parent']['stage']==stage-1


def test_environment_factory_defaults_to_all_sequential_stages_and_respects_explicit_subset(tmp_path,monkeypatch):
    from Ai.Generation3D.runtime.common_gateway.service import from_env
    monkeypatch.setenv('HEALTHMON_GPU_WORK_ROOT',str(tmp_path/'journal'))
    monkeypatch.setenv('AI_SERVER_TOKEN','cpu-contract-fixture')
    monkeypatch.delenv('HEALTHMON_GPU_SUPPORTED_STAGES',raising=False)
    assert from_env().state.settings.supported_stages==frozenset({1,2,3})
    monkeypatch.setenv('HEALTHMON_GPU_SUPPORTED_STAGES','1,2')
    assert from_env().state.settings.supported_stages==frozenset({1,2})


@pytest.mark.parametrize('stage',(1,2,3))
@pytest.mark.parametrize('upper,lower,nutrition,eb,appearance',[
    (30,30,30,40,'adipose'),(80,80,80,-40,'lean_athletic'),(30,30,30,-40,'lean'),
    (80,80,80,40,'bulky_athletic'),(50,50,50,40,'rounded_general'),
    (90,60,80,0,'upper_developed'),(60,90,80,0,'lower_developed'),
    (80,80,80,0,'balanced_athletic'),(80,80,30,0,'developed_general'),
    (50,50,50,0,'ordinary'),(30,30,30,0,'undertrained')])
def test_all_stage_and_stat_profiles_reach_frozen_compiler(tmp_path,stage,upper,lower,nutrition,eb,appearance):
    body=request(stage,stage-1)
    state=body['input']['state']
    state.update(upper_body=upper,lower_body=lower,nutrition=nutrition,energy_balance=eb)
    body['input']['profile']=rules.evolution_profile(state)
    body['input']['legacy_compatibility'].update(original_energy_balance=eb,energy_balance_normalized=eb/100)
    assert body['input']['profile']['appearance']==appearance
    stats=validate_request(body['request_id'],body)
    compiled=compile_individual(dict(species='lucan',level=state['level'],source_stage=stage-1,
        target_stage=stage,seed=42,stats=stats,history=[],history_origin='missing',
        authoritative_game_profile=body['input']['profile']),game_contract='healthmon.v2.2')
    assert compiled['transition']=={'source_stage':stage-1,'target_stage':stage,'level':(0,10,20,30)[stage]}
    assert compiled['recipe']['authoritative_game_profile']==body['input']['profile']
    assert compiled['stats']['UpperBody']==upper and compiled['stats']['LowerBody']==lower
    assert compiled['stats']['EnergyBalance']==eb/100
    prompt=apply_to_prompt('SCORE-DERIVED BODY CONDITION: old\n',body['input']['profile'])
    assert body_condition(body['input']['profile']) in prompt
    store=Store(tmp_path/'matrix');store.bind_parent(body['pet_id'],fixture_parent(stage-1))
    queued=store.submit(body['request_id'],body,Settings(store.root,'fixture').supported_stages)
    state['upper_body']=0
    assert queued['status']=='queued' and store.get(body['request_id'])['input']['input']['state']['upper_body']==upper


def test_no_public_token_issuance_or_unauthorized_job_access(adapter):
    client,_,_=adapter
    assert client.put('/v1/evolutions/stable-fixture-id',json=request(),headers={'Authorization':''}).status_code==401
    assert client.get('/v1/evolutions/stable-fixture-id',headers={'Authorization':'Bearer wrong-fixture'}).status_code==401
    assert client.post('/token').status_code==404


def test_worker_requires_explicit_gpu_start(adapter,tmp_path):
    _,store,settings=adapter
    called=[]
    with pytest.raises(PermissionError):
        run_once(settings,store,tmp_path/'models',tmp_path/'vendor',runner=lambda *a,**k:called.append(a))
    assert called==[]
    assert not (settings.work_root/'runtime').exists()


def test_docker_uses_existing_readonly_models_without_network_or_token(tmp_path):
    command=docker_command(tmp_path,tmp_path/'original-models',tmp_path/'original-vendor','stable-fixture-id','plan')
    assert command[command.index('--network')+1]=='none'
    assert command[command.index('--gpus')+1]=='all'
    model_mount=next(v for v in command if 'src='+str((tmp_path/'original-models').resolve())+',' in v)
    assert model_mount.endswith(',readonly')
    vendor_mount=next(v for v in command if 'src='+str((tmp_path/'original-vendor').resolve())+',' in v)
    assert vendor_mount.endswith(',readonly')
    writable_model_mounts=[item for item in command if ',dst=/opt/healthmon/Ai/Generation3D/models/' in item and not item.endswith(',readonly')]
    assert len(writable_model_mounts)==3
    for name in ('flex_gemm','torch_extensions','triton'):
        assert f'type=bind,src={tmp_path.resolve()/"cache/trellis"/name},dst=/opt/healthmon/Ai/Generation3D/models/trellis/{name}' in writable_model_mounts
    assert not any(item.startswith(('AI_SERVER_TOKEN=','HF_TOKEN=','HUGGING_FACE_HUB_TOKEN=')) for item in command)
    assert command[-3:]==['plan','--job-id','stable-fixture-id']


def test_execution_caches_seed_without_mutating_original_or_overwriting_runtime_cache(tmp_path):
    from Ai.Generation3D.runtime.common_gateway.runtime import prepare_execution_caches
    models=tmp_path/'original-models'
    cache=models/'trellis/flex_gemm'
    cache.mkdir(parents=True)
    (cache/'autotune_cache.json').write_text('{"known_kernel":1}')
    (cache/'autotune_cache.json.lock').write_text('stale source lock')
    (models/'checkpoint.safetensors').write_bytes(b'fixture checkpoint remains untouched')
    root=tmp_path/'isolated'
    prepare_execution_caches(root,models)
    local=root/'cache/trellis/flex_gemm/autotune_cache.json'
    assert local.read_text()=='{"known_kernel":1}'
    assert not local.with_suffix('.json.lock').exists()
    assert not (root/'cache/checkpoint.safetensors').exists()
    local.write_text('{"known_kernel":1,"new_kernel":2}')
    prepare_execution_caches(root,models)
    assert local.read_text()=='{"known_kernel":1,"new_kernel":2}'
    assert (cache/'autotune_cache.json').read_text()=='{"known_kernel":1}'
    assert (models/'checkpoint.safetensors').read_bytes()==b'fixture checkpoint remains untouched'


@pytest.mark.parametrize('upper,lower,nutrition,eb,appearance',[
    (30,30,30,40,'adipose'),(80,80,80,-40,'lean_athletic'),(30,30,30,-40,'lean'),
    (80,80,80,40,'bulky_athletic'),(50,50,50,40,'rounded_general'),
    (90,60,80,0,'upper_developed'),(60,90,80,0,'lower_developed'),
    (80,80,80,0,'balanced_athletic'),(80,80,30,0,'developed_general'),
    (50,50,50,0,'ordinary'),(30,30,30,0,'undertrained')])
def test_every_shared_appearance_controls_final_visible_body_without_new_score_rules(upper,lower,nutrition,eb,appearance):
    profile=rules.evolution_profile(dict(rules.initial_state(),upper_body=upper,lower_body=lower,nutrition=nutrition,energy_balance=eb))
    assert profile['appearance']==appearance
    saved=deepcopy(profile)
    legacy='Existing species and stage\nSCORE-DERIVED BODY CONDITION: Balanced moderately built body. Neither bodybuilder nor very large fat belly.\nExisting inherited palette and full-body pose.\n'
    prompt=apply_to_prompt(legacy,profile)
    assert body_condition(profile) in prompt and BODY_CONDITIONS[appearance] in prompt
    assert prompt.count('AUTHORITATIVE V2.2 APPEARANCE ['+appearance+']')==2
    assert 'moderately built' not in prompt and 'Neither bodybuilder' not in prompt
    assert 'Existing species and stage' in prompt and 'Existing inherited palette' in prompt
    assert profile==saved
    assert 'Mood' not in prompt


def test_unknown_authoritative_appearance_fails_closed():
    with pytest.raises(ValueError): body_condition({'rule_version':'healthmon.v2.2','appearance':'invented'})
    with pytest.raises(ValueError): body_condition({'rule_version':'legacy','appearance':'adipose'})
    with pytest.raises(ValueError): apply_to_prompt('No explicit body instruction',{'rule_version':'healthmon.v2.2','appearance':'adipose'})


def test_actual_v22_planner_writes_authoritative_adipose_prompt_without_loading_models(tmp_path,monkeypatch):
    import importlib
    source_root=Path(__file__).resolve().parents[2]/'Ai/Generation3D'
    monkeypatch.syspath_prepend(str(source_root))
    monkeypatch.syspath_prepend(str(source_root/'runtime/unity'))
    monkeypatch.syspath_prepend(str(source_root/'src'))
    # The shared CPU test suite also imports Server/healthmon as `healthmon`.
    # Bind the real 3D modules only within this planner test, then restore that
    # existing package. Test order must not select a different implementation.
    monkeypatch.setitem(sys.modules,'healthmon',importlib.import_module('Ai.Generation3D.src.healthmon'))
    for name in ('individual_evolution','qwen_runner','species_contract'):
        monkeypatch.setitem(sys.modules,'healthmon.'+name,importlib.import_module('Ai.Generation3D.src.healthmon.'+name))
    monkeypatch.setitem(sys.modules,'torch',SimpleNamespace())
    monkeypatch.setitem(sys.modules,'transformers',SimpleNamespace(Qwen3VLForConditionalGeneration=object,Qwen3VLProcessor=object))
    path=source_root/'runtime/unity/evolution_worker.py'
    spec=importlib.util.spec_from_file_location('v22_prompt_wiring_fixture',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    from Ai.Generation3D.runtime.common_gateway.runtime import sha
    body=request();body['input']['state'].update(upper_body=30,lower_body=30,nutrition=30,energy_balance=40)
    body['input']['profile']=rules.evolution_profile(body['input']['state'])
    body['input']['legacy_compatibility'].update(original_energy_balance=40,energy_balance_normalized=.4)
    stats=validate_request('stable-fixture-id',body)
    profile={'species':'lucan','level':10,'source_stage':0,'target_stage':1,'seed':42,'stats':stats,
             'history':[],'history_origin':'missing','authoritative_game_profile':body['input']['profile']}
    compiled=compile_individual(profile,game_contract='healthmon.v2.2')
    parent=tmp_path/'parent.png';parent.write_bytes(b'CPU-only parent hash fixture; image decoder never called')
    folder=tmp_path/'output';folder.mkdir()
    design={'implementation':{'model_id':'Qwen/Qwen-Image-2.1','revision':'d26bb61231c349cf6b7896fa83353113880e1ba3',
            'dtype':'bfloat16','compiler_version':compiled['version'],
            'compiler_sha256':sha(source_root/'src/healthmon/individual_evolution.py'),
            'adapter_sha256':sha(path),'conditioning_mode':'planner_only'},
            'visual_references':[{'sha256':sha(parent)}],
            'concept':{'image_prompt':'Parent-grounded juvenile four-pawed thunder-wolf with a distinctly rounded soft abdomen.'}}
    (folder/'design.json').write_text(json.dumps(design),encoding='utf-8')
    module.plan_from_parent(folder,{'target_stage':1,'source_stage':0,'source_revision':'fixture','seed':42,
        'stats':stats,'game_contract':'healthmon.v2.2','authoritative_state':body['input']['state'],
        'authoritative_profile':body['input']['profile']},parent,{'image_sha256':sha(parent),'stage':0,'species':'lucan'})
    prompt=(folder/'prompt.txt').read_text(encoding='utf-8')
    assert 'AUTHORITATIVE V2.2 APPEARANCE [adipose]' in prompt
    assert 'large projecting rounded abdomen' in prompt and 'wide soft waist' in prompt
    assert 'moderately built' not in prompt and 'Neither bodybuilder' not in prompt
    assert 'Artistic adiposity=' not in prompt
    plan=json.loads((folder/'planning_request.json').read_text(encoding='utf-8'))
    planned=json.loads(plan['user'])
    assert planned['authoritative_body_condition']==body_condition(body['input']['profile'])
    assert 'not a swollen belly' not in json.dumps(planned)
    assert 'Moderately' not in planned['explicit_score_condition_direction']
    # The existing legacy function and its original formula thresholds are preserved.
    assert 'Balanced moderately built' in module.body_instruction(compiled)


def test_clean_entrypoint_can_import_appearance_despite_sibling_runtime_py(tmp_path):
    # A script runs with common_gateway as sys.path[0], where runtime.py must not
    # shadow a generic `runtime` namespace. Use the actual entrypoint path setup.
    entry=Path(__file__).resolve().parents[2]/'Ai/Generation3D/runtime/common_gateway/gpu_entry.py'
    code='import runpy,sys\nfrom pathlib import Path\np=Path(sys.argv[1])\nsys.path.insert(0,str(p.parent))\nrunpy.run_path(str(p),run_name="cpu_entrypoint_fixture")\nfrom Ai.Generation3D.runtime.common_gateway.appearance import body_condition\nassert "large projecting rounded abdomen" in body_condition({"rule_version":"healthmon.v2.2","appearance":"adipose"})\nassert "torch" not in sys.modules\nprint("clean entrypoint import PASS")\n'
    result=subprocess.run([sys.executable,'-I','-c',code,str(entry)],cwd=tmp_path,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='clean entrypoint import PASS'


def test_leases_recover_same_job_after_restart_without_stale_publish(adapter):
    client,store,_=adapter
    client.put('/v1/evolutions/stable-fixture-id',json=request())
    with ThreadPoolExecutor(max_workers=5) as executor:
        claimed=list(executor.map(lambda _:store.claim(),range(5)))
    job=next(item for item in claimed if item is not None)
    assert sum(item is not None for item in claimed)==1
    store.update(job['id'],expected_lease=job['lease_token'],lease_until=0)
    recovered=Store(store.root).claim()
    assert recovered['id']==job['id']
    assert recovered['input']==job['input']
    with pytest.raises(Conflict):
        store.update(job['id'],expected_lease=job['lease_token'],status='succeeded')


@pytest.mark.parametrize('stage',[1,2,3])
def test_v22_compiler_has_actual_milestones_and_no_invented_mood(stage):
    body=request(stage,published=stage-1)
    stats=validate_request('stable-fixture-id',body)
    profile={'species':'lucan','level':body['input']['state']['level'],'source_stage':stage-1,
             'target_stage':stage,'stats':stats,'history':[],'history_origin':'missing',
             'authoritative_game_profile':body['input']['profile']}
    compiled=compile_individual(profile,game_contract='healthmon.v2.2')
    assert compiled['transition']['level']==(0,10,20,30)[stage]
    assert compiled['transition']['target_stage']==stage
    assert compiled['recipe']['authoritative_game_profile']==body['input']['profile']
    assert 'Mood' not in compiled['stats']
    assert 'Mood' not in compiled['recipe']['current']
    assert compiled['expression'] is None and compiled['expression_key'] is None
    assert compiled['history']['available'] is False
    for mood in (0,50,100):
        level=(0,15,30,50)[stage]
        legacy=compile_individual({'species':'lucan','previous_level':level-1,'level':level,
                                   'stats':{**stats,'Mood':mood},'history':[],'history_origin':'missing'})
        for key in ('dimensions','condition','individual_variation','tendencies'):
            assert compiled[key]==legacy[key]  # old body math preserved; expression omitted entirely
