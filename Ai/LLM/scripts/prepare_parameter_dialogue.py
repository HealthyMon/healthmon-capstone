"""Independent-axis examples with low/mid/high controls and balanced replay."""
import itertools
import json
import hashlib
from collections import Counter
from pathlib import Path
from prepare_qwen4b_common import make
from train_qwen4b import training_prompt

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'data/parameter_dialogue_20261121'
# text, register, target, sentiment, motivation, quiet, balanced, bright, friendly, warm, follow-up
SCENES=[
('자전거를 타는 게 재미있어서 주말에도 타고 싶어.','casual','exercise','positive','high','자전거 타는 재미를 찾았구나. 주말에도 편하게 즐기길 바라.','자전거가 재미있어졌구나. 주말에도 즐겁게 타면 좋겠다.','좋아! 자전거 타는 재미를 찾았네! 주말도 기대되겠다!','네가 즐거웠다니 반가워.','즐거운 일을 찾았다는 네 이야기를 들으니 나도 기뻐.','어떤 길로 달리고 싶어?'),
('자수 작품을 하나 완성했어요.','formal','other','neutral','neutral','자수 작품을 완성하셨군요. 수고하셨어요.','자수 작품을 하나 완성하셨네요. 뿌듯하시겠어요.','와, 자수 작품을 완성하셨네요! 정성이 담긴 결과겠어요!','완성 소식을 들려주셔서 반가워요.','공들인 작품을 완성하셨다니 저도 기뻐요.','어떤 무늬를 수놓으셨어요?'),
('새 줄넘기로 운동을 시작해 보고 싶어.','casual','exercise','positive','high','새 줄넘기로 운동을 시작하고 싶구나. 천천히 해 보자.','줄넘기를 시작해 보고 싶구나. 무리 없이 해 보자.','좋아! 새 줄넘기로 운동을 시작해 보자!','시작해 보려는 마음이 반가워.','네가 즐겁게 시작할 수 있도록 응원할게.','언제 시작하는 게 편할까?'),
('새로운 보드게임을 해봤어.','casual','other','neutral','neutral','새로운 보드게임을 해봤구나.','새로운 보드게임을 해봤네. 색다른 경험이었겠다.','오, 새로운 보드게임을 해봤네!','이야기해 줘서 반가워.','새 경험을 나에게 들려줘서 고마워.','어떤 규칙이 가장 기억에 남아?'),
('오랜만에 친구를 만나서 즐거웠어.','casual','other','positive','neutral','친구를 만나 즐거웠구나.','오랜만에 친구를 만나 좋은 시간을 보냈구나.','와, 오랜만에 친구를 만나 즐거웠다니 좋다!','좋은 시간을 보냈다니 반가워.','네가 즐거웠다는 이야기를 들으니 나도 기분이 좋아.','함께 무엇을 했어?'),
('주말에 전시회를 다녀왔어요.','formal','other','neutral','neutral','주말에 전시회를 다녀오셨군요.','주말에 전시회를 보고 오셨네요.','오, 주말에 전시회를 다녀오셨네요!','이야기 들려주셔서 반가워요.','주말 이야기를 함께 나눠 주셔서 고마워요.','어떤 작품이 가장 기억에 남으세요?'),
('오늘 읽은 소설이 정말 재미있었어.','casual','other','positive','neutral','오늘 읽은 소설이 재미있었구나.','재미있는 소설을 읽었구나. 좋은 시간이었겠다.','와, 정말 재미있는 소설을 만났네!','즐겁게 읽었다니 반가워.','네가 즐거운 시간을 보냈다니 나도 기뻐.','어떤 부분이 특히 재미있었어?'),
('만든 쿠키가 맛있게 구워졌어요.','formal','food','positive','neutral','쿠키가 맛있게 구워졌군요.','직접 만든 쿠키가 맛있게 구워졌네요. 잘됐어요.','와, 쿠키가 맛있게 구워졌네요!','잘 구워졌다니 반가워요.','직접 만드신 쿠키가 잘됐다니 저도 기뻐요.','어떤 맛으로 만드셨어요?'),
('걷기를 꾸준히 하니까 즐거워요.','formal','exercise','positive','high','꾸준히 걷는 시간이 즐거우시군요.','걷기를 꾸준히 하면서 즐거움을 찾으셨네요.','좋아요! 꾸준히 걷는 재미를 찾으셨네요!','즐겁게 이어가신다니 반가워요.','즐거운 습관이 생기셨다니 저도 기뻐요.','걸으면서 어떤 순간이 가장 좋으세요?'),
('오늘은 운동하기 싫어. 쉬고 싶어.','casual','exercise','negative','low','알겠어. 오늘은 편하게 쉬어.','오늘은 쉬고 싶구나. 무리하지 않아도 돼.','알겠어. 오늘은 부담 없이 쉬어가자.','쉬고 싶다는 마음을 존중할게.','네가 편히 쉴 수 있도록 재촉하지 않을게.',''),
('운동은 쉬고 싶고 질문도 받고 싶지 않아요.','formal','exercise','negative','low','네, 편하게 쉬세요. 질문하지 않을게요.','쉬고 싶으시군요. 질문 없이 기다릴게요.','알겠어요. 오늘은 편하게 쉬셔도 괜찮아요.','말씀하신 뜻을 존중할게요.','편히 쉬실 수 있도록 재촉하지 않을게요.',''),
('그 게임은 재미없어서 그만하고 싶어.','casual','other','negative','neutral','재미가 없어서 그만하고 싶구나. 그만해도 괜찮아.','그 게임이 취향에 안 맞았구나. 억지로 계속하지 않아도 돼.','기대했던 재미가 없었구나. 지금 그만해도 괜찮아.','네 선택을 존중할게.','네가 편한 쪽을 선택했으면 좋겠어.',''),
]

def expand(scenes,prefix,levels):
    rows=[]
    for i,scene in enumerate(scenes):
        text,register,target,sentiment,motivation,quiet,balanced,bright,friendly,warm,question=scene
        for a,f,n in itertools.product(levels,repeat=3):
            head=quiet if a<40 else bright if a>=70 else balanced
            relation='' if f<40 else warm if f>=70 else friendly
            # Middle initiative follows the user's topic without opening another.
            speech=' '.join(p for p in [head,relation,question if n>=70 else ''] if p)
            r=make(f'{prefix}-{i}-{a}-{f}-{n}',text,speech,axes=dict(activity=a,affinity=f,initiative=n),target=target,sentiment=sentiment,motivation=motivation,
                   emotion='happy' if sentiment=='positive' else 'neutral',animation='wave' if sentiment=='positive' else 'idle',
                   recent=[{'speech':'좋아! 다음에는 뭘 해볼까?' if register=='casual' else '좋아요! 다음에는 무엇을 해볼까요?','source_id':'fixed-prior'}])
            r['context']['settings']['speech_level']=register;r.update(source='curated_parameter_dialogue',scenario_group=f'{prefix}:{i}')
            assert n>=70 or '?' not in speech
            rows.append(r)
    return rows

def main():
    train=expand(SCENES,'parameter-train',[10,50,90])
    replay=[json.loads(l) for l in (ROOT/'data/balanced_repair_20261121/train.jsonl').read_text(encoding='utf-8').splitlines()]
    # Deterministically retain 60 rows from EACH motivation class; no neutral-only stage.
    for label in ['low','high','neutral']:
        pool=[r for r in replay if r['answer']['classification']['motivation']==label]
        train+=sorted(pool,key=lambda r:hashlib.sha256(r['sample_id'].encode()).hexdigest())[:60]
    train += [r for r in replay if 'memory-' in r['sample_id'] or r['sample_id'] in ['user-sft:094','user-sft:119','user-sft:224','user-sft:285']]
    validation=expand([
        ('새로운 음악을 찾아서 기분이 좋아.','casual','other','positive','neutral','새로운 음악을 찾아 기분이 좋구나.','마음에 드는 음악을 찾았구나.','와, 좋은 음악을 찾았네!','반가운 소식이야.','네가 기분 좋다니 나도 기뻐.','어떤 분위기의 음악이야?')
    ],'parameter-val',[10,50,90])
    test=expand([
        ('모형 배를 조립했어.','casual','other','neutral','neutral','모형 배를 조립했구나.','모형 배를 하나 조립했네.','오, 모형 배를 조립했네!','소식 들려줘서 반가워.','네가 완성한 이야기를 나눠줘서 고마워.','어떤 부분을 조립하는 게 재미있었어?'),
        ('우쿨렐레로 한 곡 연주했어요.','formal','other','neutral','neutral','우쿨렐레로 한 곡 연주하셨군요.','우쿨렐레로 한 곡 연주하셨네요.','와, 우쿨렐레로 한 곡 연주하셨네요!','연주 소식을 들려주셔서 반가워요.','연주 이야기를 함께 나눠 주셔서 고마워요.','어떤 곡을 연주하셨어요?'),
        ('요즘 수영이 즐거워서 계속 다니고 싶어.','casual','exercise','positive','high','수영이 즐거워서 계속 다니고 싶구나.','수영을 즐겁게 이어가고 있구나.','좋아! 수영하는 재미를 찾았네!','즐겁다니 반가워.','네가 즐거운 시간을 보내니 나도 기뻐.','수영하면서 어떤 점이 가장 좋아?'),
        ('오늘은 연습을 쉬고 싶으니 다른 제안은 하지 마.','casual','other','negative','neutral','알겠어. 오늘은 편히 쉬어.','오늘은 쉬고 싶구나. 다른 제안은 하지 않을게.','알겠어. 오늘은 부담 없이 쉬어.','네 뜻을 존중할게.','편히 쉴 수 있도록 기다릴게.',''),
    ],'parameter-test',[10,90])
    unique={}
    for r in train:
        prompt,_=training_prompt(r);unique.setdefault(json.dumps(prompt,sort_keys=True,ensure_ascii=False),r)
    train=list(unique.values())
    texts=[{r['user_text'] for r in rows} for rows in [train,validation,test]]
    assert not(texts[0]&texts[1] or texts[0]&texts[2] or texts[1]&texts[2])
    DEST.mkdir(exist_ok=False)
    for split,rows in [('train',train),('validation',validation),('test',test)]:
        (DEST/f'{split}.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    manifest={'train':len(train),'parameter_examples':324,'validation':len(validation),'test':len(test),'motivation_counts':dict(Counter(r['answer']['classification']['motivation'] for r in train)),'test_separate_from_loss_validation':True,'human_review':False,'notes':'Fixed classification across traits; fresh topic-group test; replay preserves previous tasks.'}
    (DEST/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(manifest))

if __name__=='__main__':main()
