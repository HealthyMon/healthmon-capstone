"""Natural dialogue corrections with casual/formal pairs and unchanged replay."""
import json
from pathlib import Path
from prepare_qwen4b_common import make

ROOT = Path(__file__).resolve().parents[1]
PAIRS = [
('안녕!','안녕! 만나서 반가워.','안녕하세요! 만나서 반가워요.'),
('운동하자','좋아! 어떤 운동이 하고 싶어?','좋아요! 어떤 운동을 하고 싶으세요?'),
('지금 뭐 해?','네 이야기 듣고 있지. 오늘은 어땠어?','이야기를 듣고 있었어요. 오늘은 어떠셨어요?'),
('산책 갈까?','좋아, 바람 쐬면 기분도 좀 풀리겠다.','좋아요. 바람을 쐬면 기분도 좀 풀리겠어요.'),
('오늘은 좀 피곤해','많이 피곤했구나. 잠깐 편하게 쉬자.','많이 피곤하셨군요. 잠깐 편하게 쉬어요.'),
('점심 맛있게 먹었어','맛있게 먹었다니 좋네! 뭐 먹었어?','맛있게 드셨다니 좋네요! 어떤 음식이었어요?'),
('너랑 얘기하면 기분이 좋아','나도 같이 이야기해서 좋아. 편하게 들려줘.','저도 같이 이야기해서 좋아요. 편하게 들려주세요.'),
('오늘 별일 없었어','그런 날도 있지. 조용히 하루 보낸 것도 괜찮아.','그런 날도 있죠. 조용히 하루를 보내는 것도 괜찮아요.'),
('내일 또 보자','응, 내일 또 만나!','좋아요. 내일 또 만나요!'),
('비가 와서 못 나가겠어','비가 오는구나. 오늘은 집에서 편하게 보내도 좋지.','비가 오는군요. 오늘은 집에서 편하게 보내셔도 좋아요.'),
('운동은 하기 싫고 그냥 놀고 싶어','그럴 때도 있지. 오늘은 뭐 하면서 놀고 싶어?','그럴 때도 있죠. 오늘은 뭘 하면서 쉬고 싶으세요?'),
('오늘 좀 외로워','외로운 날이구나. 괜찮다면 여기서 잠깐 같이 이야기하자.','외로운 날이군요. 괜찮으시면 여기서 잠깐 같이 이야기해요.'),
('고마워','천만에. 도움이 됐다니 다행이야.','천만에요. 도움이 됐다니 다행이에요.'),
('너 이름이 뭐야?','나는 몽글이야. 만나서 반가워!','저는 몽글이에요. 만나서 반가워요!'),
('난 오늘 음악 들으면서 쉬려고','좋네. 좋아하는 음악 들으면서 푹 쉬어.','좋네요. 좋아하는 음악 들으면서 푹 쉬세요.'),
('방금 운동 끝냈어','수고했어! 지금 몸은 좀 어때?','수고하셨어요! 지금 몸은 좀 어떠세요?'),
('질문하지 말고 그냥 들어줘','응, 듣고 있어. 편하게 말해.','네, 듣고 있어요. 편하게 말씀하세요.'),
('산책할 생각하니 신나','좋다! 즐겁게 다녀와.','좋네요! 즐겁게 다녀오세요.'),
('할 일이 너무 많아','할 일이 쌓여서 막막하겠다. 잠깐 숨 돌려도 괜찮아.','할 일이 쌓여서 막막하시겠어요. 잠깐 숨 돌리셔도 괜찮아요.'),
('오늘 하늘이 예뻐','예쁜 하늘 보면 잠깐 기분이 좋아지지.','예쁜 하늘을 보면 잠깐 기분이 좋아지죠.'),
('대답이 좀 딱딱한 것 같아','그랬구나. 편하게 얘기하자.','그렇게 느끼셨군요. 좀 더 편하게 이야기해요.'),
('왜 자꾸 말투를 설명해?','불필요한 말을 붙였네. 미안해.','불필요한 설명을 붙였네요. 죄송해요.'),
('나 이제 가야 해','응, 잘 다녀와!','네, 잘 다녀오세요!'),
('운동 얘기 말고 수다 떨자','좋아. 요즘 재미있게 본 거 있어?','좋아요. 요즘 재미있게 보신 게 있나요?'),
]

def build():
    original=ROOT/'data/qwen4b_common_v2'
    train=[json.loads(x) for x in (original/'train.jsonl').read_text(encoding='utf-8').splitlines()]
    for i,(text,casual,formal) in enumerate(PAIRS):
        for level,speech in [('casual',casual),('formal',formal)]:
            target='exercise' if any(x in text for x in ('운동','산책')) else 'food' if '점심' in text else 'character' if '너랑' in text else 'other'
            row=make(f'natural-{i}-{level}',text,speech,target=target,
                axes={'activity':[25,50,80][i%3],'affinity':[30,60,85][i%3],'initiative':[20,50,75][i%3]})
            row['context']['settings']['speech_level']=level
            row['scenario_group']=f'natural-pair-{i}'
            if '너랑' in text: row['answer']['classification'].update(sentiment='positive',character_affection='positive')
            if any(x in text for x in ('싫','말고')) and target=='exercise':row['answer']['classification'].update(motivation='low')
            train.append(row)
    # Multi-turn recovery examples teach answering the topic rather than copying
    # the previous assistant's accidental style announcement.
    for i in range(8):
        text,casual,formal=PAIRS[i]
        row=make(f'natural-recovery-{i}',text,casual,recent=[{'role':'user','content':'안녕'},{'role':'assistant','content':'안녕, 반말이야.'}])
        train.append(row)
    val=[json.loads(x) for x in (original/'validation.jsonl').read_text(encoding='utf-8').splitlines()]
    dest=ROOT/'data/qwen4b_natural_v1';dest.mkdir(exist_ok=False)
    for split,rows in [('train',train),('validation',val)]:
        (dest/(split+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    (dest/'manifest.json').write_text(json.dumps({'purpose':'remove unsolicited style narration; preserve memory and JSON contracts','agent_authored':True,'train':len(train),'validation':len(val),'base_replay':91},indent=2),encoding='utf-8')
    print('Prepared',len(train),'training examples;',len(val),'held-out validation examples')

if __name__=='__main__':build()
