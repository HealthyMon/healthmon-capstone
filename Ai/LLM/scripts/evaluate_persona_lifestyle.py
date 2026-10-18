"""Nine dry-run presets x six questions through the running local LoRA, no training."""
import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.persona_lifestyle import LIFESTYLE_PRESETS
from src.persona_lifestyle_service import TEST_QUESTIONS

OUT = ROOT / 'runs/persona-lifestyle'
ORIGIN = 'http://127.0.0.1:8001'
HEADERS = {'Origin': ORIGIN, 'X-Persona-Lab': '1'}


def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    temp = OUT / (name + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(OUT / name)


def run(resume=False):
    path = OUT / 'actual-model-comparisons.json'
    rows = json.loads(path.read_text(encoding='utf-8')) if resume and path.exists() else []
    finished = {row['id'] for row in rows}
    projections = {}
    # One explicit synthetic memory is kept identical in every before/after pair.
    memories = [{'id':'lifestyle-memory-1','content':'나는 짧고 부담 없는 활동을 선호해.',
                 'source_id':'synthetic-evaluation-preference','source_revision':1,
                 'slot':'preference','verification_status':'user_reported'}]
    with httpx.Client(timeout=600, headers=HEADERS, trust_env=False) as client:
        health = client.get(ORIGIN+'/api/health'); health.raise_for_status()
        save('evaluation-manifest.json', {'health': health.json(), 'preset_count': 9, 'questions': TEST_QUESTIONS,
              'memories':memories,'seed':20261001,'training_data':False,'database_write':False,
              'scope':'Actual current LoRA before/after record history; same memory, user text, seed, settings and comparison timestamp. One seed per condition; not a LoRA-only causal test.'})
        for preset, definition in LIFESTYLE_PRESETS.items():
            response = client.post(ORIGIN+'/api/lifestyle/simulate', json={'records':definition['input']})
            response.raise_for_status()
            projections[preset] = response.json()
        save('projections.json',projections)
        for preset, definition in LIFESTYLE_PRESETS.items():
            for index, text in enumerate(TEST_QUESTIONS):
                ident = f'{preset}:{index+1}'
                if ident in finished:
                    continue
                request = {'records':definition['input'], 'text':text, 'mode':'qwen', 'memories':memories,
                           'generation':{'seed':20261001},'start':'2026-10-01T00:00:00+09:00'}
                response = client.post(ORIGIN+'/api/lifestyle/compare',json=request)
                response.raise_for_status()
                data = response.json()
                rows.append({'id':ident,'preset':preset,'label':definition['label'],'request':request,'response':data})
                save('actual-model-comparisons.json', rows)
                pair=data['results'][0]
                print(f"{len(rows)}/54 {ident} A={pair['a']['output_origin']} B={pair['b']['output_origin']}",flush=True)
        outcomes=Counter(row['response']['results'][0][side]['output_origin'] for row in rows for side in ('a','b'))
        summary={'completed_pairs':len(rows),'final_output_origins':dict(outcomes),
                 'shared_memories':all(row['response']['contexts']['a']['memories']==row['response']['contexts']['b']['memories'] for row in rows),
                 'shared_timestamp':all(row['response']['contexts']['a']['as_of']==row['response']['contexts']['b']['as_of'] for row in rows),
                 'all_seed_same':all(row['response']['results'][0]['seed']==20261001 for row in rows),
                 'first_pass_valid':sum(row['response']['results'][0][s]['metrics'].get('attempts')==1 for row in rows for s in ('a','b')),
                 'actual_results_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                 'quality_verdict':'Requires separate semantic review; schema or lexical differences are not quality passes.'}
        save('verification-summary.json',summary)
        print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--resume',action='store_true')
    run(parser.parse_args().resume)
