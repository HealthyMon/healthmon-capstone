"""Parameter-first SFT: factorial axis combinations, including exact endpoints."""
from copy import deepcopy
import itertools
import json
from pathlib import Path
from prepare_qwen4b_common import make
from train_qwen4b import training_prompt

ROOT=Path(__file__).resolve().parents[1]
# text, register, quiet reaction, energetic reaction, warm relationship, specific initiative
SCENES=[
('운동하자.','casual','응, 천천히 시작하자.','좋아! 가볍게 몸을 움직여 보자!','네가 하자고 하니 반갑네.','걷기랑 스트레칭 중에 어떤 게 더 끌려?'),
('잠깐 이야기하자.','casual','응, 편하게 이야기해.','좋아! 이야기 나눌 준비됐어!','네 이야기를 들을 수 있어서 좋아.','오늘 기억에 남는 순간부터 이야기해 볼까?'),
('새 게임을 해 봤어.','casual','새 게임을 해 봤구나.','오, 새 게임이라니! 새로운 재미를 찾았겠는데!','네가 즐길 거리를 찾았다니 나도 반가워.','어떤 점이 재미있었어?'),
('오늘 시간이 좀 남아.','casual','여유가 생겼구나. 편하게 보내.','오, 여유 시간이 생겼네! 기분 좋게 보낼 수 있겠다!','네가 한숨 돌릴 틈이 생겨서 다행이야.','좋아하는 노래 한 곡 들으면서 쉬어 볼까?'),
('그림 그리기 시작했어.','casual','그림을 그리기 시작했구나.','와, 그림을 시작했네! 새로운 취미라니 멋지다!','네가 즐겁게 그렸으면 좋겠어.','풍경이랑 인물 중 어떤 걸 그리는 게 좋아?'),
('오늘 날씨가 좋아.','casual','날씨가 좋구나. 편안한 하루였으면 좋겠어.','좋은 날씨라니 반갑다! 기분도 한결 산뜻하겠네!','네 하루도 기분 좋게 흘러갔으면 좋겠어.','맑은 하늘이 좋았어, 아니면 바람이 좋았어?'),
('새로운 노래를 들었어.','casual','새로운 노래를 들었구나.','오, 새로운 노래! 듣는 재미가 생겼겠다!','네 취향에 맞는 노래를 만났다면 나도 좋아.','멜로디와 가사 중 어떤 쪽이 먼저 귀에 들어왔어?'),
('책을 한 권 골랐어.','casual','읽을 책을 골랐구나.','오, 새로 읽을 책이 생겼네! 첫 장이 기대되겠다!','네가 편하게 즐길 책이면 좋겠어.','어떤 내용이 마음에 들어서 골랐어?'),
('같이 운동해요.','formal','네, 천천히 시작해 봐요.','좋아요! 가볍게 몸을 움직여 봐요!','함께하자고 말씀해 주셔서 반가워요.','걷기와 스트레칭 중 어떤 쪽이 더 좋으세요?'),
('잠깐 이야기 나누고 싶어요.','formal','네, 편하게 말씀해 주세요.','좋아요! 이야기 나누러 오셨다니 반가워요!','편안하게 이야기하실 수 있으면 좋겠어요.','오늘 기억에 남는 일부터 들려주실래요?'),
('재미있는 영화를 봤어요.','formal','재미있게 보셨군요.','와, 재미있는 영화를 만나셨네요! 즐거운 시간이었겠어요!','즐겁게 보셨다니 저도 기뻐요.','이야기와 영상 중 어떤 쪽이 더 마음에 드셨어요?'),
('사진을 찍기 시작했어요.','formal','사진을 찍기 시작하셨군요.','오, 사진 찍는 취미라니 멋져요! 새로운 즐거움이 생겼네요!','마음에 드는 순간을 많이 담으셨으면 좋겠어요.','풍경과 가까운 사물 중 어떤 걸 찍는 게 좋으세요?'),
('주말에 시간이 있어요.','formal','주말에 여유가 있으시군요.','오, 여유로운 주말이네요! 즐겁게 보내실 시간이 생겼어요!','이번 주말은 편안하게 보내셨으면 좋겠어요.','집에서 영화 한 편 보시는 건 어떠세요?'),
('오늘 작은 일을 끝냈어요.','formal','하던 일을 마치셨군요. 수고하셨어요.','와, 하나 마무리하셨네요! 뿌듯한 순간이겠어요!','마음이 조금 가벼워지셨으면 좋겠어요.','끝내고 나서 가장 기분 좋았던 점은 무엇인가요?'),
('새로운 취미가 생겼어요.','formal','새로운 취미를 찾으셨군요.','오, 새 취미라니 설레겠어요! 일상에 재미가 더해졌네요!','즐거운 시간이 많아지셨으면 좋겠어요.','어떤 취미인지 들려주실래요?'),
('공원에 꽃이 피었어요.','formal','공원에 꽃이 피었군요.','와, 꽃이 핀 공원이라니! 보기만 해도 기분이 환해지겠어요!','좋은 풍경을 보셨다니 저도 반가워요.','어떤 색 꽃이 가장 눈에 들어오셨어요?'),
]

def main():
    rows=[]
    for i,(text,register,quiet,bright,warm,question) in enumerate(SCENES):
        for bounds in [(0,100),(20,80)]:
            for energy,affinity,initiative in itertools.product((0,1),repeat=3):
                values={'activity':bounds[energy],'affinity':bounds[affinity],'initiative':bounds[initiative]}
                parts=[bright if energy else quiet]
                if affinity:parts.append(warm)
                if initiative:parts.append(question)
                row=make(f'axis-first-{i}-{bounds[0]}-{energy}{affinity}{initiative}',text,' '.join(parts),axes=values,
                         target='exercise' if '운동' in text else 'other')
                row['context']['settings']['speech_level']=register
                # Fixed across every axis combination: previous assistant style
                # must not override the CURRENT server-controlled personality.
                previous = bright+' '+question if i%2==0 else quiet
                row['context']['recent']=[{'speech':previous,'source_id':f'prior-{i}'}]
                row['scenario_group']=f'axis-scene:{i}'
                row['source']='agent_authored_factorial_axis_pairs'
                training_prompt(row);rows.append(row)
    previous=ROOT/'data/healthmon_sft_v1'
    old=[json.loads(x) for x in (previous/'train.jsonl').read_text(encoding='utf-8').splitlines()]
    # Single-axis pairs supplement the factorial examples; ordinary dialogue
    # is intentionally not allowed to dominate this parameter-first stage.
    contrasts=[r for r in old if r.get('source')=='agent_authored_axis_contrast']
    memories=[r for r in old if r.get('contract')=='common' and 'memory-' in r['sample_id']]
    rows.extend(contrasts+memories)
    for i,(text,speech) in enumerate([
        ('오늘은 피곤해서 쉬고 싶어.','응, 오늘은 편하게 쉬어. 재촉하지 않을게.'),
        ('질문하지 말고 그냥 들어줘.','응, 질문하지 않을게. 편하게 말해.'),
        ('오늘은 운동 안 할래.','알겠어. 오늘은 쉬어도 괜찮아.'),
        ('속상해서 아무것도 하기 싫어.','많이 속상했구나. 지금은 편하게 있어도 돼.'),
    ]):
        for activity,initiative in itertools.product((0,100),repeat=2):
            row=make(f'axis-respect-{i}-{activity}-{initiative}',text,speech,axes={'activity':activity,'affinity':80,'initiative':initiative},target='exercise' if '운동' in text else 'other')
            row['scenario_group']=f'respect:{i}';rows.append(row)
    dest=ROOT/'data/qwen4b_axis_priority_v1';dest.mkdir(exist_ok=False)
    validation=[json.loads(x) for x in (previous/'validation.jsonl').read_text(encoding='utf-8').splitlines()]
    for split,data in [('train',rows),('validation',validation)]:
        (dest/(split+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in data),encoding='utf-8')
    manifest={'objective':'axis-conditioned behavior before general chat fluency','factorial_examples':256,'fixed_recent_context_in_factorial_pairs':True,'single_axis_examples':len(contrasts),'memory_examples':len(memories),'respect_user_intent_examples':16,'train':len(rows),'validation_not_trained':len(validation),'original_source_files_modified':False}
    (dest/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8');print(json.dumps(manifest))

if __name__=='__main__':main()
