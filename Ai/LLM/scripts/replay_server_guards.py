"""Reapply server-only fixes to actual saved generations; not a fresh model benchmark."""
import copy,json,hashlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.agent import respond
D=ROOT/'runs/improvement-20260929';source=json.loads((D/'final-comparison.json').read_text(encoding='utf-8'))
reports=[];changes=[]
for model in source['models']:
 rows=[]
 for original in model['results']:
  class Recorded:
   used=0
   def generate(self,context,text,repair=None):
    a=original['attempts'][self.used]
    assert repair==a['repair_input'],(original['id'],'Repair prompt changed; new generation required')
    self.used+=1;return a['raw']
  b=Recorded();out,metrics=respond(b,original['context'],original['input'])
  metrics['latency_seconds']=None
  changed=out.model_dump()!=original['final'] or metrics['fallback']!=original['metrics']['fallback']
  row={'id':original['id'],'output':out.model_dump(),'metrics':metrics,'used_recorded_attempts':b.used,'changed':changed}
  rows.append(row)
  if changed:changes.append({'adapter':model['adapter'],'id':original['id'],'before':original['final'],'after':out.model_dump(),
    'fallback_before':original['metrics']['fallback'],'fallback_after':metrics['fallback']})
 reports.append({'adapter':model['adapter'],'executed_replays':len(rows),'fallback':sum(r['metrics']['fallback'] for r in rows),'results':rows})
report={'method':'Replay of recorded real Qwen generations through revised server guards. No new model inference. Original frozen results unchanged.',
 'agent_sha256':hashlib.sha256((ROOT/'src/agent.py').read_bytes()).hexdigest(),'human_review':False,'models':reports,'changes':changes}
(D/'server-guard-replay.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'models':[{k:v for k,v in r.items() if k!='results'} for r in reports],'changes':changes},ensure_ascii=False,indent=2))
