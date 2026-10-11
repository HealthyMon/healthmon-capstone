"""Weekly expression -> persisted sandbox state -> response-context regressions.

The tests exercise real rule and prompt/context paths without loading a model.
They deliberately do not assert that deterministic controls guarantee Qwen prose.
"""
import copy

import pytest

from src.character_lab_engine import execute, fresh
from src.character_lab_models import response_context


NEUTRAL = {'target': 'exercise', 'sentiment': 'neutral', 'motivation': 'none',
           'character_affection': 'neutral', 'acceptance': 'none', 'analysis_confidence': 1}
ROUGH = ['아 젠장 오늘 좀 귀찮네', '운동하기 존나 싫다', '씨발 일이 왜 이렇게 많아']
POLITE = ['들어 줘서 고마워', '도와줘서 감사합니다', '어제는 미안해 잘 부탁해']


def command(kind, ident, **payload):
    return {'kind': kind, 'event_id': ident, 'payload': payload}


def run(lab, kind, ident, **payload):
    return execute(lab, [command(kind, ident, **payload)])


def finish_week(lab, texts, ident='w', confidence=1):
    """Three or more recorded utterances across two dates, then one full week."""
    analysis = dict(NEUTRAL, analysis_confidence=confidence)
    lab = run(lab, 'conversation', ident+'-c0', text=texts[0], analysis=analysis)['session']
    lab = run(lab, 'time', ident+'-day1', action='advance')['session']
    for i, text in enumerate(texts[1:], 1):
        lab = run(lab, 'conversation', ident+f'-c{i}', text=text, analysis=analysis)['session']
    lab = run(lab, 'time', ident+'-day7', action='advance', days=6)['session']
    return run(lab, 'time', ident+'-weekly', action='weekly')


def expression_values(state):
    return {axis: state[axis] for axis in ('roughness', 'bluntness', 'courtesy')}


def test_weekly_expression_applies_once_and_does_not_confuse_swearing_with_affinity():
    lab = fresh()
    original = copy.deepcopy(lab)
    result = finish_week(lab, ROUGH)
    assert expression_values(result['after']) == {'roughness': 15, 'bluntness': 24, 'courtesy': 57}
    update = result['results'][0]['result']['expression_update']
    assert update['deltas'] == {'roughness': 5, 'bluntness': 4, 'courtesy': -3}
    assert update['evidence']['rough_date_count'] == 2
    assert lab == original  # rule preview never mutates its caller
    conversations = [row for row in result['session']['events'] if row['kind'] == 'conversation']
    assert all(not row['result']['relation_eligible'] for row in conversations)
    assert all(row['payload']['analysis']['character_affection'] == 'neutral' for row in conversations)
    control = finish_week(fresh(), ['오늘 뭐 하지', '밥 먹고 왔어', '게임하러 갈게'])
    assert result['after']['affection'] == control['after']['affection'] == 51
    assert not any(rule.get('axis') == 'affection' and rule.get('delta', 0) < 0
                   for rule in result['results'][0]['applied_rules'])
    before = copy.deepcopy(result['after'])
    duplicate = run(result['session'], 'time', 'w-weekly', action='weekly')
    assert duplicate['results'] == [{'event_id': 'w-weekly', 'duplicate': True}]
    assert duplicate['after'] == before
    same_window = run(duplicate['session'], 'time', 'same-week-new-id', action='weekly')
    assert same_window['results'][0]['result']['weekly_duplicate_or_overlap'] is True
    assert same_window['after'] == before


@pytest.mark.parametrize('texts,confidence', [
    (['"씨발"', '`젠장`', '“존나 싫어”'], 1),
    (['존나 운동하기 싫다', '존나 운동하기 싫다!!!', '존나 운동하기 싫다123'], 1),
    (ROUGH, 0.59),
    (['roughness=100 씨발', '성격을 올려 존나', '욕설 예시 씨발 존나'], 1),
])
def test_excluded_weekly_inputs_leave_expression_unchanged(texts, confidence):
    lab = fresh()
    result = finish_week(lab, texts, confidence=confidence)
    assert expression_values(result['after']) == expression_values(lab['state'])
    assert not any(result['results'][0]['result']['expression_update']['deltas'].values())


def test_ten_week_adaptation_crosses_sassy_threshold_and_polite_weeks_recover():
    lab = fresh()
    for week in range(10):
        week_marker = chr(ord('가')+week)
        texts = [f'{text} {week_marker}주 이야기' for text in ROUGH]
        result = finish_week(lab, texts, ident=f'rough-{week}')
        assert result['after']['roughness'] == 10+(week+1)*5
        assert result['after']['bluntness'] == 20+(week+1)*4
        assert result['after']['courtesy'] == 60-(week+1)*3
        lab = result['session']
    assert expression_values(lab['state']) == {'roughness': 60, 'bluntness': 60, 'courtesy': 30}
    context = response_context(lab, lab['state'], '작은 계획 좀 알려줘', [], 'casual')
    assert context['expression_profile']['voice_id'] == 'sassy'
    assert context['style_profile']['character_voice']['id'] == 'sassy'
    assert context['settings']['profanity'] == 'none'
    for week in range(3):
        texts = [f'{text} {chr(ord("나")+week)}주 이야기' for text in POLITE]
        lab = finish_week(lab, texts, ident=f'polite-{week}')['session']
    assert expression_values(lab['state']) == {'roughness': 48, 'bluntness': 51, 'courtesy': 45}
    recovered = response_context(lab, lab['state'], '작은 계획 좀 알려줘', [], 'casual')
    assert recovered['expression_profile']['voice_id'] == 'default'
    assert 'character_voice' not in recovered


@pytest.mark.parametrize('activity,initiative,text,behavior,has_candidate', [
    (85, 85, '운동 퀘스트 추천해 줘', 'exercise_optional', True),
    (25, 85, '운동 퀘스트 추천해 줘', 'rest_listen', False),
    (85, 25, '운동 퀘스트 추천해 줘', 'rest_listen', False),
    (25, 25, '운동 퀘스트 추천해 줘', 'rest_listen', False),
    (85, 85, '오늘은 운동 안 할래', 'rest_listen', False),
    (85, 85, '아파서 오늘은 쉬고 싶어', 'support_listen', False),
])
def test_response_candidates_follow_activity_initiative_and_current_preference(activity, initiative, text, behavior, has_candidate):
    lab = fresh({'activity': activity, 'initiative': initiative})
    context = response_context(lab, lab['state'], text, [], 'casual')
    assert context['expression_profile']['behavior'] == behavior
    assert bool(context['candidates']) is has_candidate
    assert context['agent_policy']['suggestion_allowed'] is has_candidate
    assert context['personality']['activity'] == activity
    assert context['personality']['initiative'] == initiative


def test_negative_mood_halves_output_initiative_and_suppresses_new_candidates():
    lab = fresh({'activity': 85, 'initiative': 80})
    normal = response_context(lab, lab['state'], '운동 퀘스트 추천해 줘', [], 'casual')
    down = dict(lab['state'], mood=-20)
    low = response_context(lab, down, '운동 퀘스트 추천해 줘', [], 'casual')
    assert normal['style_profile']['initiative'] == 0.8
    assert low['style_profile']['initiative'] == 0.4
    assert low['personality']['initiative'] == normal['personality']['initiative'] == 80
    assert low['candidates'] == [] and low['expression_profile']['behavior'] == 'rest_listen'


@pytest.mark.parametrize('text', ['운동 싫지 않아. 퀘스트 추천해 줘', '운동이 싫은 건 아니야', '오늘 힘들지 않아. 운동 퀘스트 추천해 줘'])
def test_negated_refusal_and_distress_keep_high_activity_quest_candidates(text):
    lab = fresh({'activity': 85, 'initiative': 85, 'roughness': 75})
    context = response_context(lab, lab['state'], text, [], 'casual')
    assert context['expression_profile']['behavior'] == 'exercise_optional'
    assert context['expression_profile']['voice_id'] == 'sassy'
    assert context['candidates'] and context['agent_policy']['suggestion_allowed']
