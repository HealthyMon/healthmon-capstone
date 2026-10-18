"""Write an evidence-linked status, keeping prior FINAL_STATUS.json intact."""
import json,statistics,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'runs/improvement-20260929'
read=lambda p:json.loads((ROOT/p).read_text(encoding='utf-8'))
data=read('data/improvement_v3/manifest.json')
mechanical=read('runs/improvement-20260929/final-mechanical.json')
semantic=read('runs/improvement-20260929/final-semantic-review.json')
replay=read('runs/improvement-20260929/server-guard-replay.json')
http=read('runs/improvement-20260929/live-http.json')
preservation=read('runs/improvement-20260929/preservation-verified.json')
models=[]
for m,s,r in zip(mechanical['models'],semantic['models'],replay['models']):
    assert m['executed']==s['executed']==58
    models.append({'adapter':m['adapter'],'requests':58,
        'raw_json_syntax_errors':m['raw_error_counts'].get('json_syntax',0),
        'raw_schema_errors':m['raw_error_counts'].get('schema',0),
        'raw_semantic_flags':s['raw_counts'],'observed_server_semantic_flags':s['server_counts'],
        'observed_fallback_count':m['fallback'],'observed_fallback_rate':m['fallback']/58,
        'post_hoc_guard_replay_fallback_count':r['fallback']})
calls=[r for r in http['results'] if r['result']['metrics']['attempts']>0]
live={'executed_chat_turns':len(http['results']),'model_request_turns':len(calls),
      'deterministic_memory_command_turns':len(http['results'])-len(calls),
      'fallback_count':sum(r['result']['metrics']['fallback'] for r in calls),
      'semantic_success_count':None,'http_script_completed':True,
      'first_attempts_and_failed_raw_outputs_persisted':False,
      'model_latency_median_seconds':statistics.median(r['result']['metrics']['latency_seconds'] for r in calls),
      'model_latency_max_seconds':max(r['result']['metrics']['latency_seconds'] for r in calls),
      'reviewer':'Codex agent','human_review':False,
      'finding':'Preference write/retrieval/follow-up, authenticated source correction and deletion, normal movement and polite assignment refusal observed. Last repeated rest request fell back after two ValueErrors; failed raw outputs are unavailable for that HTTP turn.'}
(D/'live-http-review.json').write_text(json.dumps(live,ensure_ascii=False,indent=2),encoding='utf-8')
status={'status':'expanded_training_and_comparison_complete_with_quality_regressions',
        'production_quality_approved':False,'overall_superiority_claimed':False,
        'targets':data['targets'],'actual_data_counts':data['counts'],'data_target_complete':False,
        'reviewer':'Codex agent (same author and evaluator)','human_reviewed_count':0,
        'external_data_used_count':0,'selected_adapter':'runs/expanded-20260929/checkpoint-epoch-1',
        'selection_used_final_test':False,'final_test_now_exposed_for_future_work':True,
        'training':read('runs/improvement-20260929/training-summary.json'),
        'comparison':models,'comparison_semantic_success_count':None,
        'post_hoc_guard_replay_is_new_model_inference':False,'live_http':live,
        'preservation':preservation,
        'report':'docs/IMPROVEMENT_RESULTS.md','direct_test_guide':'docs/EXPANDED_RUN_GUIDE.md',
        'remaining':['data target shortfall','no independent human review','provided-memory contradictions and time changes','quest target/progress reversal','repeated dialogue fallback','single active preference/goal slot limitation','team production integration not verified']}
(ROOT/'IMPROVEMENT_STATUS.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'data':status['actual_data_counts'],'comparison':models,'live_http':live,'preservation':preservation},ensure_ascii=False))
