import json,statistics,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.agent import validate
rows=[json.loads(s) for s in (ROOT/'data/pilot_v2/validation.jsonl').read_text(encoding='utf-8').splitlines()]
bygroup={r['scenario_group']:r for r in rows}
paired=json.loads((ROOT/'runs/paired-validation.json').read_text(encoding='utf-8'))
summary=[]
for model in paired['models']:
    passed=0;failures=[]
    for result in model['results']:
        row=bygroup[result['group']]
        try:validate(result['raw'],row['context'],row['user_text']);passed+=1
        except ValueError as e:failures.append({'group':result['group'],'reason':str(e)})
    summary.append({'epoch':model['epoch'],'json_parse':model['json_parse'],'current_contract_valid':passed,
                    'n':model['count'],'mean_seconds':round(statistics.mean(x['latency_seconds'] for x in model['results']),3),'failures':failures})
flows=json.loads((ROOT/'runs/flows-development.json').read_text(encoding='utf-8'))['flows']
flow_stats={'flows':len(flows),'turns':sum(len(f['turns']) for f in flows),'two_sessions':sum(f['sessions']==2 for f in flows),
      'state_change_pass':sum(f['category']=='change' and f['state_rule_pass'] for f in flows),
      'state_maintain_pass':sum(f['category']=='maintain' and f['state_rule_pass'] for f in flows),
      'correction_flows':sum(f['category']=='correction' for f in flows),'fallback_turns':sum(t['metrics']['fallback'] for f in flows for t in f['turns']),
      'extra_generation_turns':sum(t['metrics']['attempts']>1 for f in flows for t in f['turns']),
      'http_errors':sum(len(f['errors']) for f in flows)}
report={'paired_current_policy_rescore':summary,'flow_stats':flow_stats,'human_review':False,'frozen_final_test_count':0,
        'semantic_review':'agent review: do not infer factual correctness from contract scores',
        'code_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'src').glob('*.py'))}}
(ROOT/'runs/evaluation-summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
