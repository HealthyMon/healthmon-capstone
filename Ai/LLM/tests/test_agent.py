import copy,json
import pytest
from src.agent import validate,respond
from src.rules import RULES

CONTEXT={'settings':{'name':'몽글이','speech_level':'casual','profanity':'mild'},'traits':RULES['initial'],
         'mood':{},'recent':[],'memories':[],'candidates':[],'active_quests':[]}
def output(speech,**extra):
    return json.dumps({'speech':speech,'emotion':'neutral','animation':'idle','action':{'type':'none','target_id':None},'memory_ids':[],'personality_update':None,**extra},ensure_ascii=False)

def test_claimed_memory_and_execution_rejected():
    with pytest.raises(ValueError):validate(output('네 취향을 알고 있어.'),CONTEXT,'내가 좋아하는 운동 알고 있어?')
    with pytest.raises(ValueError):validate(output('별명을 알려 줬었지? 네 말에 따라 기억하고 있을게.'),CONTEXT,'내 별명도 기억해?')
    with pytest.raises(ValueError):validate(output('알고 있는 운동이 있네! 네 취향에 맞는 걸 알려 줄게.'),CONTEXT,'내가 좋아하는 운동을 알고 있어?')
    with pytest.raises(ValueError):validate(output('알아. 좋아하는 운동에 대한 기록이 없어.'),CONTEXT,'내가 좋아하는 운동을 알고 있어?')
    with pytest.raises(ValueError):validate(output('오늘 500 걸음 퀘스트가 남아 있어.'),CONTEXT,'나는 걷는 게 좋아')
    with pytest.raises(ValueError):validate(output('운동 확인 완료로 처리.'),CONTEXT,'운동했어')
    assert validate(output('지금은 취향을 확인할 기록이 없어. 알려 줄래?'),CONTEXT,'내 취향 기억해?')

def test_permissions_and_politeness():
    with pytest.raises(ValueError):validate(output('기억해.',memory_ids=['another-user']),CONTEXT,'안녕')
    with pytest.raises(ValueError):validate(output('퀘스트야',action={'type':'offer_quest','target_id':'invented'}),CONTEXT,'안녕')
    with pytest.raises(ValueError):validate(output('과제 대행은 안 해.'),CONTEXT,'과제 전체 대신 써줘')
    ctx=copy.deepcopy(CONTEXT);ctx['settings']['profanity']='none'
    with pytest.raises(ValueError):validate(output('아, 젠장.'),ctx,'끈이 풀렸어')
    ctx=copy.deepcopy(CONTEXT);ctx['memories']=[{'id':'m1','content':'나는 걷는 게 좋아.'}]
    with pytest.raises(ValueError):validate(output('좋아하는 운동에 대한 기록이 없어.',memory_ids=['m1']),ctx,'내가 좋아하는 운동 기억해?')

def test_two_generation_limit_shared_by_repetition_and_schema():
    class Backend:
        calls=0
        def generate(self,*args):
            self.calls+=1
            return output('반가워.') if self.calls==1 else 'invalid'
    ctx=copy.deepcopy(CONTEXT);ctx['recent']=[{'user':'안녕','assistant':'반가워.'}]
    b=Backend();out,metrics=respond(b,ctx,'안녕')
    assert b.calls==2 and metrics['fallback'] and out.action.type=='none'
    assert metrics['failure_codes']==['repeated_response','output_validation']
    assert len(metrics['generation_attempt_seconds'])==2
