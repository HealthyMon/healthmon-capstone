"""Query routing, not answer generation. Explicit topic wins over recent context."""
import re

def memory_slot(text,recent=()):
    if re.search(r'별명|호칭',text):return 'nickname'
    if '목표' in text:return 'goal'
    if re.search(r'취향|좋아하는|좋아한다고|선호|나는 .*(좋아|싫어)',text):return 'preference'
    if re.search(r'지금은 뭐|그럼 뭐|그건|그거|기억나|기억해',text):
        for turn in reversed(recent[-2:]):
            slot=memory_slot(turn['user'])
            if slot:return slot
    return None

def relevant_recent_fact(text,recent):
    slot=memory_slot(text,recent)
    patterns={'nickname':r'내 별명은','goal':r'내 목표는|목표로 정했',
              'preference':r'나는 .*(좋아|싫어)|보다 .*좋아'}
    pattern=patterns.get(slot)
    return bool(pattern and any(re.search(pattern,r['user']) and '?' not in r['user'] for r in recent))

def repeated(speech,recent):
    from difflib import SequenceMatcher
    norm=lambda s:re.sub(r'[^가-힣a-z0-9]','',s.lower())
    a=norm(speech)
    return any(a and SequenceMatcher(None,a,norm(r)).ratio()>0.90 for r in recent)
