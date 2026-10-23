import json,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[1];run=root/'runs/expanded-20260929'
events=[json.loads(l) for l in (run/'metrics.jsonl').read_text().splitlines()];back=[r for r in events if r['event']=='backward']
conf=json.loads((run/'config.json').read_text(encoding='utf-8'))
summary={'run':str(run),'init_adapter':conf['init_adapter'],'training_examples':216,'sample_visits':len(back),
 'optimizer_steps':sum(r['event']=='optimizer_update' for r in events),'completed_epochs':max(r['epoch'] for r in back),
 'wall_seconds':events[-1]['time']-events[0]['time'],'bf16':conf['bf16'],'rank':conf['rank'],'alpha':conf['alpha'],'learning_rate':conf['lr'],
 'trainable':conf['trainable'],'max_sequence_length':conf['max_length'],
 'peak_allocated_gib':max(r['peak_allocated_gib'] for r in back),'peak_reserved_gib':max(r['peak_reserved_gib'] for r in back),
 'device_sample_peak_mib':max(int(r['device_used_total_mib'].split(',')[0]) for r in back),
 'online_validation':[{k:r[k] for k in ['epoch','loss','checkpoint']} for r in events if r['event']=='validation'],
 'online_validation_count':44,'clean_selection_validation_count':43,'end_status':events[-1]['event'],
 'early_stop':any(r['event']=='early_stop' for r in events),'new_data_resume':False,'human_review':False,
 'training_data_sha256':hashlib.sha256((root/'data/improvement_v2/train.jsonl').read_bytes()).hexdigest(),
 'same_train_file_v3':(root/'data/improvement_v2/train.jsonl').read_bytes()==(root/'data/improvement_v3/train.jsonl').read_bytes()}
(root/'runs/improvement-20260929/training-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
