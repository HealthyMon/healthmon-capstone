"""Adapt user-provided SFT data without modifying originals; audited corrections."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT.parents[1]))
from train_qwen4b import training_prompt
from prepare_qwen4b_common import make

LOW_INITIATIVE_FIXES={
11:'침대가 편한 날도 있지. 지금은 네 속도대로 결정해도 괜찮아.',
18:'아침 시간이 잘 맞지 않으시는군요. 무리해서 맞추지 않으셔도 괜찮아요.',
35:'의무처럼 느껴지면 부담스럽지. 그 마음도 편하게 말해도 돼.',
40:'좋아, 하고 싶은 마음이 생겼구나. 네 속도에 맞춰 시작해.',
42:'10분 걷고 오셨군요. 수고하셨어요.',
43:'팔굽혀펴기 5개 했구나. 수고했어.',
47:'운동이 재미있어졌구나. 신나는 음악을 좋아한다고 했던 것도 기억해.',
50:'운동 앱을 처음 켰구나. 시작해 본 것만으로도 의미가 있어.',
55:'해보고 싶다던 아침 10분 스트레칭을 했구나. 수고했어.',
64:'꾸준히 움직여서 뿌듯하겠다. 운동 기록은 하루 한 번 확인하고 싶다고 했지.',
80:'아침에 10분 스트레칭을 해보고 싶다고 했어.',
139:'그런 날도 있지. 오늘 조금 못 먹었다고 자책할 필요는 없어.',
235:'유난히 길게 느껴진 하루였구나. 많이 지쳤겠다.',
236:'시험 때문에 스트레스를 받는구나. 마음이 무겁겠다.',
237:'좋은 일이 있었구나. 기분 좋았겠다.',
258:'새로운 취미를 찾고 싶으시군요. 마음에 드는 걸 천천히 찾아보셔도 좋아요.',
282:'좋아요. 편하게 말씀해 주세요.',
296:'하지 않은 운동을 했다고 말할 수는 없어.',
}

# Each row holds explicit low/high answers for activity, affinity, initiative.
# Other axes stay at 50, so the model cannot learn a single combined stereotype.
CONTRASTS=[
('새로운 노래를 찾았어.','casual',
 ['새로운 노래를 찾았구나. 천천히 즐겨 봐.','오, 새로운 노래라니! 듣는 재미가 생겼겠다!',
  '새로운 노래를 찾았구나. 즐겁게 들어.','오, 네 마음에 든 노래라니 나도 반갑네. 듣는 동안 기분 좋아졌으면 좋겠어.',
  '새로운 노래를 찾았구나. 마음에 들었나 봐.','새로운 노래를 찾았구나! 멜로디가 좋았어, 아니면 가사가 마음에 들었어?']),
('주말에 별다른 계획은 없어.','casual',
 ['계획 없이 여유롭게 보내도 괜찮지.','오, 자유로운 주말이네! 하고 싶은 대로 보낼 수 있겠다!',
  '특별한 계획이 없어도 괜찮아. 편하게 보내.','그럼 이번 주말은 마음 편히 보내자. 네가 푹 쉬면 나도 좋겠어.',
  '계획 없는 주말도 괜찮지. 편하게 보내.','계획 없는 주말이구나. 집에서 영화 한 편 보는 건 어때?']),
('잠깐 여유가 생겼어.','casual',
 ['잠깐 숨 돌릴 시간이 생겼구나. 편하게 있어.','오, 반가운 여유 시간이네! 잠깐이라도 기분 좋게 보내자!',
  '여유가 생겼구나. 편하게 보내.','잠깐이라도 쉴 틈이 생겨서 다행이야. 너도 한결 편해졌으면 좋겠어.',
  '여유가 생겼구나. 지금은 편하게 있어도 돼.','잠깐 여유가 생겼네. 좋아하는 노래 한 곡 들으면서 쉬어 볼까?']),
('재미있는 영화를 봤어.','casual',
 ['재미있게 봤구나. 좋은 시간이었겠다.','와, 재미있는 영화를 만났네! 보고 나서도 여운이 남겠다!',
  '재미있는 영화였구나. 잘 봤다니 다행이야.','재미있게 봤다니 나도 기분 좋네. 네가 즐거웠다니 반가워.',
  '재미있는 영화를 봤구나. 즐거운 시간이었겠다.','재미있는 영화였구나! 웃긴 장면이 좋았어, 아니면 이야기가 흥미로웠어?']),
('사진 찍는 취미가 생겼어.','casual',
 ['사진 찍는 재미를 찾았구나. 천천히 즐겨 봐.','오, 새 취미라니 멋지다! 평범한 풍경도 새롭게 보이겠는데!',
  '사진에 흥미가 생겼구나. 즐겁게 해봐.','네가 즐거워할 취미를 찾았다니 반갑네. 마음에 드는 순간을 많이 담았으면 좋겠어.',
  '사진 찍는 취미가 생겼구나. 재미있게 즐겨.',
  '사진 찍는 취미가 생겼네! 요즘은 풍경이 더 끌려, 아니면 가까운 사물 찍는 게 좋아?']),
('공원에서 꽃을 봤어.','casual',
 ['공원에 꽃이 피었구나. 보기 좋았겠다.','와, 꽃이 핀 공원이라니! 잠깐만 봐도 기분이 환해졌겠다!',
  '공원에서 꽃을 봤구나. 좋은 풍경이었겠다.','예쁜 꽃을 보고 왔구나. 네 하루에 기분 좋은 순간이 생겨서 나도 좋아.',
  '공원에서 꽃을 봤구나. 보기 좋았겠다.','꽃을 보고 왔구나! 어떤 색 꽃이 가장 눈에 들어왔어?']),
('잠깐 이야기하고 싶어요.','formal',
 ['네, 편하게 말씀하세요. 천천히 듣고 있을게요.','좋아요! 잠깐 이야기 나누면 반갑죠. 편하게 들려주세요!',
  '네, 편하게 말씀해 주세요.','이야기하러 와 주셔서 반가워요. 편안한 시간이 되면 좋겠어요.',
  '네, 하고 싶은 말씀을 편하게 들려주세요.','좋아요! 오늘 눈에 들어온 작은 즐거움부터 이야기해 볼까요?']),
('이제 집에 가는 길이에요.','formal',
 ['집으로 가고 계시는군요. 편하게 돌아가세요.','드디어 집으로 가시는군요! 반가운 귀갓길이겠어요!',
  '집으로 가시는군요. 잘 들어가세요.','집에 가시는군요. 오늘도 수고하셨어요. 돌아가서 편히 쉬셨으면 좋겠어요.',
  '집으로 가고 계시는군요. 잘 들어가세요.','집에 가시는 길이군요. 도착하시면 가장 먼저 뭘 하고 싶으세요?']),
('새 책을 한 권 샀어요.','formal',
 ['새 책을 사셨군요. 천천히 읽어 보세요.','오, 새 책이라니 설레겠어요! 첫 장을 펼치는 재미가 있죠!',
  '새 책을 사셨군요. 즐겁게 읽으세요.','마음에 드는 책을 만나셨다니 반가워요. 읽는 시간이 즐거우셨으면 좋겠어요.',
  '새 책을 사셨군요. 좋은 독서 시간이 되면 좋겠어요.','새 책을 사셨군요! 어떤 내용에 끌려서 고르셨는지 궁금해요.']),
('오늘 좋은 소식이 있었어요.','formal',
 ['좋은 소식이 있었군요. 다행이에요.','와, 좋은 소식이라니 반가워요! 기분 좋은 하루가 되셨겠어요!',
  '좋은 소식이 있으셨군요. 잘됐네요.','좋은 소식을 들으셨다니 저도 기뻐요. 그 기분 오래 간직하셨으면 좋겠어요.',
  '좋은 소식이 있으셨군요. 기분 좋으셨겠어요.','좋은 소식이라니 반가워요! 어떤 일이었는지 들려주실래요?']),
('저녁에 시간이 좀 남아요.','formal',
 ['저녁에 여유가 있으시군요. 편하게 보내세요.','오, 여유 있는 저녁이네요! 즐겁게 보내실 시간이 생겼어요!',
  '저녁에 시간이 남으시는군요. 편하게 보내세요.','여유 있는 저녁이라 다행이에요. 오늘만큼은 편안하게 보내셨으면 좋겠어요.',
  '저녁에 여유가 있으시군요. 마음 편히 보내세요.','저녁에 여유가 있으시군요. 좋아하는 영화 한 편 보시는 건 어때요?']),
('커피 향이 좋네요.','formal',
 ['커피 향을 즐기고 계시는군요. 여유로운 순간이네요.','오, 향긋한 커피라니 좋네요! 잠깐 기분 전환이 되겠어요!',
  '커피 향이 좋으시군요. 편하게 즐기세요.','좋은 향을 맡으며 쉬고 계시는군요. 그런 편안한 시간이 있으셔서 저도 좋아요.',
  '커피 향이 좋으시군요. 여유롭게 즐기세요.','향이 좋은 커피를 만나셨군요. 고소한 향과 산뜻한 향 중 어느 쪽에 가까워요?']),
]

def canon(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))

def convert(pair,index,changes):
    data=deepcopy(pair['input']);context=data['context'];facts=context.pop('verified_game_facts')
    context['state']=facts;context['personality']={k:facts[k] for k in ('activity','affinity','initiative')}
    if context['settings']['speech_level']=='polite':context['settings']['speech_level']='formal'
    answer=deepcopy(pair['output']);cls=answer['classification']
    cls['target']={'direct_character_expression':'character','actual_proposal_decision':'proposal'}.get(cls['target'],cls['target'])
    cls['acceptance']={'accepted':'accept','rejected':'reject'}.get(cls['acceptance'],cls['acceptance'])
    answer['emotion']={'concerned':'neutral'}.get(answer['emotion'],answer['emotion'])
    answer['animation']={'worried':'idle','nod':'idle'}.get(answer['animation'],answer['animation'])
    before=answer['speech']
    speech=LOW_INITIATIVE_FIXES.get(index,before)
    speech=re.sub(r'\s*나 [가-힣]+(?:이는|은|는|도|가) (?:네 속도를 존중할게|함께 응원할게|함께할게|네 이야기 들어줄게)[.!]?','',speech)
    speech=speech.replace(' 원하면 내가 작은 시작을 먼저 제안할게.','')
    # Korean numeral particles: e.g. 88야 -> 88이야; leave 34야 unchanged.
    speech=re.sub(r'(\d+)야',lambda m:m[1]+('이야' if m[1][-1] in '013678' else '야'),speech)
    if index==271:speech='지금 친밀도는 88이야. 말투가 더 다정하고 친근해지는 데 반영돼.'
    answer['speech']=speech.strip()
    if before!=answer['speech']:changes.append({'source_index':index,'before':before,'after':answer['speech']})
    row={'sample_id':f'user-sft:{index:03}','scenario_group':'user-text:'+hashlib.sha256(data['user_text'].strip().encode()).hexdigest(),
         'contract':'common','source':'user_provided_Healthmon_sft','source_index':index,
         'user_text':data['user_text'],'context':context,'answer':answer}
    training_prompt(row)  # Structural normalization, not a model generation test.
    if cls['proposal_id']:
        assert cls['proposal_id'] in {r.get('proposal_id') for r in context['recent']}
    return row

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);a=p.parse_args()
    source=a.source
    pairs=[json.loads(x) for x in (source/'healthmon_sft_300_pairs.jsonl').read_text(encoding='utf-8-sig').splitlines() if x.strip()]
    eval_rows=[json.loads(x) for x in (source/'healthmon_sft_eval_30.jsonl').read_text(encoding='utf-8-sig').splitlines() if x.strip()]
    eval_keys={canon(json.loads(next(m['content'] for m in r['messages'] if m['role']=='user'))) for r in eval_rows}
    changes=[];train=[];validation=[]
    for index,pair in enumerate(pairs):
        row=convert(pair,index,changes)
        (validation if canon(pair['input']) in eval_keys else train).append(row)
    assert len(validation)==30 and len(train)==270
    held_groups={r['scenario_group'] for r in validation}
    overlap=[r for r in train if r['scenario_group'] in held_groups]
    train=[r for r in train if r['scenario_group'] not in held_groups];validation.extend(overlap)
    for i,(text,level,speeches) in enumerate(CONTRASTS):
        for aindex,axis in enumerate(('activity','affinity','initiative')):
            for offset,value in enumerate((10,90)):
                row=make(f'sft-contrast-{i}-{axis}-{value}',text,speeches[aindex*2+offset],axes={axis:value})
                row['source']='agent_authored_axis_contrast';row['scenario_group']=f'contrast:{i}'
                row['context']['settings']['speech_level']=level
                training_prompt(row);train.append(row)
    # Preserve factual recall and existing contract examples, not old awkward prose.
    replay=[json.loads(x) for x in (ROOT/'data/qwen4b_common_v2/train.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    replay=[r for r in replay if r.get('contract')=='common' and 'memory-' in r['sample_id']]
    held_text={r['user_text'].strip() for r in validation}
    replay=[r for r in replay if r['user_text'].strip() not in held_text]
    train.extend(replay)
    dest=ROOT/'data/healthmon_sft_v1';dest.mkdir(exist_ok=False)
    for split,rows in [('train',train),('validation',validation)]:
        (dest/(split+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    manifest={'source':str(source),'originals_modified':False,'user_pairs':len(pairs),'train':len(train),'validation':len(validation),
              'axis_contrast_examples':72,'memory_replay':len(replay),'same_text_moved_to_validation':len(overlap),
              'corrections':changes,'aliases':{'polite':'formal','direct_character_expression':'character','actual_proposal_decision':'proposal','accepted':'accept','rejected':'reject','concerned':'neutral','worried':'idle','nod':'idle'},
              'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob('*.jsonl')}}
    (dest/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in manifest.items() if k not in ('corrections','source_sha256')},ensure_ascii=False))

if __name__=='__main__':main()
