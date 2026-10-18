import json, re, time
from difflib import SequenceMatcher
from .contracts import ModelOutput,Action
from .rules import role_intent
from .evidence import relevant_recent_fact,repeated

def validate(raw,context,text):
    out=ModelOutput.model_validate_json(raw)
    if '<think' in out.speech or re.search(r'[{}]',out.speech): raise ValueError('UI content invalid')
    if not re.search('[가-힣]',out.speech): raise ValueError('Korean required')
    if re.search(r'[\u0e00-\u0e7f\u4e00-\u9fff]',out.speech):raise ValueError('Unexpected foreign script in Korean dialogue')
    if context['settings']['speech_level']=='formal' and not re.search(r'요[.!? ]|니다[.!? ]|요$|니다$',out.speech):
        raise ValueError('Requested formal speech level')
    if context['settings']['profanity']=='none' and re.search('젠장|씨발|시발|존나|개새|닥쳐',out.speech):
        raise ValueError('Expression limit')
    if re.search('씨발|시발|개새끼|병신',out.speech): raise ValueError('Expression limit')
    if re.search(r'완료로 처리|확인 완료|보상.{0,8}(지급했|지급됐|줬어)|점수.{0,8}(바꿨어|변경했)',out.speech):
        raise ValueError('Model cannot declare execution, confirmation or rewards')
    if out.personality_update is not None: raise ValueError('State proposals disabled in rules.v1')
    if not set(out.memory_ids)<= {m['id'] for m in context['memories']}: raise ValueError('Unknown memory')
    # "다른 취향은 기억에 없어" does not negate the cited fact in another clause.
    clauses=re.split(r'[.!?]\s*',out.speech)
    unqualified=[s for s in clauses if not re.match(r'^(?:(?:하지만|그리고|그런데)\s+)?(?:다른|그 외|그밖|나머지)',s.strip())]
    if out.memory_ids and any(re.search(r'(기록|기억).{0,12}없|확인할.{0,8}없',s) for s in unqualified):
        raise ValueError('Cited existing memory contradicts claimed missing record')
    lookup=bool(re.search(r'기억|내.*(취향|좋아하는|목표|별명)|지난번|지난주',text))
    recent_facts=relevant_recent_fact(text,context['recent'])
    activity_facts=bool(re.search(r'운동|걸음|걷|활동',text) and not re.search(r'취향|좋아|목표',text) and
                        (context.get('activities') or context.get('activity_summary',{}).get('requested_period',{}).get('record_count',0)>0))
    if lookup and not context['memories'] and not recent_facts and not activity_facts:
        if re.search(r'^(알아|알고 있어|기억해|기억하고 있어)[.! ]',out.speech):
            raise ValueError('Do not affirm knowing an absent past fact')
        if not re.search(r'모르|몰라|없|못|기억하.{0,3}않|알지.{0,3}않|확인.*필요|(?:기록|기억).{0,10}남아\s*있지\s*않|기억.{0,6}(?:안\s*나|나지\s*않)|기억.{0,10}떠오르.{0,5}않',out.speech):
            raise ValueError('No evidence for requested past fact; acknowledge missing record')
    if re.search(r'walk_\d+|message:|activity:',out.speech):raise ValueError('Do not display internal IDs in dialogue')
    if not context['active_quests'] and re.search(r'퀘스트.{0,10}남아|남은.{0,8}(걸음|퀘스트)',out.speech):
        raise ValueError('No accepted active quest; candidates are only offers')
    # IDs can be checked mechanically; semantic factual accuracy is evaluated separately.
    if out.action.type=='offer_quest' and out.action.target_id not in {q['id'] for q in context['candidates']}:
        raise ValueError('Unauthorized quest')
    if out.action.type=='show_progress' and out.action.target_id not in {q['id'] for q in context['active_quests']}:
        raise ValueError('Unknown active quest')
    if role_intent(text)=='assignment' and not re.search('어려|없|않|대행',out.speech):
        raise ValueError('Assignment completion is outside product role')
    if role_intent(text)=='assignment' and not re.search(r'요[.!? ]|니다[.!? ]|요$|니다$',out.speech):
        raise ValueError('Assignment refusal must use polite Korean')
    return out

def respond(backend,context,text):
    started=time.monotonic(); metrics={'attempts':0,'raw_valid':False,'repaired':False,'fallback':False,'errors':[],
                                      'failure_codes':[],'generation_attempt_seconds':[]}
    repair=None
    for attempt in range(2):
        metrics['attempts']+=1
        raw=''
        attempt_started=time.monotonic()
        try:
            raw=backend.generate(context,text,repair)
            out=validate(raw,context,text)
            if attempt==0: metrics['raw_valid']=True
            recent=[r['assistant'] for r in context['recent'][-3:]]
            fact_recheck=bool(re.search(r'기억|기록|합계|몇 걸음|취향|목표|별명',text))
            terminal_close=bool(re.fullmatch(r'(?:나[는]?\s*)?(?:이제\s*|슬슬\s*)?(?:잘게|잘\s*자|내일\s*보자|안녕히\s*계세요|안녕히\s*가세요)[.!~ ]*',text))
            if role_intent(text)!='assignment' and not fact_recheck and not terminal_close and repeated(out.speech,recent):
                raise ValueError('Unnecessary repeated response')
            metrics['repaired']=bool(attempt); metrics['latency_seconds']=time.monotonic()-started
            return out,metrics
        except (ValueError,RuntimeError,TimeoutError) as e:
            # Record error category only, never copy personal dialogue into operational logs.
            reason=str(e)[:180] if isinstance(e,ValueError) else type(e).__name__
            repair={'raw':raw,'reason':reason}
            metrics['errors'].append(type(e).__name__)
            metrics['failure_codes'].append('repeated_response' if reason=='Unnecessary repeated response'
                else 'output_validation' if isinstance(e,ValueError) else type(e).__name__)
            if isinstance(e,(RuntimeError,TimeoutError)): break
        finally:
            metrics['generation_attempt_seconds'].append(time.monotonic()-attempt_started)
    metrics['fallback']=True; metrics['latency_seconds']=time.monotonic()-started
    speech='잠깐 말이 꼬였어. 조금 뒤에 다시 이야기해 줄래?'
    if context['settings']['speech_level']=='formal':speech='잠깐 말이 꼬였어요. 조금 뒤에 다시 이야기해 주실래요?'
    if not context['memories'] and re.search(r'기억|내.*(취향|좋아하는|목표|별명)|지난번|지난주',text):
        speech='지금은 그걸 확인할 기억이 없어. 다시 알려 줄래?'
        if context['settings']['speech_level']=='formal':speech='지금은 그걸 확인할 기억이 없어요. 다시 알려 주실래요?'
    if role_intent(text)=='assignment': speech='제출할 과제 완성본을 대신 만들어 드리기는 어려워요. 시작할 수 있게 응원할게요.'
    memory_ids=[]
    if re.search(r'기억|내.*(취향|좋아하는|목표|별명)',text) and len(context['memories'])==1:
        memory=context['memories'][0];content=memory['content']
        relevant=(memory.get('slot')=='preference' and bool(re.search(r'좋아|취향',text))) or (memory.get('slot')=='goal' and '목표' in text) or (memory.get('slot')=='experience' and bool(re.search(r'어제|지난|경험',text)))
        if relevant and role_intent(text)!='assignment' and len(content)<180 and not re.search(r'씨발|시발|젠장|SQL|규칙|<|>|[{}]',content):
            speech=f'기록에는 “{content}”라고 남아 있어.'
            if context['settings']['speech_level']=='formal':speech=f'기록에는 “{content}”라고 남아 있어요.'
            memory_ids=[memory['id']]
            metrics['grounded_excerpt_fallback']=True
    return ModelOutput(speech=speech,emotion='neutral',animation='idle',action=Action(),memory_ids=memory_ids),metrics
