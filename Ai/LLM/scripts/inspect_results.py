import json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for name in ['baseline-validation.json','lora-validation.json']:
    d=json.loads((ROOT/'runs'/name).read_text(encoding='utf-8'))
    syntax=0
    for r in d['results']:
        try:json.loads(r['raw']);syntax+=1
        except ValueError:pass
    print(name,{'json_parse':f'{syntax}/{d["count"]}','contract_at_run':f'{sum(r["raw_valid"] for r in d["results"])}/{d["count"]}',
                'mean_seconds':round(statistics.mean(r['latency_seconds'] for r in d['results']),2)})
metrics=[json.loads(s) for s in (ROOT/'runs/pilot-20260929/metrics.jsonl').read_text().splitlines()]
samples=[r for r in metrics if r['event']=='backward']
print('training',{'unique_samples':34,'epochs':3,'processed_samples':len(samples),
      'peak_device_used_mib':max(int(r['device_used_total_mib'].split(',')[0]) for r in samples),
      'seconds':round(metrics[-1]['time']-metrics[0]['time'],1),**{k:v for k,v in metrics[-1].items() if k not in ('event','time')}})
path=ROOT/'runs/flows-development.json'
if path.exists():
    d=json.loads(path.read_text(encoding='utf-8'));flows=d['flows']
    print('flows',{'finished':len(flows),'turns':sum(len(f['turns']) for f in flows),
          'state_pass':sum(f['state_rule_pass'] is True for f in flows),
          'state_fail':sum(f['state_rule_pass'] is False for f in flows),
          'fallbacks':sum(t['metrics']['fallback'] for f in flows for t in f['turns']),
          'http_errors':sum(len(f['errors']) for f in flows)})
