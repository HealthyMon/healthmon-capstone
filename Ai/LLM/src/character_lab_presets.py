"""Small explicit synthetic test scenarios, never model/training data."""
from datetime import date, timedelta
from .character_lab_engine import fresh, execute
from .character_lab_schema import RULES

PRESETS = {
    'exercise_7': '1. 7일 연속 운동 성공', 'inactive_7': '2. 7일 운동 없음',
    'upper_only': '3. 상체 운동만 지속', 'lower_only': '4. 하체 운동만 지속',
    'balanced': '5. 운동 성공 + 균형 식사', 'overeat': '6. 운동 없음 + 과식',
    'stop_next_week': '7. 운동 성공 후 다음 주 운동 중단', 'positive_chat': '8. 캐릭터와 매일 긍정 대화',
    'reject_proposals': '9. 캐릭터 제안 지속 거절', 'exercise_profanity': '10. 욕설 있지만 운동에 대한 불만',
    'evolution_fat': '11. 1차 운동형 → 2차 체지방 증가형', 'evolution_recovery': '12. 2차 체지방 증가형 → 3차 회복형',
    'rough_language': '13. 반복 거친 말투 10주 → 툴툴대는 목소리',
    'polite_recovery': '14. 툴툴대는 성격에서 공손한 말투 3주 → 회복',
}


def commands_for(name, session):
    if name not in PRESETS:
        raise ValueError('Unknown Character Lab preset')
    commands = []
    start = date.fromisoformat(session['state']['virtual_test_date'])

    def add(kind, **payload):
        commands.append({'kind': kind, 'event_id': f'preset:{name}:{start}:{len(commands)}', 'payload': payload})

    if name in ('rough_language', 'polite_recovery'):
        polite = name == 'polite_recovery'
        if polite:
            add('manual_override', state=dict(session['state'], roughness=60, bluntness=60, courtesy=30))
        texts = (['고마워 오늘도 같이 이야기해 줘서', '부탁할게 내 이야기를 잠깐 들어 줘', '수고했어 덕분에 기분이 좋아']
                 if polite else ['아 젠장 오늘 버스를 놓쳤어', '존나 귀찮은 일이 생겼네', '씨발 비가 와서 신발이 다 젖었어'])
        for _ in range(3 if polite else 10):
            for day in range(7):
                for text in texts[:2] if day == 0 else texts[2:] if day == 1 else []:
                    add('conversation', text=text, analysis={'target': 'other', 'sentiment': 'neutral',
                        'motivation': 'none', 'character_affection': 'neutral', 'acceptance': 'none', 'analysis_confidence': 1})
                add('time', action='advance', days=1)
            add('time', action='weekly')
        return commands

    if name.startswith('evolution_'):
        # Threshold demonstrations are explicit manual overrides, not earned growth claims.
        levels = RULES['evolution']['levels']
        state = dict(session['state'], level=levels[0] if name == 'evolution_fat' else levels[1],
                     upper_body=82 if name == 'evolution_fat' else 38,
                     lower_body=79 if name == 'evolution_fat' else 40,
                     nutrition=80 if name == 'evolution_fat' else 42,
                     energy_balance=5 if name == 'evolution_fat' else 70,
                     evolution_stage=0, body_type='initial', previous_evolution={})
        add('manual_override', state=state)
        add('evolution', apply=True)
        state.update(level=levels[1] if name == 'evolution_fat' else levels[2],
                     upper_body=38 if name == 'evolution_fat' else 82,
                     lower_body=40 if name == 'evolution_fat' else 79,
                     nutrition=42 if name == 'evolution_fat' else 80,
                     energy_balance=70 if name == 'evolution_fat' else 5,
                     evolution_stage=1 if name == 'evolution_fat' else 2,
                     body_type='balanced_exercise' if name == 'evolution_fat' else 'fat_gain',
                     previous_evolution={'evolution_stage': 1 if name == 'evolution_fat' else 2,
                                         'final_body_type': 'balanced_exercise' if name == 'evolution_fat' else 'fat_gain'})
        add('manual_override', state=state)
        add('evolution', apply=True)
        return commands
    duration = 14 if name == 'stop_next_week' else 7
    for day in range(duration):
        if name in ('exercise_7', 'upper_only', 'lower_only', 'balanced') or name == 'stop_next_week' and day < 7:
            add('exercise', exercise_type='pushup' if name == 'upper_only' else 'squat',
                category='upper' if name == 'upper_only' else 'lower' if name == 'lower_only' else 'full',
                actual=50, target=50, unit='count', verification_status='verified')
        if name in ('balanced', 'overeat'):
            add('food', raw_text='synthetic balanced meal' if name == 'balanced' else 'synthetic excessive meal',
                analysis={k: 'proper' if name == 'balanced' else 'low' if k == 'vegetable' else 'high'
                          for k in ('protein', 'carbohydrate', 'fat', 'vegetable', 'amount')},
                amount_severity='extreme' if name == 'overeat' else 'normal')
        if name in ('positive_chat', 'exercise_profanity'):
            positive = name == 'positive_chat'
            add('conversation', text='네 응원이 좋아, 고마워!' if positive else '운동하기 존나 싫다',
                analysis={'target': 'character' if positive else 'exercise', 'sentiment': 'positive' if positive else 'negative',
                          'motivation': 'none' if positive else 'low', 'character_affection': 'positive' if positive else 'neutral',
                          'acceptance': 'none', 'analysis_confidence': 1})
        if name == 'reject_proposals':
            qid = f'preset-proposal-{start}-{day}'
            add('quest', action='create', quest_id=qid)
            add('quest', action='reject', quest_id=qid)
        add('time', action='advance', days=1)
        if (day+1) % 7 == 0:
            add('time', action='weekly')
    return commands


def preview(name, session=None):
    session = session or fresh()
    commands = commands_for(name, session)
    result = execute(session, commands)
    result.update(preset=name, label=PRESETS[name], commands=commands, training_data=False,
                  timeline=[{'date': x['result_virtual_date'], 'before': x['before'], 'after': x['after'],
                             'rules': x['applied_rules']} for x in result['results']])
    return result
