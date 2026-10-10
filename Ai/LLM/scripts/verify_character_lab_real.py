"""Finite actual offline Qwen checks. No retraining or bulk dataset generation."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.character_lab_schema import ConversationLabel
from src.persona_runtime import DEFAULT_GENERATION


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8001)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise ValueError('Choose a new verification output path')
    origin=f'http://127.0.0.1:{args.port}'
    client=httpx.Client(base_url=origin,trust_env=False,timeout=300,
                       headers={'Origin':origin,'X-Persona-Lab':'1'})
    cases=[('운동하기 존나 싫다',{'target':'exercise','motivation':'low','character_affection':'neutral','acceptance':'none'}),
           ('너 자꾸 말 걸지 마. 귀찮아.',{'target':'character','character_affection':'negative','acceptance':'reject'}),
           ('네가 응원해 줘서 좋아. 고마워!',{'target':'character','character_affection':'positive','acceptance':'none'}),
           ('치킨 존나 맛있다',{'target':'food','character_affection':'neutral'}),
           ('매일 운동해야겠어',{'target':'exercise','character_affection':'neutral'}),
           ('그 퀘스트는 오늘 안 할래',{'target':'quest','acceptance':'reject','character_affection':'neutral'})]
    results={'started_at':datetime.now(timezone.utc).isoformat(),'model_mode':'actual_qwen',
             'analyzer':[],'food':[],'response':[],'training_executed':False,'download_executed':False}
    def save():args.output.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    def post(path,body):
        r=client.post('/dev/character-lab'+path,json=body)
        if r.status_code!=200:raise RuntimeError(f'{path}: {r.status_code} {r.text[:500]}')
        return r.json()
    for text,expected in cases:
        print('Analyzer: '+text,flush=True)
        try:
            result=post('/conversation/analyze',{'text':text,'mode':'qwen','generation':dict(DEFAULT_GENERATION,seed=20261004)})
            prediction=result['prediction'] or {}
            row={'text':text,'expected':expected,'result':result,
                 'matches_expected':all(prediction.get(k)==v for k,v in expected.items())}
            results['analyzer'].append(row)
            print('match='+str(row['matches_expected'])+' prediction='+json.dumps(prediction,ensure_ascii=False),flush=True)
        except Exception as e:
            results['analyzer'].append({'text':text,'error':str(e),'matches_expected':False})
        save()
    print('FoodAnalyzer: incomplete food name',flush=True)
    try:
        result=post('/food/analyze',{'text':'치킨, 감자튀김, 콜라','mode':'qwen'})
        results['food'].append(result)
    except Exception as e:results['food'].append({'error':str(e)})
    save()
    state=client.get('/dev/character-lab/state').json()['session']
    memory=[{'id':'synthetic-preference','content':'나는 짧게 걷는 것이 좋아.','source_id':'synthetic-manual-memory','slot':'preference'}]
    for text in ['오늘 운동하기 싫어','오늘 할 수 있는 작은 목표를 추천해 줘']:
        print('Responder A/B: '+text,flush=True)
        try:
            result=post('/conversation/respond',{'text':text,'mode':'qwen','session':state,
                'a':dict(state['state'],activity=85,affection=80,initiative=80),
                'b':dict(state['state'],activity=25,affection=80,initiative=25),
                'memory':memory,'generation':dict(DEFAULT_GENERATION,seed=20261004)})
            results['response'].append(result)
            for side in ('a','b'):
                print(side+': '+json.dumps(result['results'][0][side]['output'],ensure_ascii=False),flush=True)
        except Exception as e:results['response'].append({'user_text':text,'error':str(e)})
        save()
    results['completed_at']=datetime.now(timezone.utc).isoformat()
    results['summary']={'analyzer_matches':sum(x.get('matches_expected',False) for x in results['analyzer']),
                        'analyzer_total':len(cases),'response_pairs':sum('results' in x for x in results['response']),
                        'response_fallbacks':sum(x['results'][0][side]['metrics']['fallback'] for x in results['response'] if 'results' in x for side in ('a','b'))}
    save();print(json.dumps(results['summary']),flush=True)


if __name__=='__main__':main()
