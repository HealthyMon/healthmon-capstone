import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.qwen_loading import verify_adapter_base
from src.chatml import encode_chatml


def test_runtime_identity_reports_selected_four_b(monkeypatch):
    from src.model_runtime import OnDemandQwen
    backend = object.__new__(OnDemandQwen)
    monkeypatch.setenv('MODEL_PATH', 'models/qwen3.5-4b')
    monkeypatch.setenv('MODEL_QUANTIZATION', 'nf4')
    monkeypatch.setenv('ADAPTER_PATH', 'runs/four-b/checkpoint-epoch-1')
    assert backend.name == 'qwen3.5-4b-nf4-lora'
    monkeypatch.delenv('MODEL_PATH')
    monkeypatch.delenv('MODEL_QUANTIZATION')
    monkeypatch.delenv('ADAPTER_PATH')
    assert backend.name == 'qwen3.5-9b-bf16'


def test_nine_b_adapter_rejected_for_four_b(tmp_path):
    base = tmp_path/'qwen3.5-4b'
    base.mkdir()
    adapter = tmp_path/'adapter'
    adapter.mkdir()
    (adapter/'adapter_config.json').write_text(json.dumps({'base_model_name_or_path':'Qwen/Qwen3.5-9B'}))
    with pytest.raises(ValueError, match='mismatch'):
        verify_adapter_base(base, adapter)
    (base/'healthmon-source.json').write_text(json.dumps({'model_id':'Qwen/Qwen3.5-4B'}))
    (adapter/'adapter_config.json').write_text(json.dumps({'base_model_name_or_path':'Qwen/Qwen3.5-4B'}))
    verify_adapter_base(base, adapter)


def test_assistant_only_labels_keep_complete_context():
    class Tokenizer:
        def apply_chat_template(self, prompt, **kwargs):
            assert kwargs['enable_thinking'] is False
            assert prompt[0]['content'] == 'personality, recent dialogue, relevant memory'
            return [1,2,3,4]
        def encode(self, target, **kwargs):
            assert target.endswith('<|im_end|>')
            return [5,6]
    result = encode_chatml(Tokenizer(),[{'role':'system','content':'personality, recent dialogue, relevant memory'}],'{}',6)
    assert result['labels'] == [-100,-100,-100,-100,5,6]
    with pytest.raises(ValueError, match='no truncation'):
        encode_chatml(Tokenizer(),[{'role':'system','content':'personality, recent dialogue, relevant memory'}],'{}',5)


def test_common_training_preserves_memory_recent_and_personality():
    from scripts.prepare_qwen4b_common import make
    from scripts.train_qwen4b import training_prompt
    memories=[{'id':'m1','content':'보리차를 좋아해.','source_id':'s1','source_revision':2}]
    recent=[{'speech':'안녕.','source_id':'s2'}]
    row=make('fixture','좋아하는 차 알려줘.','보리차야.',
             axes={'activity':90,'affinity':10,'initiative':50}, memories=memories,recent=recent)
    prompt,target=training_prompt(row)
    content=json.loads(prompt[1]['content'])
    assert content['context']['memories']==memories
    assert content['context']['recent']==recent
    assert content['context']['verified_game_facts']['activity']==90
    assert content['context']['verified_game_facts']['affinity']==10
    assert content['user_text']==row['user_text']
    assert 'classification' in json.loads(target)
    assert 'personality_update' not in json.loads(target)
