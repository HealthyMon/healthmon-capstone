"""Turn continuation examples; recent assistant turns use the real server schema."""
import json,itertools,hashlib
from pathlib import Path
from collections import Counter
from prepare_qwen4b_common import make
from train_qwen4b import training_prompt
ROOT=Path(__file__).resolve().parents[1];DEST=ROOT/'data/dialogue_continuity_20261121'
# previous assistant, current user, grounded reply, energetic reply, warm tail,
# relevant NEW follow-up (never repeat an answered question), target, sentiment, motivation
TRAIN=[
('어떤 운동을 하고 싶어?','산책을 하고 싶어.','산책을 골랐구나. 편한 속도로 걸으면 되겠다.','좋아! 산책으로 정했네. 편하게 걸어보자.','부담 없이 즐겼으면 좋겠어.','집 근처와 공원 중 어디가 편해?','exercise','positive','high'),
('집 근처와 공원 중 어디가 편해?','공원으로 갈 거야.','공원으로 정했구나. 천천히 다녀와.','공원으로 정했네! 기분 좋게 다녀와.','네가 편안하게 걸었으면 좋겠어.','', 'exercise','neutral','neutral'),
('어떤 음악을 좋아해?','잔잔한 피아노 음악이 좋아.','잔잔한 피아노 음악을 좋아하는구나.','피아노의 잔잔한 분위기를 좋아하는구나!','취향을 들려줘서 고마워.','주로 어느 때 들어?','other','positive','neutral'),
('주로 어느 때 들어?','잠들기 전에 들어.','잠들기 전에 듣는 음악이구나.','잠들기 전 음악으로 듣는구나!','편안한 시간이 됐으면 좋겠어.','','other','neutral','neutral'),
('어떤 규칙이 재미있었어?','카드를 서로 바꾸는 규칙이 재미있었어.','카드를 주고받는 규칙이 재미있었구나.','카드를 바꾸면서 흐름이 달라지는 게 재미있었겠네!','즐겁게 놀았다니 나도 반가워.','친구들과 함께 했어?','other','positive','neutral'),
('어떤 책을 읽었어?','우주에 관한 과학책을 읽었어.','우주에 관한 과학책을 읽었구나.','우주 이야기라니 흥미롭겠다!','읽은 이야기를 나눠줘서 고마워.','어떤 내용이 가장 기억에 남아?','other','neutral','neutral'),
('어떤 내용이 가장 기억에 남아?','블랙홀 이야기가 기억에 남아.','블랙홀 이야기가 기억에 남았구나.','블랙홀 이야기가 특히 인상적이었네!','네가 흥미롭게 읽은 부분을 알게 돼서 좋아.','','other','neutral','neutral'),
('오늘은 어떤 운동을 하고 싶어?','운동 말고 영화 이야기하자.','알겠어. 영화 이야기로 바꾸자.','좋아, 영화 이야기로 넘어가자!','네가 하고 싶은 이야기를 들을게.','최근에 본 영화가 있어?','other','neutral','neutral'),
('네가 하자고 하니 반갑네. 어떤 운동을 할까?','그 말은 아까 했잖아. 반복하지 마.','맞아, 같은 말을 되풀이했네. 미안해. 이번에는 네가 말한 내용에 맞춰 답할게.','같은 말을 또 했네. 미안해. 네 이야기에 맞춰 답할게.','','','other','negative','neutral'),
('어떤 취미가 좋아?','방금 사진 찍는 게 좋다고 말했어.','사진 찍는 걸 좋아한다고 했지. 다시 물어서 미안해.','사진 찍는 게 좋다고 했는데 또 물었네. 미안해.','','풍경과 인물 중 어떤 사진을 자주 찍어?','other','neutral','neutral'),
('같이 뛰어 볼까?','뛰는 건 싫어. 다른 운동도 권하지 마.','알겠어. 운동을 더 권하지 않을게.','알겠어. 지금은 운동 이야기를 멈출게.','네 뜻을 존중할게.','','exercise','negative','low'),
('뭘 해보고 싶어?','그냥 쉬고 싶어. 질문도 하지 마.','알겠어. 질문하지 않을게. 편히 쉬어.','알겠어. 오늘은 편하게 쉬어.','재촉하지 않고 기다릴게.','','other','neutral','neutral'),
('책을 읽으면 좋겠다.','책 말고 그림을 그리고 싶어.','그림을 그리고 싶구나. 원하는 걸 해 보자.','좋아! 그림을 그리는 쪽으로 정했네.','네 선택을 존중할게.','무엇을 그리고 싶어?','other','positive','neutral'),
('무엇을 그리고 싶어?','우리 집 고양이를 그릴래.','집에서 키우는 고양이를 그릴 거구나.','고양이를 그리기로 했네!','즐겁게 그렸으면 좋겠어.','','other','positive','neutral'),
('어떤 곡을 연주하셨어요?','학교에서 배운 동요를 연주했어요.','학교에서 배운 동요를 연주하셨군요.','배운 동요를 직접 연주하셨네요!','이야기를 들려주셔서 고마워요.','연주하면서 어떤 부분이 가장 즐거우셨어요?','other','neutral','neutral'),
('어떤 취미를 시작하셨어요?','뜨개질이라고 아까 말씀드렸어요.','뜨개질이라고 말씀하셨는데 다시 여쭤봤네요. 죄송해요.','뜨개질이라고 이미 말씀하셨죠. 다시 여쭤봐서 죄송해요.','','어떤 것을 만들고 계세요?','other','neutral','neutral'),
('산책 목표는 아침 10분이야.','아니, 저녁 5분으로 바꿨어.','알겠어. 지금 말한 목표는 저녁 5분 산책이야.','알겠어! 아침 10분이 아니라 저녁 5분으로 바뀌었구나.','','','exercise','neutral','neutral'),
('힘내! 넌 할 수 있어!','응원 말고 내가 물어본 시간에 답해줘. 5분이면 돼?','응원만 해서 질문을 놓쳤네. 미안해. 가볍게 시작하는 거라면 5분부터 해보고 몸 상태에 맞춰 조절해.','질문을 놓쳤네. 미안해. 가볍게 시작한다면 5분부터 해보고 몸 상태에 맞춰 조절해.','','','exercise','neutral','neutral'),
('오늘도 즐겁게 시작해보자!','응, 오늘 스트레칭을 해볼게.','스트레칭을 해보기로 했구나. 무리 없는 범위에서 시작해.','좋아! 스트레칭으로 시작하기로 했네.','네가 편하게 이어갔으면 좋겠어.','','exercise','positive','high'),
('어떤 산책길이 좋아?','왜 계속 질문만 해? 그냥 대답해줘.','질문이 너무 많았네. 미안해. 네 말에 답하는 데 집중할게.','내가 질문만 이어갔네. 미안해. 이번에는 답변에 집중할게.','','','other','negative','neutral'),
]

def build(scenes,prefix):
 rows=[]
 for i,(previous,text,quiet,bright,warm,question,target,sentiment,motivation) in enumerate(scenes):
  for a,f,n in itertools.product((10,90),repeat=3):
   speech=' '.join(s for s in [bright if a==90 else quiet,warm if f==90 else '',question if n==90 else ''] if s)
   r=make(f'{prefix}-{i}-{a}-{f}-{n}',text,speech,axes=dict(activity=a,affinity=f,initiative=n),recent=[{'speech':previous,'source_id':f'{prefix}-previous-{i}'}],target=target,sentiment=sentiment,motivation=motivation)
   r['context']['settings']['speech_level']='formal' if text.endswith('요.') else 'casual'
   r.update(scenario_group=f'{prefix}:{i}',source='curated_turn_continuation')
   rows.append(r)
 return rows

def main():
 train=build(TRAIN,'continuity')
 # Expose repeated prior assistant turns explicitly; the target moves forward.
 for r in list(train):
  if r['context']['personality']['affinity']!=90:continue
  c=json.loads(json.dumps(r));c['sample_id']+='-loop-context'
  c['context']['recent']=[dict(c['context']['recent'][0],source_id=f'loop-{j}') for j in range(3)]
  train.append(c)
 replay=[json.loads(l) for l in (ROOT/'data/parameter_dialogue_20261121/train.jsonl').read_text(encoding='utf-8').splitlines()]
 for label in ['low','high','neutral']:
  train+=sorted([r for r in replay if r['answer']['classification']['motivation']==label],key=lambda r:hashlib.sha256(r['sample_id'].encode()).hexdigest())[:60]
 validation=build([
 ('어떤 음료가 좋아?','따뜻한 보리차를 좋아해.','따뜻한 보리차를 좋아하는구나.','따뜻한 보리차가 취향이구나!','취향을 알려줘서 고마워.','주로 언제 마셔?','food','positive','neutral'),
 ('무엇을 만들고 있어?','나무로 작은 의자를 만들고 있어.','나무로 작은 의자를 만들고 있구나.','작은 나무 의자를 만드는 중이구나!','만드는 시간이 즐거웠으면 좋겠어.','어느 부분까지 만들었어?','other','neutral','neutral')
 ],'continuity-val')
 seen=set();unique=[]
 for r in train:
  key=json.dumps(training_prompt(r)[0],ensure_ascii=False,sort_keys=True)
  if key not in seen:unique.append(r);seen.add(key)
 DEST.mkdir(exist_ok=False)
 for split,rows in [('train',unique),('validation',validation)]:
  (DEST/f'{split}.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
 manifest=dict(train=len(unique),validation=len(validation),new_continuation_examples=240,motivation=dict(Counter(r['answer']['classification']['motivation'] for r in unique)),evaluation='fresh multi-turn generated-answer rollout',human_review=False)
 (DEST/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(manifest))

if __name__=='__main__':main()
