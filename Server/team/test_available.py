import json
from pathlib import Path
import sys
import pytest
from Server.local_probe import local_services as svc
from Server.team import available

@pytest.fixture
def installed(tmp_path, monkeypatch):
    monkeypatch.setattr(svc,'ROOT',tmp_path)
    runtime=tmp_path/'.runtime'; runtime.mkdir()
    monkeypatch.setattr(svc,'RUNTIME',runtime)
    def put(name,data=b'fixture model'):
        path=tmp_path/name; path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(data)) if isinstance(data,(dict,list)) else path.write_bytes(data)
        return str(path)
    llm=dict(environment='test',server_token='fixture-token')
    for key in ('model_path','embedding_path'):
        directory=tmp_path/key; put(key+'/config.json',{});put(key+'/model.safetensors')
        llm[key]=str(directory)
    vision=dict(environment='test',server_token='fixture-token',vision_python=sys.executable,vision_assets=str(tmp_path/'vision'))
    put('Ai/Vision/weights-manifest.json',{'food.pth':{'size_bytes':13}})
    put('vision/food.pth');put('vision/nutrition.json',{})
    put('Ai/Generation3D/migration/model_manifest.json',{'files':[{'required':True,'target':'models/model.bin','bytes':13}]})
    put('generation/model.bin');(tmp_path/'vendor').mkdir()
    evolution=dict(model_root=str(tmp_path/'generation'),vendor_root=str(tmp_path/'vendor'),work_root=str(runtime/'jobs'))
    put('Ai/Pose/mac-exercise-counter/models/manifest.json',{'pose':{'file':'pose.onnx'}})
    put('Ai/Pose/mac-exercise-counter/models/pose.onnx')
    values=dict(python=sys.executable,llm_python=sys.executable,pose_python=sys.executable,
                llm_config=put('.runtime/llm.json',llm),vision_config=put('.runtime/vision.json',vision),evolution_config=put('.runtime/evolution.json',evolution))
    config=put('.runtime/services.json',values)
    return tmp_path,Path(config),put

def test_all_present_enables_all_without_loading_models(installed):
    _,path,_=installed
    value=available.configuration(path)
    assert value['enabled']==['router','llm','vision','evolution','pose'] and not value['skipped']

@pytest.mark.parametrize('missing,disabled',[
 ('model_path/model.safetensors','llm'),('embedding_path/config.json','llm'),
 ('vision/food.pth','vision'),('generation/model.bin','evolution'),
 ('Ai/Pose/mac-exercise-counter/models/pose.onnx','pose')])
def test_one_missing_model_does_not_disable_others(installed,missing,disabled):
    root,path,_=installed;(root/missing).unlink()
    value=available.configuration(path)
    assert disabled not in value['enabled'] and list(value['skipped'])==[disabled]
    commands=svc.service_commands(value)
    assert set(commands)==set(value['enabled']) and len(commands)==4

def test_missing_both_heavy_models_keeps_food_and_pose(installed):
    root,path,_=installed
    (root/'model_path/model.safetensors').unlink();(root/'generation/model.bin').unlink()
    value=available.configuration(path)
    assert value['enabled']==['router','vision','pose']
    assert set(svc.service_commands(value))=={'router','vision','pose'}

def test_missing_one_private_config_can_use_other_token(installed):
    root,path,_=installed;(root/'.runtime/llm.json').unlink()
    value=available.configuration(path)
    assert 'llm' in value['skipped'] and 'vision' in value['enabled']

def test_incomplete_sharded_model_is_skipped(installed):
    root,path,put=installed
    put('model_path/model.safetensors.index.json',{'weight_map':{'tensor':'missing-shard.safetensors'}})
    value=available.configuration(path)
    assert 'llm' in value['skipped'] and 'vision' in value['enabled']

def test_lfs_pointer_is_not_an_installed_model(installed):
    root,path,put=installed
    put('model_path/model.safetensors',b'version https://git-lfs.github.com/spec/v1\noid sha256:fixture\nsize 13\n')
    assert 'llm' in available.configuration(path)['skipped']

def test_failed_optional_process_does_not_stop_other_services(tmp_path,monkeypatch):
    monkeypatch.setattr(svc,'RUNTIME',tmp_path)
    monkeypatch.setattr(svc,'STOP',tmp_path/'stop')
    commands={name:(port,['python',name]) for name,port in [('router',1),('vision',2),('llm',3)]}
    monkeypatch.setattr(svc,'service_commands',lambda config: dict(commands))
    active=set();events=[]
    monkeypatch.setattr(svc,'matching_processes',lambda cmd: [])
    monkeypatch.setattr(svc,'health',lambda port: next(n for n,(p,_) in commands.items() if p==port) in active)
    class Child:
        def __init__(self,name):self.name=name
        def poll(self):return 1 if self.name=='llm' else None
    def spawn(cmd,**kwargs):
        active.add(cmd[1]);events.append(('start',cmd[1]));return Child(cmd[1])
    monkeypatch.setattr(svc.subprocess,'Popen',spawn)
    monkeypatch.setattr(svc,'stop_matching',lambda cmd:(events.append(('stop',cmd[1])),active.discard(cmd[1])))
    def status(phase,**extra):
        events.append((phase,extra))
        if phase=='ready':svc.STOP.touch()
    monkeypatch.setattr(svc,'write_status',status)
    svc.supervise({'available_only':True})
    ready=next(value for phase,value in events if phase=='ready')
    assert ready['services']=={'router':True,'vision':True}
    assert 'llm' in ready['failed'] and 'llm' not in ready['skipped']
    assert events.index(('stop','vision'))>next(i for i,event in enumerate(events) if event[0]=='ready')


def test_multifood_uses_new_manifest_and_keeps_other_services(installed):
    root,path,put=installed
    cfg=root/'.runtime/vision.json'; value=json.loads(cfg.read_text())
    value.update(vision_backend='multifood',vision_assets=str(root/'multifood'))
    put('.runtime/vision.json',value)
    put('multifood/models/manifest.json',{'classifier.pkl':{'size_bytes':13}})
    put('multifood/models/classifier.pkl');put('multifood/nutrition.csv');put('multifood/worker.py')
    (root/'vision/food.pth').unlink()
    assert 'vision' in available.configuration(path)['enabled']
    (root/'multifood/models/classifier.pkl').unlink()
    result=available.configuration(path)
    assert result['enabled']==['router','llm','evolution','pose']
    assert list(result['skipped'])==['vision']


def test_missing_food_container_keeps_other_ai(installed,monkeypatch):
    root,path,put=installed
    cfg=root/'.runtime/vision.json';value=json.loads(cfg.read_text())
    value.update(vision_backend='multifood',vision_container=True,vision_assets=str(root/'multifood'))
    put('.runtime/vision.json',value)
    put('multifood/models/manifest.json',{'classifier.pkl':{'size_bytes':13}})
    put('multifood/models/classifier.pkl');put('multifood/nutrition.csv');put('multifood/worker.py')
    monkeypatch.setattr(available.shutil,'which',lambda _:None)
    result=available.configuration(path)
    assert result['enabled']==['router','llm','evolution','pose']
    assert list(result['skipped'])==['vision']
