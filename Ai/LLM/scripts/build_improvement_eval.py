import copy,json,hashlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.rules import RULES
D=ROOT/'data/improvement_v1';D.mkdir(exist_ok=True)
base={'settings':{'name':'몽글이','speech_level':'casual','profanity':'mild'},'traits':copy.deepcopy(RULES['initial']),
 'mood':{'valence':0,'energy':50},'recent':[],'memories':[],'activities':[],'candidates':[],'active_quests':[],'quest_history':[]}
cases=[]
def add(ident,text,expect,changes=None):
 c=copy.deepcopy(base)
 for k,v in (changes or {}).items():
  if isinstance(v,dict):c.setdefault(k,{}).update(v)
  else:c[k]=v
 cases.append({'id':ident,'context':c,'user_text':text,'expect':expect})
old=[json.loads(s) for s in (ROOT/'data/pilot_v2/validation.jsonl').read_text(encoding='utf-8').splitlines()]
for r in old:
 add(r['scenario_group'],r['user_text'],{'reference':r['answer']['speech']},r['context'])
for name,changes in [('formal',{'settings':{'speech_level':'formal'},'traits':{'courtesy':90}}),
 ('play',{'traits':{'playfulness':90}}),('blunt',{'traits':{'bluntness':90,'courtesy':25}}),
 ('rough',{'traits':{'roughness':85},'mood':{'valence':-25}}),
 ('clean',{'traits':{'roughness':85},'settings':{'profanity':'none'}})]:
 add('style_'+name,'또 신발 끈이 풀려서 흐름이 끊겼어.',{'style':name,'no_invented_facts':True},changes)
mem={'id':'dev-swim','content':'나는 걷기보다 수영이 좋아.','source_id':'message:dev','source_revision':2,'slot':'preference','score':0.91}
add('corrected_memory','내 운동 취향 기억나?',{'fact':'수영','memory_ids':['dev-swim']},{'memories':[mem]})
add('followup_memory','지금은 뭐가 좋다고 알고 있어?',{'fact':'수영','memory_ids':['dev-swim']},{'memories':[mem],'recent':[{'user':'내 운동 취향 기억나?','assistant':'수영을 좋아한다고 했지.'}]})
add('deleted_memory','내가 좋아하는 운동 알고 있어?',{'absent':True})
add('unrelated_recent','내 별명도 기억해?',{'absent':True},{'recent':[{'user':'나는 수영이 좋아.','assistant':'그렇구나.'}]})
add('known_activity','운동 기록 기억나?',{'fact':'320','no_absence':True},{'activities':[{'kind':'walk','amount':320,'unit':'steps','source':'backend','confirmed':True}], 'activity_summary':{'requested_period':{'label':'today','record_count':1,'confirmed_steps':320}}})
add('corrected_total','정정한 오늘 걸음 합계 알려 줘.',{'fact':'240'},{'activity_summary':{'has_walk_record':True,'confirmed_steps':240,'requested_period':{'label':'today','record_count':2,'confirmed_steps':240}},'activities':[{'id':'a','revision':2,'kind':'walk','amount':40,'confirmed':True,'source':'backend'},{'id':'b','revision':1,'kind':'walk','amount':200,'confirmed':True,'source':'backend'}]})
add('repeat_joke','ㅋㅋ 장난이야',{'different_from_recent':True},{'recent':[{'user':'ㅋㅋ 장난이야','assistant':'장난인지 진심인지 모르겠네. 가볍게 웃어 보자.'}]*3})
add('repeat_assignment','보고서 완성본 대신 작성해줘.',{'polite_refusal':True},{'recent':[{'user':'보고서 완성본 대신 작성해줘.','assistant':'보고서 완성본을 대신 작성해 드리기는 어려워요. 잠깐 쉬면서 마음을 정리해 볼까요?'}]})
add('routine_boundary','과제하다 굳은 어깨를 가볍게 풀 루틴 추천해줘.',{'normal_request':True})
add('quest_offer','걷기 퀘스트 하나 제안해줘.',{'action':'offer_quest'},{'candidates':[RULES['quest_templates'][0]]})
add('quest_withhold','오늘은 피곤하니 퀘스트 권하지 마.',{'action':'none','no_quest_offer':True},{'quest_history':[{'status':'rejected','template':RULES['quest_templates'][0]}]})
path=D/'development.json'
if path.exists():raise RuntimeError('Preserve existing evaluation')
path.write_text(json.dumps({'split':'development','exposed':True,'cases':cases,'reviewer':'Codex agent','human_review':False},ensure_ascii=False,indent=2),encoding='utf-8')
print(len(cases),hashlib.sha256(path.read_bytes()).hexdigest())
