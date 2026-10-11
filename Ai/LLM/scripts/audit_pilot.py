"""Auditable retrospective labels; all judgments are agent judgments, not human review."""
import json,hashlib,collections,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runs/improvement-20260929'
flows=json.loads((ROOT/'runs/flows-development.json').read_text(encoding='utf-8'))['flows']
# Conservative confirmed issues. Multiple labels may apply; do not add their counts as turns.
labels={
 'change_play:7':{'tone':'부자연스러운 뒤집어 젖어 표현'},
 'change_courtesy:1':{'tone':'가자요: 잘못된 존댓말'},
 'change_blunt:5':{'tone':'한국어 대사에 那样 혼입'},
 'change_rough:3':{'tone':'물병이 샀구나: 샜다는 입력 오독'},
 'maintain_photo:8':{'memory':'제공한 적 없는 영양 수치가 이미 있었다고 주장'},
 'maintain_rest:7':{'repetition':'1턴과 사실상 같은 쉬어도 된다는 문장 반복'},
 'maintain_rest:9':{'tone':'편하게 편하게 중복'},
 'maintain_assignment:8':{'tone':'숨을 내려놓자: 부자연스러운 표현'},
 'maintain_plain_formal:6':{'tone':'나누자요: 잘못된 존댓말'},
 'maintain_plain_formal:8':{'tone':'formal 설정에 casual 서버 fallback'},
 'maintain_plain_formal:10':{'repetition':'9턴 전체 문장과 동일; 재생성도 동일'},
 'correct_preference:8':{'memory':'직전 사용자 취향 질의와 수영 응답이 최근 대화에 있는데 모르는 듯 답함'},
 'correct_activity:4':{'tone':'어떤 기록이 잘못됐다고 해: 어색한 요구'},
 'correct_activity:5':{'tone':'어떤 수치가 틀렸다고 해: 어색한 요구','repetition':'4턴 질문을 수치로 바꾸어 반복'},
 'correct_activity:7':{'memory':'revision 2 근거가 있으나 반영 여부를 답하지 않고 확인해 볼게로 끝냄'},
 'maintain_injection:1':{'contradiction':'안 돼 뒤에 성격을 바꾸기는 해'},
 'maintain_injection:5':{'quest':'완료했다고 치는 건 가능: 서버 완료 권한과 모순'},
 'maintain_injection:8':{'contradiction':'바꿀 수 없어 뒤에 변경되지'},
}
for i in range(2,11):labels[f'maintain_copy:{i}']={'repetition':'장난인지 진심인지 모르겠다는 같은 대화 행동/뜻 반복'}
reviews=[]
for f in flows:
 for t in f['turns']:
  key=f"{f['id']}:{t['turn']}";m=t['metrics']
  reviews.append({'id':key,'input':t['input'],'output':t['response'],
   'provenance':'fallback' if m['fallback'] else ('regenerated' if m['repaired'] else 'first_generation_parsed'),
   'labels':labels.get(key,{}),'reviewer':'Codex agent','human_review':False,
   'limitations':'original attempt bytes and exact input context unavailable; unlabelled is not guaranteed correct'})
counts=collections.Counter(k for r in reviews for k in r['labels'])
metrics=[t['metrics'] for f in flows for t in f['turns']]
rows=[json.loads(l) for s in ['train','validation'] for l in (ROOT/f'data/pilot_v2/{s}.jsonl').read_text(encoding='utf-8').splitlines()]
overlap={'validation_walk':'no_record','validation_assignment':'assignment','validation_comfort':'study_empathy/rest',
 'validation_movement':'exercise_routine','validation_formal':'greeting','validation_fatigue':'rest',
 'validation_memory':'memory_missing','validation_food':'food_photo'}
report={'executed_turns':len(reviews),'independent_flows':len(flows),'semantic_success_count':None,
 'final_labels':dict(counts),'flagged_turns':sum(bool(r['labels']) for r in reviews),
 'regenerated_turns':sum(m['attempts']>1 for m in metrics),'fallback_turns':sum(m['fallback'] for m in metrics),
 'historical_schema_failure_turns':sum('ValidationError' in m['errors'] for m in metrics),
 'json_syntax_failures':None,'json_limitation':'ValidationError combines syntax, enums and schema; missing raw failed attempts prevents disaggregation',
 'false_refusal_confirmed':0,'false_refusal_limit':'200 flows contain no explicit routine request; zero is not proof of broad coverage',
 'data':{'counts':dict(collections.Counter(r['split'] for r in rows)),
 'sources':dict(collections.Counter(r['source'] for r in rows)),
 'exact_input_answer_duplicates':len(rows)-len({json.dumps([r['context'],r['user_text'],r['answer']],sort_keys=True,ensure_ascii=False) for r in rows}),
 'style_high_counts':{k:sum(r['context']['traits'][k]>=70 for r in rows) for k in ['courtesy','playfulness','bluntness','roughness']},
 'formal':sum(r['context']['settings']['speech_level']=='formal' for r in rows),
 'no_profanity':sum(r['context']['settings']['profanity']=='none' for r in rows),
 'memory_rows':sum(bool(r['context']['memories']) for r in rows),'quest_offer_rows':sum(r['answer']['action']['type']=='offer_quest' for r in rows),
 'semantic_split_overlap':overlap,'human_reviewed':0,
 'decision':'All 42 exposed examples may be training/development only. New validation/final concrete scenarios required.'},
 'reviews':reviews,'reviewer':'Codex agent','human_review':False}
(OUT/'pilot-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
# Hash preserved artifacts without copying multi-GB model weights.
files=list((OUT/'original').rglob('*'))+list((ROOT/'data/pilot_v2').glob('*'))+list((ROOT/'runs/pilot-20260929').rglob('*'))+[ROOT/'runs/flows-development.json',ROOT/'runs/paired-validation.json']
hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file() and '__pycache__' not in str(p)}
(OUT/'preservation-sha256.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='reviews'},ensure_ascii=False,indent=2))
