"""Conservative near-paraphrase audit: preserve original sets, move overlaps to regression."""
import json,hashlib,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];src=ROOT/'data/improvement_v2';dst=ROOT/'data/improvement_v3'
if dst.exists():raise RuntimeError('Version already exists')
dst.mkdir()
shutil.copy2(src/'train.jsonl',dst/'train.jsonl')
val=[json.loads(l) for l in (src/'validation.jsonl').read_text(encoding='utf-8').splitlines()]
excluded_val=[r for r in val if r['sample_id']=='expanded-v2-0259']
val=[r for r in val if r not in excluded_val]
(dst/'validation.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in val),encoding='utf-8')
final=json.loads((src/'final-frozen.json').read_text(encoding='utf-8'))
excluded_final=[r for r in final['cases'] if r['id'] in ['f_chem_move','f_repeat_refusal']]
final['cases']=[r for r in final['cases'] if r not in excluded_final]
(dst/'final-frozen.json').write_text(json.dumps(final,ensure_ascii=False,indent=2),encoding='utf-8')
(dst/'final-freeze.json').write_text(json.dumps({'count':len(final['cases']),'sha256':hashlib.sha256((dst/'final-frozen.json').read_bytes()).hexdigest(),
 'scenario_groups':len({r['scenario_group'] for r in final['cases']}),'frozen_before_any_final_generation':True,'human_review':False},indent=2),encoding='utf-8')
(dst/'moved-to-regression.json').write_text(json.dumps({'validation':excluded_val,'final':excluded_final,
 'reason':'Train input differs mainly by afternoon modifier, course/body-part substitution, or repeated assignment phrasing. Exclude conservatively before selection/final inference.',
 'reviewed_kept':'f_mint query resembles preference queries, but negated food preference with distinct source fact differs from exercise preference scenario.',
 'human_review':False},ensure_ascii=False,indent=2),encoding='utf-8')
m=json.loads((src/'manifest.json').read_text(encoding='utf-8'));m.update(counts={'train':216,'validation':len(val),'final_test':len(final['cases'])},
 actual_training='runs/expanded-20260929 used identical train SHA256 from v2. Original 44-example online val retained in logs; final selection recomputes loss on clean 43-example v3 split.',
 sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [dst/'train.jsonl',dst/'validation.jsonl',dst/'final-frozen.json']})
m['distribution']['validation']['count']=len(val)
(dst/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(m['counts']))
