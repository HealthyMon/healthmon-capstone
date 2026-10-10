"""Gradual sandbox expression adaptation, independent of Affinity and legacy axes.

These rules recognize repeated own language, not whether a user is a good person.
They never generate speech, modify the legacy store, or treat dummy output as Qwen.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parents[1] / 'config' / 'character_expression.json'
EXPRESSION = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
DEFAULTS = {'roughness': 10, 'bluntness': 20, 'courtesy': 60}


def _matches(patterns, text):
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _preference_text(text):
    """Remove known negated refusals/symptoms before applying lexical controls.

    Reuse the catalog's Korean refusal negations so quest choice and expression
    agree. This is a bounded rule for explicit phrases, not general language
    understanding. A later affirmative clause remains available for matching.
    """
    from .persona_quests import load_catalog
    rules = load_catalog()['selection'].get('current_turn_exercise_refusal', {})
    for pattern in rules.get('negated_patterns', []):
        text = re.sub(pattern, '', text)
    for pattern in (
        r'(?:힘들|아프|싫|무섭|슬프|괴롭)(?:지|지는|진)\s*않[가-힣]*',
        r'(?:힘든|아픈|싫은|무서운|슬픈|괴로운)\s*(?:건|것|게|거)(?:은|이|가)?\s*(?:아니|아냐)[가-힣]*',
        r'(?:피곤|우울|불안)하(?:지|지는|진)\s*않[가-힣]*',
        r'(?:피곤|우울|불안)한\s*(?:건|것|게|거)(?:은|이|가)?\s*(?:아니|아냐)[가-힣]*',
        r'(?:안|전혀|하나도)\s*(?:힘들|아프|피곤|우울|불안)[가-힣]*',
        r'(?:힘들|아프|싫|무섭|슬프|괴롭)(?:다는|다고)\s*(?:건|것|게|거)(?:은|이|가)?\s*(?:아니|아냐)[가-힣]*',
    ):
        text = re.sub(pattern, '', text)
    return text


def _own_text(text):
    """Ignore quoted examples, copied output and instructions about the evaluator."""
    text = unicodedata.normalize('NFKC', str(text)).casefold()
    text = re.sub(r'```.*?```', ' ', text, flags=re.DOTALL)
    text = re.sub(r'(?m)^\s*>.*$', ' ', text)
    for pattern in (r'`[^`]*`', r'"[^"\n]*"', r"'[^'\n]*'", r'“[^”]*”', r'‘[^’]*’', r'「[^」]*」', r'『[^』]*』'):
        text = re.sub(pattern, ' ', text)
    if _matches(EXPRESSION['instruction_patterns'], text):
        return ''
    return text.strip()


def _normalized(text):
    # Punctuation, counters and artificial repeated spelling cannot manufacture evidence.
    text = re.sub(r'[\W\d_]+', '', text, flags=re.UNICODE)
    return re.sub(r'(.)\1{2,}', r'\1\1', text)


def _rough(text):
    for exclusion in EXPRESSION['rough_term_exclusions']:
        text = text.replace(unicodedata.normalize('NFKC', exclusion).casefold(), '')
    for term in EXPRESSION['rough_terms']:
        term = unicodedata.normalize('NFKC', term).casefold()
        if term.isascii():
            if re.search(r'\b' + re.escape(term) + r'(?:ing|ed|er|s)?\b', text):
                return True
        elif term in text:
            return True
    return False


def expression_weekly(events: list[dict], state: dict) -> dict:
    """Compute bounded deltas from an already bounded weekly event window.

    Replays and overlapping windows remain the caller's existing responsibility.
    No single message or repeated paste changes expression. At least three distinct
    trusted own messages across two dates and a majority signal are required.
    """
    distinct = {}
    excluded = {'untrusted': 0, 'quoted_or_instruction': 0, 'duplicate_text': 0}
    for event in events:
        if event.get('kind') != 'conversation':
            continue
        payload, result = event.get('payload', {}), event.get('result', {})
        confidence = payload.get('analysis', {}).get('analysis_confidence', 0)
        if (result.get('long_term_eligible') is not True or result.get('review_required', False)
                or confidence < EXPRESSION['minimum_analysis_confidence']):
            excluded['untrusted'] += 1
            continue
        text = _own_text(payload.get('text', ''))
        normalized = _normalized(text)
        if not normalized:
            excluded['quoted_or_instruction'] += 1
            continue
        if normalized in distinct:
            excluded['duplicate_text'] += 1
            continue
        rough = _rough(text)
        distinct[normalized] = {
            'event_id': event.get('event_id'), 'date': event.get('virtual_test_date'),
            'rough': rough,
            # Mixed rough/polite messages remain rough evidence, not recovery evidence.
            'polite': not rough and any(term in text for term in EXPRESSION['polite_terms']),
        }
    rows = list(distinct.values())
    rough = [row for row in rows if row['rough']]
    polite = [row for row in rows if row['polite']]

    def sustained(signal):
        return (len(signal) >= EXPRESSION['minimum_distinct_texts']
                and len({row['date'] for row in signal if row['date']}) >= EXPRESSION['minimum_distinct_dates']
                and len(signal) / max(1, len(rows)) >= EXPRESSION['minimum_signal_ratio'])

    signal = 'repeated_rough_language' if sustained(rough) else 'repeated_polite_language' if sustained(polite) else 'insufficient_repeated_evidence'
    changes = (EXPRESSION['rough_delta'] if signal == 'repeated_rough_language'
               else EXPRESSION['polite_delta'] if signal == 'repeated_polite_language' else dict.fromkeys(DEFAULTS, 0))
    deltas, reasons = {}, []
    for axis, requested in changes.items():
        current = float(state.get(axis, DEFAULTS[axis]))
        bounded = min(EXPRESSION['weekly_max_delta'], max(-EXPRESSION['weekly_max_delta'], requested))
        delta = round(min(100, max(0, current + bounded)) - current, 6)
        deltas[axis] = delta
        reasons.append({'axis': axis, 'delta': delta, 'applied_rule': 'provisional:expression:' + signal,
                        'reason': f'{len(rough)} rough/{len(polite)} polite of {len(rows)} distinct trusted own texts; bounded weekly update'})
    return {'deltas': deltas, 'reasons': reasons,
            'evidence': {'distinct_text_count': len(rows), 'rough_count': len(rough), 'polite_count': len(polite),
                         'rough_date_count': len({x['date'] for x in rough if x['date']}),
                         'polite_date_count': len({x['date'] for x in polite if x['date']}),
                         'event_ids': [x['event_id'] for x in (rough if signal == 'repeated_rough_language' else polite if signal == 'repeated_polite_language' else [])],
                         'excluded': excluded, 'signal': signal},
            'rule_version': EXPRESSION['version'], 'provisional': True}


def expression_profile(state: dict, text: str) -> dict:
    """Pure controls/guidance; actual model speech still requires Qwen evaluation."""
    cfg = EXPRESSION['profile']
    axes = {axis: min(100, max(0, float(state.get(axis, default)))) for axis, default in DEFAULTS.items()}
    activity, initiative = float(state['activity']), float(state['initiative'])
    negative_mood = state['mood'] < 0
    preference = _preference_text(text)
    stop = _matches(cfg['stop_style_patterns'], preference)
    distress = _matches(cfg['distress_patterns'], preference)
    rest = _matches(cfg['rest_patterns'], preference)
    mockery_allowed = not (stop or distress)
    voice = 'sassy' if axes['roughness'] >= cfg['sassy_roughness'] and mockery_allowed else 'default'
    behavior = ('support_listen' if distress else 'rest_listen' if rest or negative_mood
                or activity < cfg['low_axis'] or initiative < cfg['low_axis'] else
                'exercise_optional' if activity >= cfg['high_axis'] and initiative >= cfg['high_axis'] else 'responsive')
    guidance = []
    if voice == 'default' and axes['roughness'] >= cfg['casual_roughness'] and mockery_allowed:
        guidance.append('툴툴대는 짧은 구어체를 조금 섞되 실제 도움을 먼저 준다. 같은 감탄사를 반복하지 않는다.')
    if axes['bluntness'] >= cfg['direct_bluntness']:
        guidance.append('결론을 짧고 직설적으로 말한다. 사용자의 선택은 존중하고 무례한 평가나 욕설은 쓰지 않는다.')
    elif axes['bluntness'] < cfg['low_axis']:
        guidance.append('명령형보다 부드러운 제안형을 쓴다. 실제 질문에 먼저 답한다.')
    if axes['courtesy'] >= cfg['polite_courtesy']:
        guidance.append('선택된 반말/존댓말을 유지하며 감사와 배려를 자연스럽게 표현한다. 과한 칭찬은 덧붙이지 않는다.')
    elif axes['courtesy'] < cfg['low_axis']:
        guidance.append('의례적인 인사와 긴 위로를 줄이고 짧게 받아친다. 사람을 모욕하거나 깎아내리지는 않는다.')
    if stop or distress:
        guidance.append('이번 응답은 빈정거림과 놀림을 멈춘다. 사용자의 요청이나 힘든 상황을 진지하고 담백하게 받아준다.')
    if behavior == 'exercise_optional':
        guidance.append('활동성과 주도성이 높다. 활동 관련 대화나 다음 행동을 묻는 상황이면 서버 후보의 운동 한 가지를 선택 사항으로 제안한다. 무관한 질문에는 운동 권유를 붙이지 않는다.')
    elif behavior in ('rest_listen', 'support_listen'):
        guidance.append('지금은 휴식과 듣기를 먼저 선택한다. 새 운동이나 퀘스트를 먼저 권하지 않고 사용자의 실제 질문에 짧게 답한다. 요청한 활동 정보는 제공할 수 있다.')
    else:
        guidance.append('사용자가 관심을 보이거나 다음 행동을 물으면 선택 사항 한 가지만 제안한다. 대화마다 운동을 권하지 않는다.')
    guidance.append('표현 적응은 어감과 문장 구조에만 적용한다. 사용자 욕설을 그대로 복사하거나 Affinity·퀘스트 목표·보상을 임의로 바꾸지 않는다.')
    return {**axes, 'voice_id': voice, 'behavior': behavior, 'mockery_allowed': mockery_allowed,
            'stop_style_requested': stop, 'sensitive_distress': distress, 'rest_requested': rest,
            'effective_initiative': round(initiative / 100 * (cfg['negative_mood_initiative_multiplier'] if negative_mood else 1), 4),
            'guidance': guidance, 'version': EXPRESSION['version'], 'provisional': True}
