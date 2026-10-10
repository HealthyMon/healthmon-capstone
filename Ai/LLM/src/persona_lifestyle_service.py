"""Dry-run projections over the existing growth engine; no store or model ownership."""
import copy
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from .persona_engine import RULES, replay_events
from .persona_ledger import summarize_ledger
from .persona_runtime import prepare_context
from .persona_quests import select_quests

TEST_QUESTIONS = [
    '오늘 운동하기 싫어.', '오늘은 뭘 해볼까?', '이번 주는 거의 운동을 못 했어.',
    '새로운 음식을 먹어봤어.', '요즘 퀘스트를 계속 실패하고 있어.', '이번 주 운동 목표를 전부 달성했어.',
]


def lifestyle_projection(body):
    from .persona_lifestyle import compile_lifestyle
    compiled = compile_lifestyle(body.records, body.start)
    events = compiled['events']
    initial = body.initial.personality.model_dump()
    short = body.initial.short_term.model_dump()
    days = compiled['requested']['days']
    timeline = []
    for day in range(days + 1):
        at = body.start if day == 0 else body.start + timedelta(days=day) - timedelta(microseconds=1)
        visible = [e for e in events if datetime.fromisoformat(e['occurred_at']) <= at]
        state = replay_events(visible, now=at, initial=initial, short_term=short)
        state['character_voice'] = body.initial.character_voice
        # An inspection is not a quest proposal/acceptance. Do not create extra events.
        quests = select_quests(state, visible, at, limit=3, user_text='오늘은 뭘 해볼까?')
        timeline.append({'day': day, 'date': at.isoformat(), 'state': state, 'quests': quests})
    before, after = timeline[0]['state'], timeline[-1]['state']
    ledger = after['ledger']
    daily = defaultdict(lambda: {'positive': 0., 'negative': 0., 'streak_bonus_requested': 0., 'cap_adjustment': 0.})
    for row in ledger:
        key = (datetime.fromisoformat(row['occurred_at']).astimezone(body.start.tzinfo).date().isoformat(), row['axis'])
        item = daily[key]
        item['positive' if row['final_delta'] >= 0 else 'negative'] += abs(row['final_delta'])
        item['streak_bonus_requested'] += row['streak_bonus']
        item['cap_adjustment'] += row['cap_adjustment']
    caps = []
    for (date, axis), item in sorted(daily.items()):
        d = datetime.fromisoformat(date).date()
        week = [daily.get(((d - timedelta(days=offset)).isoformat(), axis), {}) for offset in range(7)]
        caps.append({'date': date, 'axis': axis, **{k: round(v, 6) for k, v in item.items()},
                     'rolling_7day_positive': round(sum(x.get('positive', 0) for x in week), 6),
                     'rolling_7day_negative': round(sum(x.get('negative', 0) for x in week), 6)})
    audit = after['event_audit']
    return {'days': days, 'dry_run': True, 'production_write': False, 'database_write': False,
            'synthetic': True, 'model_generated': False, 'compiled': compiled,
            'initial': before, 'final': after, 'timeline': timeline, 'events': events,
            'ledger': ledger, 'ledger_summary': summarize_ledger(initial, after['personality'], ledger),
            'short_term_change': {key: {'before': before['short_term'][key], 'after': after['short_term'][key],
                                      'delta': None if key == 'mood' else round(after['short_term'][key] - before['short_term'][key], 6)}
                                  for key in short},
            'caps': {'limits': copy.deepcopy(RULES['limits']), 'daily_and_rolling_week': caps,
                     'clipped_ledger_rows': [row for row in ledger if row['cap_adjustment']]},
            'event_audit_summary': dict(Counter(row['status'] for row in audit)),
            'ignored_duplicates': [row for row in audit if row['status'] == 'duplicate'],
            'unapplied_events': [row for row in audit if row['status'] not in ('applied', 'duplicate', 'anchor_only', 'accepted', 'proposed', 'progressed', 'completed', 'failed', 'transient_only', 'context_only', 'cancelled_or_declined')],
            'streak_rows': [row for row in ledger if row['streak_bonus']]}


def lifestyle_contexts(body, projection):
    # Use one comparison clock. Only the record history and its derived state change.
    at = datetime.fromisoformat(projection['timeline'][-1]['date'])
    memories = [x.model_dump() for x in body.memories]
    before = copy.deepcopy(projection['initial'])
    before['as_of'] = at.isoformat()
    contexts = {
        'a': prepare_context(before, [], at, body.text, memories, body.speech_level),
        'b': prepare_context(projection['final'], projection['events'], at, body.text, memories, body.speech_level),
    }
    for context in contexts.values():
        # Aggregate minutes contain no pedometer measurement. Absence is not zero.
        for period in ('requested_period', 'last_7_days'):
            context['activity_summary'][period]['confirmed_steps'] = 'unknown'
            context['activity_summary'][period]['step_measurement'] = 'not_provided'
        context['record_scope'] = {
            'kind': 'synthetic_lifestyle_dry_run',
            'date_allocation': '기간 합계를 가상 날짜로 배분했다. 실제 날짜별 활동으로 단정하지 않는다.',
            'exercise_identity': '상체·하체·유산소·유연성의 대표 유형만 사용했다. 실제 운동 종류는 unknown이며 자전거 등 특정 종목의 실제 실적을 단정하지 않는다.',
            'food_identity': '음식·음식군 이름은 가상 표기다. 실제 음식 이름, 칼로리, 영양소는 unknown이다.',
        }
    return contexts
