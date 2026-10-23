"""Mechanical checks only. Agent semantic labels are recorded separately."""
import argparse,json,re,sys,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.contracts import ModelOutput
from src.agent import validate
from src.evidence import repeated
p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('--output',required=True);args=p.parse_args()
payload=json.loads((ROOT/args.input).read_text(encoding='utf-8'));report=[]
def score(raw,row):
 errors=[]
 try:obj=json.loads(raw)
 except (ValueError,TypeError):return ['json_syntax']
 try:o=ModelOutput.model_validate(obj)
 except ValueError:return ['schema']
 try:validate(raw,row['context'],row['input'])
 except ValueError as e:errors.append('guard:'+str(e).split('\n')[0])
 e=row['expect'];s=o.speech
 fact=e.get('fact');normalized=re.sub(r'[, ]','',s) if fact and fact.isdigit() else s
 if fact and fact not in normalized:errors.append('expected_fact_missing')
 if e.get('memory_ids') and set(o.memory_ids)!=set(e['memory_ids']):errors.append('memory_citation')
 if e.get('action') and o.action.type!=e['action']:errors.append('quest_action')
 if e.get('different_from_recent') and repeated(s,[r['assistant'] for r in row['context']['recent']]):errors.append('repetition')
 if e.get('normal_request') and re.search(r'대행|대신.{0,16}(어려|없)|도와.{0,8}(없|어려)',s):errors.append('false_refusal')
 return errors
for model in payload['models']:
 rows=[]
 for r in model['results']:
  raw=r['attempts'][0].get('raw','')
  rows.append({'id':r['id'],'raw_errors':score(raw,r),'final_errors':score(json.dumps(r['final'],ensure_ascii=False),r),'fallback':r['metrics']['fallback'],'repaired':r['metrics']['repaired']})
 report.append({'adapter':model['adapter'],'executed':len(rows),'fallback':sum(r['fallback'] for r in rows),'repaired':sum(r['repaired'] for r in rows),
 'raw_error_counts':dict(collections.Counter(e for r in rows for e in r['raw_errors'])),
 'final_error_counts':dict(collections.Counter(e for r in rows for e in r['final_errors'])),'rows':rows})
out=ROOT/args.output
if out.exists():raise RuntimeError('Preserve score file')
out.write_text(json.dumps({'source':args.input,'review_type':'mechanical probes, not semantic success','models':report},ensure_ascii=False,indent=2),encoding='utf-8')
for r in report:print(json.dumps({k:v for k,v in r.items() if k!='rows'},ensure_ascii=False))
