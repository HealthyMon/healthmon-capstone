"""Skipping BGE must preserve durable memory, contextual lookup and deletion."""
import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from src import app as module
from src.db import connect


@pytest.fixture
def session(monkeypatch):
    calls = []
    contexts = []
    def vectorize(text):
        calls.append(text)
        return [1.] + [0.] * 1023
    class Model:
        def generate(self, context, text, repair=None):
            contexts.append(context)
            speech = '안녕, 만나서 반가워!' if text == '안녕!' else '네 이야기를 들었어. 차근차근 이야기하자.'
            if not context['memories'] and module.wants_memory_lookup(text, context['recent']):
                speech = '아직 저장된 기억은 없어. 지금 말한 이야기는 들었어.'
            return json.dumps({'speech': speech,
                'emotion': 'neutral', 'animation': 'idle', 'action': {'type': 'none', 'target_id': None},
                'memory_ids': [m['id'] for m in context['memories']], 'personality_update': None})
    monkeypatch.setattr(module, 'backend', Model())
    monkeypatch.setattr(module, 'vectorize', vectorize)
    client = TestClient(module.app)
    headers = {'Authorization': 'Bearer ' + next(iter(json.loads(os.environ['DEV_TOKENS'])))}
    pet = client.post('/pets', json={}, headers=headers).json()['pet_id']
    def chat(text):
        result = client.post(f'/pets/{pet}/chat', json={'request_id': uuid.uuid4().hex, 'text': text}, headers=headers)
        assert result.status_code == 200, result.text
        assert not result.json()['metrics']['fallback'], result.text
        return result.json()
    return pet, chat, calls, contexts


@pytest.mark.parametrize('text,slot', [('나는 걷기를 좋아해.', 'preference'), ('내 목표는 꾸준히 걷기야.', 'goal')])
def test_durable_memory_still_embeds_and_followup_uses_recent_topic(session, text, slot):
    pet, chat, calls, contexts = session
    assert chat(text)['metrics']['timings']['embedding_loaded']
    with connect() as c:
        memory = c.execute('SELECT slot,content,embedding FROM memories WHERE pet_id=%s AND valid', (pet,)).fetchone()
    assert memory['slot'] == slot and memory['content'] == text and memory['embedding'] is not None
    calls.clear()
    result = chat('그거 기억해?')
    assert calls == ['그거 기억해?'] and result['metrics']['timings']['embedding_loaded']
    assert contexts[-1]['memories'][0]['content'] == text


def test_normal_chat_skips_embedding_even_when_memory_exists(session):
    _, chat, calls, contexts = session
    chat('나는 걷기를 좋아해.')
    calls.clear()
    result = chat('안녕!')
    assert calls == [] and contexts[-1]['memories'] == []
    assert result['metrics']['timings']['embedding_loaded'] is False


def test_lookup_with_no_stored_memories_does_not_load_bge(session):
    _, chat, calls, contexts = session
    result = chat('내 취향 기억해?')
    assert calls == [] and contexts[-1]['memories'] == []
    assert result['metrics']['timings']['embedding_loaded'] is False


def test_forget_command_skips_models_and_invalidates_original_memory(session):
    pet, chat, calls, contexts = session
    chat('나는 걷기를 좋아해.')
    calls.clear(); contexts.clear()
    result = chat('내 취향은 기억에서 지워 줘.')
    assert calls == [] and contexts == []
    assert result['execution']['deleted_memory_id']
    with connect() as c:
        assert not c.execute('SELECT 1 FROM memories WHERE pet_id=%s AND valid', (pet,)).fetchone()
