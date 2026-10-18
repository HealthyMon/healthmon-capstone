import copy,json
import pytest
from src.agent import validate,respond
from test_agent import CONTEXT,output

def test_partial_absence_does_not_negate_cited_preference():
 c=copy.deepcopy(CONTEXT);c['memories']=[{'id':'m','content':'나는 민트 향을 좋아하지 않아.','slot':'preference'}]
 assert validate(output('민트 향은 좋아하지 않아. 다른 취향은 기억에 없어.',memory_ids=['m']),c,'내 음료 취향 알려 줘.')
 with pytest.raises(ValueError):validate(output('취향에 대한 기억이 없어.',memory_ids=['m']),c,'내 취향 기억해?')

def test_natural_absence_variants_and_false_affirmation():
 for speech in ['처음 만난 기록이 남아 있지 않아서 기억이 안 나네.','처음 만났던 기억이 딱 떠오르지는 않네.']:
  assert validate(output(speech),CONTEXT,'우리가 예전에 어디서 만났는지 기억해?')
 with pytest.raises(ValueError):validate(output('알아. 기억이 안 나네.'),CONTEXT,'내 별명 기억해?')

def test_terminal_farewell_keeps_generated_closing_without_error_fallback():
 c=copy.deepcopy(CONTEXT);c['recent']=[{'user':'나 이제 잘게.','assistant':'편히 자. 내일 또 이야기하자.'}]*2
 class B:
  calls=0
  def generate(self,*args):self.calls+=1;return output('편히 자. 내일 또 이야기하자.')
 b=B();o,m=respond(b,c,'나 이제 잘게.')
 assert b.calls==1 and not m['fallback'] and o.speech=='편히 자. 내일 또 이야기하자.'
