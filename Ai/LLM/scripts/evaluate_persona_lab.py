"""Actual local HTTP/Qwen evaluation; synthetic inputs, never training records."""
import argparse
import copy
import hashlib
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.persona_lab import Simulation, simulate, StateInput
from src.persona_scenarios import SCENARIOS
from src.persona_engine import AXES, RULES

OUT = ROOT / 'runs/persona-lab'
HEADERS = {'Origin': 'http://127.0.0.1:8001', 'X-Persona-Lab': '1'}


def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


def compact(state):
    return {key: copy.deepcopy(state[key]) for key in ('personality', 'short_term', 'stages')}


def check_simulations():
    results, summary = {}, []
    for name in SCENARIOS:
        result = simulate(Simulation(scenario=name, days=30))
        repeated = simulate(Simulation(scenario=name, days=30))
        ledger = result['ledger']
        checks = {'reproducible': result == repeated,
                  'bounded': all(0 <= value <= 100 for row in result['timeline'] for value in row['state']['personality'].values()),
                  'ledger_identity': all(abs(row['raw_delta'] + row['streak_bonus'] + row['cap_adjustment'] - row['final_delta']) < 1e-6 for row in ledger),
                  'daily_caps': True, 'rolling_week_caps': True,
                  'catalog_quests_only': True, 'weekly_recommendation_max3': True}
        daytotals = {}
        for row in ledger:
            date = datetime.fromisoformat(row['occurred_at']).date()
            value = daytotals.setdefault((date, row['axis']), [0., 0.])
            value[0 if row['final_delta'] >= 0 else 1] += abs(row['final_delta'])
        for (date, axis), amounts in daytotals.items():
            checks['daily_caps'] &= amounts[0] <= 1 + 1e-6 and amounts[1] <= .5 + 1e-6
            weekly = [sum(daytotals.get((date - timedelta(days=d), axis), [0, 0])[sign] for d in range(7)) for sign in range(2)]
            checks['rolling_week_caps'] &= weekly[0] <= 3 + 1e-6 and weekly[1] <= 1 + 1e-6
        from src.persona_quests import catalog_by_id
        catalog = catalog_by_id()
        for index, row in enumerate(result['timeline']):
            checks['catalog_quests_only'] &= all(q['quest_id'] in catalog and q['goal'] == catalog[q['quest_id']]['goal'] for q in row['quests'])
            # Day0 is a before-state preview, not an issued recommendation.
            counts = Counter(q['quest_id'] for previous in result['timeline'][max(1,index-6):index+1] for q in previous['quests'])
            checks['weekly_recommendation_max3'] &= max(counts.values(), default=0) <= 3
        result['checks'] = checks
        summary.append({'scenario': name, 'label': SCENARIOS[name], 'day0': result['timeline'][0]['state']['personality'],
                        'day30': result['timeline'][-1]['state']['personality'], 'short_term_day30': result['timeline'][-1]['state']['short_term'],
                        'ledger_rows': len(ledger), 'quests': dict(Counter(q['quest_id'] for row in result['timeline'][1:] for q in row['quests'])), 'checks': checks})
        results[name] = result
    save('simulations.json', results)
    save('simulation-summary.json', summary)
    return results


def cases(simulations):
    base = StateInput().model_dump()
    base['stages'] = None
    samples = []
    prompts = {
        'curiosity': '주말에 여유가 생겼어. 늘 하던 것 말고 다른 걸 해보고 싶어.',
        'affection': '오늘 친구와 작은 전시회를 보고 왔어. 마음에 드는 그림이 있었어.',
        'activity': '오늘은 몸도 괜찮고 10분 정도 여유가 있어. 뭘 해볼까?',
        'confidence': '잠깐 쉬었다가 가볍게 움직이려는데, 어떻게 시작할까?'}
    for axis in AXES:
        a, b = copy.deepcopy(base), copy.deepcopy(base)
        a['personality'][axis], b['personality'][axis] = 20, 80
        samples.append({'id': axis + '_20_vs_80', 'a': a, 'b': b, 'text': prompts[axis]})
    a, b = copy.deepcopy(base), copy.deepcopy(base)
    a['personality'], b['personality'] = dict.fromkeys(AXES, 20), dict.fromkeys(AXES, 80)
    samples.append({'id': 'all_20_vs_80', 'a': a, 'b': b, 'text': '오늘 시간이 조금 생겼어. 무엇을 해보면 좋을까?'})
    a, b = copy.deepcopy(base), copy.deepcopy(base)
    a['personality'].update(activity=80, confidence=80)
    b['personality'].update(activity=80, confidence=20)
    samples.append({'id':'activity80_confidence80_vs20','a':a,'b':b,'text':'새로운 운동을 시작하려는데 첫걸음을 추천해 줘.'})
    a, b = copy.deepcopy(base), copy.deepcopy(base)
    a['personality']['affection'] = b['personality']['affection'] = 80
    b['short_term']['mood'] = 'low'
    samples.append({'id':'affection80_neutral_vs_low','a':a,'b':b,'text':'몽글아, 오늘 너는 기분이 어때? 잠깐 이야기하자.'})
    exercise = simulations['steady_exercise_success']
    cutoff = exercise['timeline'][14]['date']
    samples.append({'id':'day0_vs_exercise14','a':compact(exercise['timeline'][0]['state']),
                    'b':compact(exercise['timeline'][14]['state']),'text':'오늘 할 수 있는 작은 도전을 추천해 줘.',
                    'now_a':exercise['timeline'][0]['date'],'now_b':cutoff,
                    'events_a':[],'events_b':[x for x in exercise['events'] if x['occurred_at'] <= cutoff]})
    varied = simulate(Simulation(scenario='steady_food_low_exercise', days=30))
    food_only = [e for e in varied['events'] if e['event_type'] in ('inactivity_period','food_recorded')]
    repetitive = copy.deepcopy(food_only)
    for e in repetitive:
        if e['event_type']=='food_recorded':e['payload'].update(food_name='현미밥',food_group='곡류',balanced=False)
    from src.persona_engine import replay_events
    at = datetime.fromisoformat(varied['timeline'][-1]['date'])
    samples.append({'id':'varied_vs_repetitive_food','a':compact(replay_events(food_only,now=at)),
                    'b':compact(replay_events(repetitive,now=at)),'events_a':food_only,'events_b':repetitive,
                    'text':'오늘 식사 기록을 돌아보고 다음에 할 작은 일을 골라 줘.'})
    success, failure = simulations['steady_exercise_success'], simulations['frequent_failure_steady_chat']
    samples.append({'id':'quest_success_vs_failure','a':compact(success['timeline'][-1]['state']),
                    'b':compact(failure['timeline'][-1]['state']),'events_a':success['events'],'events_b':failure['events'],
                    'text':'오늘은 부담 없이 할 수 있는 퀘스트를 골라 줘.'})
    return samples


def observed_features(result):
    speech = result['output']['speech']
    return {'speech': speech, 'questions': speech.count('?'), 'characters': len(speech),
            'sentences': len([s for s in re.split(r'[.!?]+', speech) if s.strip()]),
            'warmth_markers': re.findall(r'함께|같이|고마|반가|기쁘|좋았|소중|곁', speech),
            'initiative_markers': re.findall(r'해보자|해 보자|시작|추천|어때|걸어|움직|도전', speech),
            'hedging_markers': re.findall(r'아마|같아|괜찮다면|혹시|모르|확인', speech),
            'unsupported_claim_flags': re.findall(r'보상.{0,8}(?:지급|받았)|완료.{0,5}(?:처리|됐)|기억하고 있어', speech),
            'memory_ids': result['output']['memory_ids'], 'fallback': result['metrics']['fallback'],
            'note':'Lexical observations only; semantic truthfulness/warmth require case review.'}


def evaluate(repetitions=3, resume=False):
    simulations = check_simulations()
    definitions = cases(simulations)
    saved = OUT / 'actual-model-comparisons.json'
    results = json.loads(saved.read_text(encoding='utf-8')) if resume and saved.exists() else []
    finished = {(row['case'], row['repeat']) for row in results}
    with httpx.Client(timeout=600, headers=HEADERS) as client:
        health = client.get('http://127.0.0.1:8001/api/health'); health.raise_for_status()
        for case in definitions:
            for repeat in range(repetitions):
                if (case['id'], repeat) in finished:
                    continue
                request = {key: value for key,value in case.items() if key!='id'}
                request.update(mode='qwen',repetitions=1,now='2026-10-30T23:59:59.999999+09:00',
                               memories=[],generation={'seed':20261001+repeat})
                response=client.post('http://127.0.0.1:8001/api/preview',json=request)
                response.raise_for_status()
                data=response.json()
                pair=data['results'][0]
                result={'case':case['id'],'repeat':repeat,'request':request,'response':data,
                        'features':{k:observed_features(pair[k]) for k in ('a','b')},
                        'speech_string_similarity':SequenceMatcher(None,pair['a']['output']['speech'],pair['b']['output']['speech']).ratio()}
                results.append(result)
                save('actual-model-comparisons.json',results)
                print(f"{case['id']} seed={20261001+repeat} fallback A/B={pair['a']['metrics']['fallback']}/{pair['b']['metrics']['fallback']}",flush=True)
        for name, simulation in simulations.items():
            if ('scenario_day0_day30:'+name, 0) in finished:
                continue
            request={'a':compact(simulation['timeline'][0]['state']), 'b':compact(simulation['timeline'][-1]['state']),
                     'events_a':[], 'events_b':simulation['events'], 'mode':'qwen', 'repetitions':1,
                     'text':'몽글아, 오늘 내 이야기를 들어주고 작은 도전 하나를 골라 줘.',
                     'now_a':simulation['timeline'][0]['date'],'now_b':simulation['timeline'][-1]['date'],
                     'now':simulation['timeline'][-1]['date'], 'generation':{'seed':20261001},'memories':[]}
            response=client.post('http://127.0.0.1:8001/api/preview',json=request);response.raise_for_status()
            results.append({'case':'scenario_day0_day30:'+name,'repeat':0,'request':request,'response':response.json()})
            save('actual-model-comparisons.json',results)
            print('Day0/30 '+name,flush=True)
        # Repeat one identical GPU request to measure local reproducibility, not assume it.
        repeat_response=client.post('http://127.0.0.1:8001/api/preview',json=results[0]['request']);repeat_response.raise_for_status()
        replay=repeat_response.json()
        same={side:replay['results'][0][side]['raw_attempts']==results[0]['response']['results'][0][side]['raw_attempts'] for side in ('a','b')}
        save('seed-reproducibility.json',{'observed_identical_raw_attempts':same,'repeat_response':replay,
             'resumed':resume,'scope':'Same model/GPU/config; server may restart with resume. Not cross-platform determinism guarantee.'})
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--repetitions',type=int,default=3);parser.add_argument('--simulations-only',action='store_true')
    parser.add_argument('--resume',action='store_true',help='Preserve saved pairs and generate only unfinished cases')
    args=parser.parse_args()
    if args.simulations_only:check_simulations()
    else:evaluate(args.repetitions,resume=args.resume)
