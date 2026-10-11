"""Agent labels after reading every raw attempt and final response of the 24-case legacy rerun."""
import json,collections
from pathlib import Path
root=Path(__file__).resolve().parents[1];p=root/'runs/improvement-20260929'
raw=[{'tone':['validation_walk','validation_assignment','validation_food','style_play','style_blunt','style_rough','deleted_memory','unrelated_recent'],
      'memory':['validation_memory','corrected_memory','followup_memory','unrelated_recent'],'quest':['validation_fatigue','corrected_total']},
     {'tone':['validation_assignment','style_play','known_activity'],'memory':['followup_memory','deleted_memory','unrelated_recent'],'repetition':['repeat_assignment']}]
final=[{'tone':['validation_walk','validation_food','style_play','style_blunt','style_rough','deleted_memory','unrelated_recent'],
        'memory':['corrected_memory','followup_memory','unrelated_recent','known_activity'],'quest':['validation_fatigue']},
       {'tone':['style_play'],'memory':['followup_memory','unrelated_recent','known_activity'],'repetition':['repeat_assignment']}]
source=json.loads((p/'legacy-comparison.json').read_text(encoding='utf-8'));reports=[]
for i,model in enumerate(source['models']):
 records=[]
 for r in model['results']:
  records.append({'id':r['id'],'raw_labels':[k for k,ids in raw[i].items() if r['id'] in ids],
    'final_labels':[k for k,ids in final[i].items() if r['id'] in ids],'fallback':r['metrics']['fallback']})
 reports.append({'adapter':model['adapter'],'executed':len(records),'raw_counts':{k:len(v) for k,v in raw[i].items()},
  'final_counts':{k:len(v) for k,v in final[i].items()},'records':records})
result={'reviewer':'Codex agent','human_review':False,'rubric':'Conservative material errors; tone includes unnatural Korean, abusive or absent requested style. Empty labels do not certify all aspects.',
 'models':reports,'regressions':['deleted_memory: base raw is valid JSON/schema and acknowledges unknown preference; pilot raw emotion=curious violates schema.',
 'repeat_assignment: pilot repeats the previous long alternative; base changes the response.',
 'known_activity: correct 320-step evidence is rejected by the old server and replaced with false missing-memory fallback for both models.'],
 'schema_counts_are_in':'legacy-mechanical.json'}
(p/'legacy-semantic-review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print('Saved agent review, 48 raw/final pairs')
