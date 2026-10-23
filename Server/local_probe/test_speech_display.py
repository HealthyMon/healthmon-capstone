import json

import pytest
from pydantic import ValidationError

from Server.local_probe.speech_display import parse_generated_speech
from Server.local_probe.test_contract import context, result, scripted_models


@pytest.mark.parametrize('display', [dict(emotion='curious'), dict(animation='nod'),
                                    dict(emotion='confused', animation='listen')])
def test_unknown_display_enum_preserves_real_speech_and_classification(display, tmp_path):
    original = result('응, 어떤 이야기를 하고 싶어?').model_dump(mode='json')
    original.update(display)
    models, calls = scripted_models(tmp_path, [json.dumps(original)], False)
    output, metrics = models.chat({'text': '안녕', 'context': context()})
    assert output['speech'] == original['speech']
    assert output['classification'] == original['classification']
    assert output['memory_ids'] == original['memory_ids']
    assert len(calls) == 1 and not metrics['fallback']
    assert metrics['attempts'][0]['display_metadata_defaults'] == sorted(display)
    for key in display:
        assert output[key] == {'emotion': 'neutral', 'animation': 'idle'}[key]


def test_allowed_display_metadata_is_unchanged():
    original = result('반가워!')
    output, defaults = parse_generated_speech(original.model_dump_json())
    assert output == original and defaults == []


@pytest.mark.parametrize('change', [dict(speech=''), dict(emotion=None), dict(emotion=1),
                                  dict(classification={}), dict(extra='unexpected')])
def test_invalid_core_fields_and_types_are_still_rejected(change):
    original = result('반가워!').model_dump(mode='json')
    original.update(emotion='curious')
    original.update(change)
    with pytest.raises(ValidationError):
        parse_generated_speech(json.dumps(original))


def test_fabricated_memory_is_still_rejected(tmp_path):
    original = result('이야기하자.').model_dump(mode='json')
    original.update(emotion='curious', memory_ids=['invented'])
    models, calls = scripted_models(tmp_path, [json.dumps(original)] * 2, False)
    with pytest.raises(ValueError):
        models.chat({'text': '안녕', 'context': context()})
    assert len(calls) == 2


def test_invalid_json_and_missing_emotion_are_not_defaulted():
    with pytest.raises(ValidationError):
        parse_generated_speech('{invalid')
    original = result('반가워!').model_dump(mode='json')
    del original['emotion']
    with pytest.raises(ValidationError):
        parse_generated_speech(json.dumps(original))
