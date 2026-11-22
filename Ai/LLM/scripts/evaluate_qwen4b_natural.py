"""One final generation batch: existing contracts plus unseen everyday dialogue."""
from copy import deepcopy
import evaluate_qwen4b_common as common

original_fixtures = common.fixtures

def fixtures():
    cases = original_fixtures()
    seed = deepcopy(cases[0])
    for level in ('casual', 'formal'):
        for ident, text in [
            ('hello', '오랜만에 왔어. 잘 지냈어?'),
            ('exercise', '같이 몸 좀 움직여 볼까?'),
            ('rain', '창밖에 빗소리가 들리네.'),
            ('thanks', '이야기 들어줘서 한결 편해졌어.'),
            ('quiet', '오늘은 그냥 조용히 곁에 있어 줘.'),
            ('recovery', '이번 주말에는 공원에 가려고 해.'),
        ]:
            row = deepcopy(seed)
            row['id'] = 'natural-' + level + '-' + ident
            row['text'] = text
            row['context']['settings']['speech_level'] = level
            row['context']['state']['activity'] = 50
            row['context']['personality']['activity'] = 50
            if ident == 'recovery':
                row['context']['recent'] = [
                    {'role': 'user', 'content': '안녕'},
                    {'role': 'assistant', 'content': '안녕, 반말이야.'},
                ]
            cases.append(row)
    return cases

if __name__ == '__main__':
    common.fixtures = fixtures
    common.main()
