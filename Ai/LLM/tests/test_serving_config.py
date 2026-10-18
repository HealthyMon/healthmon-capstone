import json
from scripts.serve import ROOT,resolve_adapter

def test_default_server_uses_selected_adapter(monkeypatch):
    monkeypatch.delenv('ADAPTER_PATH',raising=False)
    selected=json.loads((ROOT/'config/serving.json').read_text(encoding='utf-8'))['adapter_path']
    assert resolve_adapter()==selected
    assert (ROOT/selected/'adapter_config.json').is_file()

def test_explicit_adapter_environment_and_base_precedence(monkeypatch):
    monkeypatch.setenv('ADAPTER_PATH','environment-adapter')
    assert resolve_adapter()=='environment-adapter'
    assert resolve_adapter('explicit-adapter')=='explicit-adapter'
    assert resolve_adapter(base=True) is None
