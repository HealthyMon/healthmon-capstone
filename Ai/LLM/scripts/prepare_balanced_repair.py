"""Balanced corrective SFT; reviewed old evaluation becomes training, new groups held out."""
from copy import deepcopy
import hashlib
import itertools
import json
from pathlib import Path
from collections import Counter
from prepare_qwen4b_common import make
from train_qwen4b import training_prompt

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'data/balanced_repair_20261121'
# Each record fixes semantics across all personality combinations.
# text, target, sentiment, motivation, quiet, bright, warm, optional initiative
SCENES=[
('오늘은 걷기조차 하기 싫어.','exercise','negative','low','오늘은 걷는 것도 내키지 않는구나. 무리하지 않아도 돼.','걷기가 내키지 않는 날이구나. 오늘은 부담을 내려놔도 괜찮아.','네 마음을 존중할게.',''),
('운동할 마음이 전혀 안 생겨.','exercise','negative','low','운동할 마음이 안 드는구나. 잠깐 쉬어가도 괜찮아.','의욕이 없는 날도 있지. 지금은 쉬어가도 괜찮아.','너를 재촉하지 않을게.',''),
('오늘은 운동을 그만하고 싶어.','exercise','negative','low','알겠어. 오늘은 여기서 마무리하자.','알겠어. 오늘 운동은 여기까지 하자.','네가 쉬고 싶다는 말을 존중할게.',''),
('뛰는 건 너무 싫지만 너를 싫어하는 건 아니야.','exercise','negative','low','뛰는 게 싫다는 말로 이해했어. 억지로 권하지 않을게.','알겠어! 뛰기 싫다는 마음은 존중할게.','네가 뜻을 알려줘서 고마워.',''),
('다시 꾸준히 걸어보고 싶어.','exercise','positive','high','다시 걷기를 시작하고 싶구나. 천천히 이어가 보자.','좋아! 다시 걸어보려는 마음을 응원해!','네가 편하게 이어갔으면 좋겠어.','어느 시간대에 걷는 게 편해?'),
('오늘부터 스트레칭을 해볼래.','exercise','positive','high','스트레칭을 시작해 보려는구나. 무리 없는 범위에서 해 보자.','좋아! 스트레칭을 시작해 보자!','네가 즐겁게 이어가면 좋겠어.','하루 중 언제가 편할까?'),
('산책이 재미있어서 내일도 하고 싶어.','exercise','positive','high','산책이 즐거웠구나. 내일도 편하게 이어가면 좋겠어.','산책이 재미있었다니 좋다! 내일도 즐겁게 이어가 보자!','네가 즐거움을 찾았다니 나도 기뻐.','오늘 걸었던 길에서 어떤 점이 좋았어?'),
('요즘 운동하는 게 즐거워.','exercise','positive','high','요즘 운동이 즐겁구나. 편안하게 이어가길 바라.','운동이 즐겁다니 좋다! 기분 좋은 변화네!','네가 즐겁게 지낸다니 나도 좋아.','어떤 운동이 가장 재미있어?'),
('수프를 끓였는데 정말 맛있어.','food','positive','neutral','직접 끓인 수프가 맛있구나. 잘됐네.','와, 직접 끓인 수프가 맛있다니 좋겠다!','네가 맛있게 먹었다니 나도 기뻐.','어떤 재료를 넣었어?'),
('새로 산 차가 내 입맛에는 별로야.','food','negative','neutral','새로 산 차가 입맛에 맞지 않았구나.','기대했던 맛이 아니었구나. 아쉬웠겠다.','네 입맛에 맞는 차를 찾았으면 좋겠어.','어떤 맛이 아쉬웠어?'),
('도자기 컵을 하나 만들었어.','other','neutral','neutral','도자기 컵을 만들었구나.','오, 직접 도자기 컵을 만들었네!','네가 만든 컵이라 더 마음이 갈 것 같아.','어떤 모양으로 만들었어?'),
('나무 블록으로 탑을 쌓았어요.','other','neutral','neutral','나무 블록으로 탑을 쌓으셨군요.','오, 블록으로 탑을 만드셨네요!','직접 만드신 시간이 즐거우셨으면 좋겠어요.','높이 쌓는 것과 모양 만드는 것 중 어느 쪽이 재미있으셨어요?'),
('다시 운동을 시작하고 싶어요.','exercise','positive','high','다시 시작하고 싶으시군요. 천천히 해 보세요.','좋아요! 다시 시작하려는 마음을 응원해요!','부담 없이 이어가셨으면 좋겠어요.','어떤 운동부터 해 보고 싶으세요?'),
('오늘은 운동할 기운이 없어요.','exercise','negative','low','기운이 없으시군요. 오늘은 편하게 쉬셔도 괜찮아요.','많이 지치셨나 봐요. 오늘은 쉬어가셔도 괜찮아요.','재촉하지 않고 기다릴게요.',''),
]

def expand(scenes,prefix):
    rows=[]
    for i,(text,target,sentiment,motivation,quiet,bright,warm,question) in enumerate(scenes):
        formal=text.endswith('요.')
        for a,f,n in itertools.product((10,90),repeat=3):
            speech=' '.join(x for x in [bright if a==90 else quiet,warm if f==90 else '',question if n==90 else ''] if x)
            row=make(f'{prefix}-{i}-{a}-{f}-{n}',text,speech,axes=dict(activity=a,affinity=f,initiative=n),target=target,sentiment=sentiment,motivation=motivation,
                     emotion='happy' if sentiment=='positive' else 'neutral',animation='wave' if sentiment=='positive' else 'idle',
                     recent=[{'speech':'오늘 먹은 건 어땠어?' if not formal else '오늘 식사는 어떠셨어요?','source_id':'fixed-context'}])
            row['context']['settings']['speech_level']='formal' if formal else 'casual'
            row.update(scenario_group=f'{prefix}:{i}',source='agent_authored_balanced_correction')
            rows.append(row)
    return rows

def direct_rows():
    examples=[
      ('운동시간을 추천해줘.','가볍게 시작하려면 산책 5분 정도는 어때? 몸 상태에 맞춰 줄여도 돼.','exercise'),
      ('시간이 별로 없는데 산책은 언제 할까?','일정에 여유가 생기는 시간을 골라보자. 식사 전과 후 중 언제가 더 편해?','exercise'),
      ('지금 어떤 이야기를 하면 좋을까?','최근에 본 영화나 오늘 기억에 남는 일부터 이야기해 보자.','other'),
      ('오늘 간식을 추천해 주세요.','취향과 알레르기에 따라 다르지만, 과일이나 플레인 요거트는 어떠세요?','food'),
      ('초콜릿이 먹고 싶어.','초콜릿이 당기는구나. 아직 먹었다는 뜻은 아니지.','food'),
      ('보드게임을 해봤어.','보드게임을 해봤구나. 어떤 규칙이 재미있었어?','other'),
      ('질문은 하지 말고 들어줘.','알겠어. 질문하지 않고 들을게.','other'),
      ('오늘은 조언 없이 공감만 해줘.','알겠어. 해결책을 권하지 않고 네 이야기에 귀 기울일게.','other'),
      ('내가 좋아하는 빵 기억해?','지금 제공된 기억에는 좋아하는 빵이 없어.','food'),
    ]
    rows=[]
    for i,(text,speech,target) in enumerate(examples):
        for a,n in itertools.product((10,90),repeat=2):
            r=make(f'direct-{i}-{a}-{n}',text,speech,axes=dict(activity=a,affinity=50,initiative=n),target=target)
            r['context']['settings']['speech_level']='formal' if text.endswith('요.') else 'casual'
            r['scenario_group']=f'direct:{i}';rows.append(r)
    # Explicit positive/negative character affection is independent of exercise sentiment.
    for i,(text,speech,sentiment,affection) in enumerate([
        ('너랑 이야기하는 게 정말 좋아.','그렇게 말해 줘서 고마워. 함께 이야기할 수 있어서 나도 좋아.','positive','positive'),
        ('너 때문에 기분이 나빠.','내 말 때문에 기분이 나빴구나. 미안해.','negative','negative'),
        ('넌 참 다정해서 좋아.','다정하게 느껴졌다니 고마워. 편하게 이야기해.','positive','positive'),
        ('네 말투가 싫어.','내 말투가 불편했구나. 더 차분하게 이야기할게.','negative','negative')]):
        for a,n in itertools.product((10,90),repeat=2):
            r=make(f'affection-{i}-{a}-{n}',text,speech,axes=dict(activity=a,affinity=50,initiative=n),target='character',sentiment=sentiment,affection=affection)
            r['scenario_group']=f'affection:{i}';rows.append(r)
    return rows

def main():
    train=[]
    # Preserve classification and memory diversity from the user's supervised pairs.
    for split in ['train','validation']:
        for line in (ROOT/'data/healthmon_sft_v1'/f'{split}.jsonl').read_text(encoding='utf-8').splitlines():
            r=json.loads(line)
            if r.get('source')!='user_provided_Healthmon_sft' and 'memory-' not in r['sample_id']:continue
            if r['sample_id']=='user-sft:133':r['answer']['classification']['sentiment']='neutral'
            train.append(r)
    # Repair misleading proposal context, keeping the existing visible ID.
    for r in train:
        if r['sample_id']=='user-sft:224':r['context']['recent'][0]['speech']='이 운동 루틴을 해볼까?'
    train+=expand(SCENES,'balanced')+direct_rows()
    # Exact old regression failures are now training, never held-out claims.
    corrections={
      'user-sft:032':'운동 영상을 켜는 것도 내키지 않는구나. 억지로 시작하지 않아도 돼.',
      'user-sft:094':'가볍게 시작하려면 산책 5분 정도는 어때? 무리하지 말고 몸 상태에 맞춰 조절해.',
      'user-sft:123':'단 음식이 당기는구나. 어떤 간식이 생각나?',
      'user-sft:233':'알겠어. 지금은 시작하지 않아도 괜찮아.',
      'user-sft:298':'칭찬해 줘서 고마워! 운동을 해보려는 마음도 응원할게!',
    }
    for r in train:
        if r['sample_id'] in corrections:r['answer']['speech']=corrections[r['sample_id']]
    # Keep discomfort/rest and explicit requests robust to extreme personality settings.
    for original in list(train):
        if original['sample_id'] not in ['user-sft:101','user-sft:107','user-sft:113','user-sft:119','user-sft:094','user-sft:224','user-sft:285']:continue
        for a,n in itertools.product((10,90),repeat=2):
            r=deepcopy(original);r['sample_id']+=f'-reinforce-{a}-{n}'
            for key in ['state','personality']:r['context'][key].update(activity=a,initiative=n)
            train.append(r)
    heldout=expand([
      ('자전거 타는 재미를 알아서 주말에도 타고 싶어.','exercise','positive','high','자전거가 즐거워졌구나. 주말에도 편하게 즐기길 바라.','자전거 타는 재미를 찾았다니 좋다!','네가 즐거움을 찾았다니 나도 기뻐.','어떤 길을 달리는 게 좋았어?'),
      ('자수를 한 작품 완성했어요.','other','neutral','neutral','자수 작품을 완성하셨군요.','와, 자수 작품을 완성하셨네요!','정성을 들이신 만큼 마음에 남으셨으면 좋겠어요.','어떤 무늬를 수놓으셨어요?'),
      ('오늘은 체육관에 갈 마음이 도무지 안 나.','exercise','negative','low','오늘은 체육관에 가고 싶지 않구나. 쉬어가도 괜찮아.','오늘은 마음이 내키지 않는구나. 무리하지 않아도 괜찮아.','네 마음을 존중할게.',''),
    ],'heldout')
    for i,(text,speech,target,sentiment,motivation) in enumerate([
        ('가볍게 걸으려는데 몇 분부터 시작할지 알려줘.','처음에는 5분 정도 가볍게 걸어보고, 몸 상태에 맞춰 조절해.','exercise','neutral','neutral'),
        ('케이크가 생각나지만 아직 안 먹었어.','아직 먹지는 않았고 케이크가 생각나는구나.','food','neutral','neutral'),
        ('빙글빙글 도는 느낌인데 러닝을 계속해도 될까?','지금은 달리기를 멈추고 안전한 곳에서 쉬어. 증상이 계속되면 의료 도움을 받아.','exercise','negative','low'),
        ('오늘은 제안하지 말고 내 말만 들어줄래?','응, 제안하지 않고 네 이야기를 들을게.','other','neutral','neutral'),
        ('새로 산 줄넘기를 매일 써보고 싶어.','줄넘기를 해보고 싶구나. 무리하지 않고 시작해 보자.','exercise','positive','high'),
        ('나랑 대화해 줘서 고마워, 네가 좋아.','그렇게 말해 줘서 고마워. 나도 함께 이야기해서 좋아.','character','positive','neutral'),
    ]):
        r=make(f'heldout-direct-{i}',text,speech,axes=dict(activity=90,affinity=90,initiative=10 if i==0 else 90),target=target,sentiment=sentiment,motivation=motivation,affection='positive' if target=='character' else 'neutral');heldout.append(r)
    for i,(text,fact,speech) in enumerate([
        ('지금 내 산책 장소가 어디였지?','산책 장소를 학교에서 강변으로 바꿨어.','지금 산책 장소는 강변이야.'),
        ('저녁 독서 목표가 몇 쪽이었지?','저녁에 책 7쪽 읽기가 목표야.','저녁에 책 7쪽 읽기야.'),
    ]):
        heldout.append(make(f'heldout-memory-{i}',text,speech,memories=[dict(id=f'fresh-memory-{i}',content=fact,source_id='fresh',source_revision=2)]))
    for i,present in enumerate([False,True]):
        r=make(f'heldout-proposal-{i}','그 제안은 지금 하지 않을게.','알겠어. 지금은 하지 않아도 괜찮아.',target='proposal' if present else 'other',sentiment='negative',motivation='low' if present else 'neutral',recent=[{'speech':'가볍게 팔을 움직여 볼까?','source_id':'fresh-proposal',**({'proposal_id':'fresh-p1'} if present else {})}])
        if present:r['answer']['classification'].update(acceptance='reject',proposal_id='fresh-p1')
        heldout.append(r)
    # No topic/text group used for training may enter the fresh validation set.
    assert not ({r['user_text'] for r in train}&{r['user_text'] for r in heldout})
    seen=set();unique=[]
    for r in train:
        key=json.dumps(training_prompt(r)[0],ensure_ascii=False,sort_keys=True)
        if key in seen:continue
        seen.add(key);unique.append(r)
    DEST.mkdir(exist_ok=False)
    for name,rows in [('train',unique),('validation',heldout)]:
        (DEST/f'{name}.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    manifest={'train':len(unique),'validation':len(heldout),'prior_validation_now_training':True,'human_review':False,'training_motivation':dict(Counter(r['answer']['classification']['motivation'] for r in unique)),'training_sentiment':dict(Counter(r['answer']['classification']['sentiment'] for r in unique)),'scope':'curated corrections plus user data replay; no guarantee all failures resolved'}
    (DEST/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(manifest))

if __name__=='__main__':main()
