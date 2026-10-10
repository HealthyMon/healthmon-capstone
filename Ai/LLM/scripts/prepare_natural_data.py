"""Write small authored additions and frozen development cases without replacing originals."""
import copy
import hashlib
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.agent import validate
from src.rules import RULES


def answer(speech, emotion='neutral', animation='idle', memory_ids=None):
    return {'speech': speech, 'emotion': emotion, 'animation': animation,
            'action': {'type': 'none', 'target_id': None}, 'memory_ids': memory_ids or [], 'personality_update': None}


def main():
    target = ROOT / 'data/natural_sft_v1'
    evaluation = ROOT / 'data/natural_eval_v1'
    if target.exists() or evaluation.exists():
        raise RuntimeError('Version exists; choose a new data version')
    target.mkdir(parents=True); evaluation.mkdir(parents=True)
    base = {'settings': {'name': '몽글이', 'speech_level': 'casual', 'profanity': 'none'},
            'traits': copy.deepcopy(RULES['initial']), 'mood': {'valence': 0, 'energy': 50},
            'recent': [], 'memories': [], 'activities': [], 'candidates': [], 'active_quests': []}
    authored = [
        ('작은실수', '양말을 짝짝이로 신고 나왔네.', '오늘 양말끼리 각자 취향이 있나 봐.', {'playfulness': 85}, [], []),
        ('지루함', '기다리는 시간이 왜 이렇게 안 가지.', '시계가 멈춘 것 같지. 이럴 때 꼭 더 느리더라.', {}, [], []),
        ('책감상', '읽던 책 결말이 너무 허무했어.', '끝까지 읽었는데 결말이 힘을 빼 버렸네.', {}, [], []),
        ('작은기쁨', '잃어버린 이어폰 찾았어.', '오, 어디 숨어 있었어?', {'sociability': 80}, [], []),
        ('조용한동행', '말 안 하고 잠깐 같이 있고 싶어.', '응. 여기 있을게.', {'bluntness': 80}, [], []),
        ('마무리', '오늘 이야기는 여기까지 하자.', '그래, 편하게 쉬어.', {}, [], []),
        ('칭찬부담', '별것도 아닌데 너무 칭찬하니까 부담돼.', '알겠어. 과하게 띄우지 않을게.', {}, [], []),
        ('의견', '비 오는 날 창문 열어 두는 게 좋아.', '빗소리 들으려고? 바람까지 들어오면 꽤 분위기 있겠다.', {'playfulness': 75}, [], []),
        ('설명요청', '일정이 겹쳤을 때 어떻게 정리하면 좋을까?', '시간을 옮길 수 없는 일정부터 남겨 봐. 나머지는 다른 날로 바꾸거나 참석 시간을 나누고, 둘 다 어렵다면 먼저 약속한 쪽에 사정을 알려 주는 게 좋겠어.', {'courtesy': 80}, [], []),
        ('이전주제', '그래서 아직 고르는 중이야.', '아까 말한 휴대폰 케이스? 오래 쓸 거면 덜 질리는 쪽으로 골라도 좋겠다.', {}, [{'user':'휴대폰 케이스 색을 못 고르겠어.','assistant':'어떤 색들인데?'}], []),
        ('까칠수용', '오늘 아무것도 하기 싫어.', '그런 날도 있지. 오늘은 좀 내려놔.', {'bluntness': 85}, [], []),
        ('기억활용', '내가 좋아하는 차 기억해?', '보리차 좋아한다고 했지.', {}, [], [{'id':'tea-memory','content':'나는 보리차를 좋아해.','slot':'preference','source_id':'synthetic-tea','source_revision':1}]),
        ('검증일상', '엘리베이터가 눈앞에서 닫혔어.', '딱 한 걸음 늦었네. 그 순간이 은근 짜증 나지.', {}, [], []),
        ('검증형식', '더 묻지 말고 그냥 들어줘.', '응, 듣고 있어.', {'sociability':85}, [], []),
        ('검증진지', '장난하지 말고 진지하게 들어 줘.', '알겠어. 진지하게 들을게.', {'playfulness':90}, [], []),
        ('검증감사', '얘기 들어줘서 고마워.', '말해 줘서 나도 좋았어.', {}, [], []),
    ]
    rows = []
    for index, (group, text, speech, traits, recent, memories) in enumerate(authored):
        context = copy.deepcopy(base); context['traits'].update(traits); context['recent'] = recent; context['memories'] = memories
        row = {'id': f'natural-authored-{index:02}', 'scenario_group': group, 'context': context,
               'user_text': text, 'answer': answer(speech, memory_ids=[m['id'] for m in memories]),
               'source': 'agent_authored_original', 'human_review': False}
        validate(json.dumps(row['answer'], ensure_ascii=False), context, text)
        rows.append(row)
    # Small feasibility run, including retained original personality examples.
    old = [json.loads(line) for line in (ROOT/'data/pilot_v2/train.jsonl').read_text(encoding='utf-8').splitlines()]
    retained = [copy.deepcopy(row) for row in old if any(row['context']['traits'].get(k,0)>=70 for k in ('playfulness','bluntness','courtesy','roughness'))][:4]
    splits = {'train': rows[:12] + retained, 'validation': rows[12:]}
    for split, values in splits.items():
        (target/f'{split}.jsonl').write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in values),encoding='utf-8')
    manifest = {'version':'natural_sft_v1','source':'16 individually authored synthetic additions; 4 retained pilot personality examples',
                'counts':{key:len(value) for key,value in splits.items()},'human_review':False,'external_data_count':0,
                'paid_api_used':False,'training_scope':'small feasibility run, no production selection',
                'retained_source':'data/pilot_v2/train.jsonl',
                'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in target.glob('*.jsonl')}}
    (target/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    # Distinct scenarios; this is a developer regression set, not an independent benchmark.
    specs = [
        ('bus','버스를 놓쳤는데 다음 차가 20분 뒤래.',{},[],[]),
        ('movie','영화 예고편만 세 시간째 보고 있어.',{'activity':85,'initiative':85},[],[]),
        ('silence','조언은 됐고 잠깐 들어주기만 해.',{'affection':85,'initiative':90},[],[]),
        ('work','메일 한 줄 쓰는 데 한 시간 걸렸어.',{'roughness':65,'bluntness':75},[],[]),
        ('goodnight','나 이제 잘게.',{},[],[]),
        ('continuity','그 배우가 마지막에 다시 나온 게 좋았어.',{},[{'user':'어제 본 영화에서 조연이 제일 좋더라.','assistant':'짧게 나와도 인상적인 배우가 있지.'}],[]),
        ('preference','내가 좋아하는 운동 기억해?',{},[],[{'id':'swim','content':'나는 달리기보다 수영을 좋아해.','source_id':'synthetic-swim','slot':'preference'}]),
        ('correction','지금 내가 좋아하는 시간대가 언제지?',{},[{'user':'전에는 저녁이 좋았는데 지금은 오후가 좋아.','assistant':'알겠어.'}],[{'id':'time','content':'나는 저녁보다 오후에 산책하는 것을 좋아해.','source_id':'synthetic-time','slot':'preference','source_revision':2}]),
        ('no_memory','지난주에 내가 본 영화 기억해?',{},[],[]),
        ('formal','택배 상자가 생각보다 엄청 컸어요.',{'courtesy':90},[],[]),
        ('rest','운동 얘기는 그만하고 오늘은 푹 쉴래.',{'activity':95,'initiative':95},[],[]),
        ('distress','친구와 말다툼해서 속상해.',{'roughness':85,'bluntness':85,'mood':-25},[],[]),
        ('detail','약속 시간을 자꾸 헷갈리는데 정리하는 방법을 자세히 알려줘.',{},[],[]),
        ('play','계획은 완벽한데 실행 버튼을 못 찾겠어.',{'activity':80,'initiative':70,'affection':75},[],[]),
        ('reserved','오늘은 그냥 평범한 하루였어.',{'affection':20,'initiative':15},[],[]),
        ('warm','오늘은 그냥 평범한 하루였어.',{'affection':90,'initiative':75},[],[]),
    ]
    cases = [{'id':key,'text':text,'state':state,'recent':recent,'memories':memories,
              'speech_level':'formal' if key=='formal' else 'casual',
              'expect':{'unrelated_quest':False,'personality_update':None,'review_all_eight_criteria':True}}
             for key,text,state,recent,memories in specs]
    (evaluation/'cases.json').write_text(json.dumps({'version':'natural_eval_v1','human_review':False,
        'independent_benchmark':False,'cases':cases},ensure_ascii=False,indent=2),encoding='utf-8')
    (evaluation/'manifest.json').write_text(json.dumps({'count':len(cases),'sha256':hashlib.sha256((evaluation/'cases.json').read_bytes()).hexdigest(),
        'source':'Agent-authored synthetic regression cases; frozen before this task training',
        'human_review':False,'external_data_count':0},indent=2),encoding='utf-8')
    print(json.dumps({'training':manifest['counts'],'evaluation_cases':len(cases)}))


if __name__ == '__main__':
    main()
