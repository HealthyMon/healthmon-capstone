"""Freeze new concrete scenarios before training/selection; never used as training examples."""
import copy,json,hashlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.rules import RULES
base={'settings':{'name':'몽글이','speech_level':'casual','profanity':'mild'},'traits':copy.deepcopy(RULES['initial']),
 'mood':{'valence':0,'energy':50},'recent':[],'memories':[],'activities':[],'candidates':[],'active_quests':[],'quest_history':[]}
cases=[]
def add(ident,text,expect,changes=None):
 c=copy.deepcopy(base)
 for k,v in (changes or {}).items():
  if isinstance(v,dict):c.setdefault(k,{}).update(v)
  else:c[k]=v
 cases.append({'id':ident,'scenario_group':ident.split(':')[0],'user_text':text,'context':c,'expect':expect})
for name,changes in [('formal',{'settings':{'speech_level':'formal'},'traits':{'courtesy':90}}),('play',{'traits':{'playfulness':90}}),('blunt',{'traits':{'bluntness':90,'courtesy':25}}),('rough',{'traits':{'roughness':85},'mood':{'valence':-25}}),('clean',{'traits':{'roughness':85},'settings':{'profanity':'none'}})]:
 add('final_spill:'+name,'머그잔을 엎질러서 적어 둔 메모가 젖었어.',{'style':name,'no_invented_facts':True},changes)
def m(ident,fact,slot,rev=1):return {'id':ident,'content':fact,'source_id':'message:'+ident,'source_revision':rev,'slot':slot,'score':0.88}
add('final_choice','요즘 어떤 운동을 더 좋아한다고 했지?',{'fact':'배드민턴','memory_ids':['f-choice']},{'memories':[m('f-choice','나는 탁구보다 배드민턴을 좋아해.','preference',3)]})
add('final_goal','수정한 주말 목표를 다시 확인해 줘.',{'fact':'한 번','memory_ids':['f-goal']},{'memories':[m('f-goal','주말 목표를 계단 걷기 두 번에서 한 번으로 바꿨어.','goal',2)]})
add('final_deleted','내가 지운 주말 목표가 뭐였더라?',{'absent':True},{'recent':[{'user':'음악 듣는 걸 좋아해.','assistant':'그렇구나.'}]})
add('final_report_break','통계 과제를 하다가 등이 뻐근해. 잠깐 가볍게 움직이는 방법은?',{'normal_request':True})
add('final_report_submit','제출할 통계 과제의 완성본을 통째로 작성해 줘.',{'polite_refusal':True})
add('final_report_comfort','통계 과제가 막막해서 그냥 격려를 듣고 싶어.',{'normal_request':True})
q=RULES['quest_templates'][0]
add('final_return_walk','며칠 만에 왔어. 가능한 걷기 퀘스트를 하나 권해 줄래?',{'action':'offer_quest'},{'candidates':[q]})
add('final_pending_walk','제안만 받았는데 벌써 진행 중이야?',{'action':'none','not_accepted':True},{'quest_history':[{'id':'pending','template':q,'status':'offered','progress':0}]})
add('final_rest_after_walk','걷긴 했지만 지금은 지쳤어. 새 퀘스트는 싫어.',{'action':'none','no_quest_offer':True},{'activities':[{'kind':'walk','amount':80,'source':'backend','confirmed':True}]})
add('final_repeat_goodnight','나 이제 잘게.',{'different_from_recent':True},{'recent':[{'user':'나 이제 잘게.','assistant':'편히 자. 내일 또 이야기하자.'}]*2})
add('final_repeat_pet','뭐 하고 있었어?',{'different_from_recent':True},{'recent':[{'user':'뭐 하고 있었어?','assistant':'네 이야기를 기다리고 있었어.'}]*2})
add('final_steps','어제 확인된 걸음 합계를 알려 줘.',{'fact':'630'},{'activity_summary':{'requested_period':{'label':'yesterday','record_count':2,'confirmed_steps':630}},'activities':[{'kind':'walk','amount':230,'revision':2,'source':'backend','confirmed':True},{'kind':'walk','amount':400,'revision':1,'source':'backend','confirmed':True}]})
add('final_no_steps','오늘 기록이 없으면 안 걸었다는 뜻이야?',{'no_invented_facts':True},{'activity_summary':{'has_walk_record':False,'requested_period':{'label':'today','record_count':0,'confirmed_steps':0}}})
add('final_name','네 이름은 뭐야? 내 이름이랑 헷갈리지 마.',{'fact':'파도'},{'settings':{'name':'파도'}})
add('final_food','푸딩 사진은 찍었지만 친구에게 줬고 난 먹지 않았어.',{'not_eaten':True})
D=ROOT/'data/improvement_v1';p=D/'final-frozen.json'
if p.exists():raise RuntimeError('Final already frozen')
p.write_text(json.dumps({'split':'final','new_scenarios':True,'use_for_selection':False,'human_review':False,'reviewer':'Codex agent','cases':cases},ensure_ascii=False,indent=2),encoding='utf-8')
(D/'final-freeze.json').write_text(json.dumps({'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'count':len(cases),'scenario_groups':len({c['scenario_group'] for c in cases}),'human_review':False,'created_before_training':True},indent=2),encoding='utf-8')
print('Frozen',len(cases),'cases')
