import json
import sys
import subprocess
from pathlib import Path
import hashlib
import pytest
from dotenv import dotenv_values
from Server.team import bootstrap
from Server.scripts import manage

@pytest.fixture
def root(tmp_path,monkeypatch):
    monkeypatch.setattr(bootstrap,'ROOT',tmp_path)
    monkeypatch.setattr(bootstrap,'STATE',tmp_path/'.runtime/team')
    monkeypatch.setattr(manage,'ROOT',tmp_path)
    return tmp_path

def test_first_setup_and_reinstall_preserve_credentials(root):
    bootstrap.connection()
    first=dotenv_values(root/'.env')
    assert first['AI_MODE']=='remote' and first['AI_BASE_URL']=='http://host.docker.internal:18090'
    assert first['POSTGRES_PASSWORD'] and first['DEV_TOKENS']
    bootstrap.connection()
    assert dotenv_values(root/'.env')==first
    assert (bootstrap.STATE/'server-token').read_text()==first['AI_SERVER_TOKEN']

def test_existing_account_database_and_token_are_retained(root):
    (root/'.env').write_text('APP_ENV=test\nAI_MODE=disabled\nAI_SERVER_TOKEN=existing-token\nPOSTGRES_PASSWORD=existing-db\nDEV_TOKENS={"a":"owner"}\nSERVER_INSTANCE_ID=existing-id\n')
    bootstrap.connection()
    value=dotenv_values(root/'.env')
    assert value['AI_SERVER_TOKEN']=='existing-token' and value['POSTGRES_PASSWORD']=='existing-db'
    assert value['SERVER_INSTANCE_ID']=='existing-id' and json.loads(value['DEV_TOKENS'])=={'a':'owner'}

def test_production_settings_never_changed(root):
    path=root/'.env';path.write_text('APP_ENV=production\n')
    with pytest.raises(ValueError,match='test backend'): bootstrap.connection()
    assert path.read_text()=='APP_ENV=production\n'

def test_native_connection_does_not_create_new_backend(root):
    bootstrap.STATE.mkdir(parents=True);(bootstrap.STATE/'server-token').write_text('existing-native-token')
    bootstrap.connection(native=True)
    assert not (root/'.env').exists()

def test_model_selection_is_offline_and_independent(root,monkeypatch):
    import socket
    monkeypatch.setattr(socket,'create_connection',lambda *a,**kw:pytest.fail('network used'))
    for group,folder,manifest in [('food','Ai/Vision/multifood/models','manifest.json'),('pose','Ai/Pose/mac-exercise-counter/models','manifest.json')]:
        target=root/folder;target.mkdir(parents=True)
        data=b'fixture';name=group+'.bin';(target/name).write_bytes(data)
        (target/manifest).write_text(json.dumps({name:{'file':name,'sha256':hashlib.sha256(data).hexdigest(),'size_bytes':len(data)}}))
    assert bootstrap.available_models()['ready']==['food','pose']
    (root/'Ai/Vision/multifood/models/food.bin').unlink()
    status=bootstrap.available_models()
    assert status['ready']==['pose'] and list(status['skipped'])==['food']
    # The inference suite may already have imported torch during collection.
    # Check the installer's cold process, independent of pytest import order.
    code = """import sys,socket
from pathlib import Path
from Server.team import bootstrap
def deny(*a,**k): raise AssertionError('model selection used network')
socket.create_connection=deny
bootstrap.ROOT=Path(sys.argv[1])
assert bootstrap.available_models()['ready']==['pose']
assert not any(n.startswith(('torch','transformers','huggingface_hub')) for n in sys.modules)
"""
    subprocess.run([sys.executable,'-B','-c',code,str(root)],check=True,cwd=Path(__file__).resolve().parents[2])


def test_food_only_gateway_reports_optional_models_without_fake_success(root,monkeypatch):
    from fastapi.testclient import TestClient
    from Server.local_probe import vision_gateway
    monkeypatch.setattr(vision_gateway,'ROOT',root)
    folder=root/'.runtime/vision';folder.mkdir(parents=True)
    config=folder/'private.json';config.write_text(json.dumps({'environment':'test','vision_enabled':True,'server_token':'fixture'}))
    class Runner:
        identity={'fixture':True}
    with TestClient(bootstrap.food_app(config,runner=Runner())) as client:
        assert client.get('/health/services').status_code==401
        value=client.get('/health/services',headers={'Authorization':'Bearer fixture'}).json()
        assert value['status']=='ready' and value['services']['vision']['available'] is True
        assert value['services']['chat']['status']=='not_installed'
        assert client.put('/v1/evolutions/fixture').status_code==501
