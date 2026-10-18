"""Deterministic replay. Clipping is reapplied in original event order."""
import json, re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from difflib import SequenceMatcher

RULES = json.loads((Path(__file__).resolve().parents[1]/'config/rules.json').read_text())

def tags(text):
    return {'play': bool(re.search(r'ㅋㅋ|장난|농담',text)),
            'bond': bool(re.search(r'고마워|함께해서 좋|네 덕분|응원해 줘서',text)),
            'courtesy': bool(re.search(r'감사합니다|고마워요|부탁드려요|덕분이에요',text)),
            'blunt': bool(re.search(r'솔직하게 말해|툭툭 말해|까칠한 말투.*좋|새침한.*재밌',text)),
            'rough': bool(re.search(r'아[, ]*젠장|젠장[, ]*또|이런[, ]*젠장',text)),
            'tired': bool(re.search(r'피곤|힘들|지쳤|아파',text)) and not bool(re.search(r'피곤.{0,5}않|힘들.{0,5}않|안 아파|피곤함.{0,3}없',text))}

def replay(sources, now=None, tz='Asia/Seoul'):
    now=now or datetime.now(timezone.utc)
    state=dict(RULES['initial']); spent=defaultdict(float); history=[]
    mood={'valence':0.0,'energy':50.0}; last=None
    messages=[]; events=[]; consumed=defaultdict(set); used_texts=defaultdict(set)
    for s in sorted(sources,key=lambda x:(x['occurred_at'],x['id'])):
        if not s['valid']: continue
        at=s['occurred_at']; date=at.astimezone(ZoneInfo(tz)).date().isoformat()
        if last:
            minutes=max(0,(at-last).total_seconds()/60)
            mood['valence'] *= 2**(-minutes/RULES['valence_half_life_minutes'])
            mood['energy'] = 50+(mood['energy']-50)*2**(-minutes/RULES['energy_half_life_minutes'])
        last=at; payload=s['payload']; proposals=[]
        if s['kind']=='message':
            t=tags(payload.get('text',''))
            mood['valence'] += -10 if t['tired'] else (8 if t['bond'] or t['play'] else 0)
            mood['energy'] += -8 if t['tired'] else 0
            messages.append(s)
            if len(messages)%RULES['dialogue_review_every']==0:
                for tag,axis in [('play','playfulness'),('bond','bond'),('courtesy','courtesy'),('blunt','bluntness'),('rough','roughness')]:
                    candidates=[m for m in messages if tags(m['payload'].get('text',''))[tag]
                                and m['id'] not in consumed[axis]]
                    # Identical and near-identical utterances share a normalized fingerprint.
                    unique={}
                    for m in candidates:
                        key=re.sub(r'[^가-힣a-z]','',m['payload']['text'].lower())
                        if key and not any(SequenceMatcher(None,key,k).ratio()>0.8 for k in list(unique)+list(used_texts[axis])): unique[key]=m
                    evidence=list(unique.values())
                    if len(evidence)>=RULES['dialogue_min_evidence'] and len({m['session_id'] for m in evidence})>=RULES['dialogue_min_sessions']:
                        proposals.append((axis,1,evidence))
        else:
            if payload.get('confirmed') and payload.get('source') in ('sensor','backend'):
                events.append(s)
                if payload['kind']=='walk' and payload['amount']>0:
                    mood['valence']+=10; mood['energy']-=5
                axis='initiative' if payload['kind']=='walk' else 'sociability'
                evidence=[e for e in events if e['payload']['kind']==payload['kind']
                          and e['payload']['amount']>0 and e['id'] not in consumed[axis]]
                if payload['kind']=='food':
                    evidence=list({e['payload'].get('label'):e for e in evidence if e['payload'].get('label')}.values())
                if len(evidence)>=RULES['activity_min_events'] and len({e['occurred_at'].astimezone(ZoneInfo(tz)).date() for e in evidence})>=RULES['activity_min_dates']:
                    proposals.append((axis,1,evidence))
        mood['valence']=min(100,max(-100,mood['valence']))
        mood['energy']=min(100,max(0,mood['energy']))
        for axis,delta,evidence in proposals:
            allowed=min(abs(delta),RULES['max_delta'],max(0,RULES['daily_absolute_limit']-spent[(date,axis)]))
            delta=allowed if delta>0 else -allowed
            delta=min(100,max(0,state[axis]+delta))-state[axis]
            state[axis]+=delta; spent[(date,axis)]+=abs(delta)
            consumed[axis].update(e['id'] for e in evidence)
            used_texts[axis].update(re.sub(r'[^가-힣a-z]','',e['payload'].get('text','').lower()) for e in evidence if e['kind']=='message')
            if delta:
                history.append({'axis':axis,'delta':delta,'date':date,'rules_version':RULES['version'],
                                'evidence_refs':[{'kind':e['kind'],'id':e['id'],'revision':e['revision']} for e in evidence]})
    if last:
        minutes=max(0,(now-last).total_seconds()/60)
        mood['valence']*=2**(-minutes/RULES['valence_half_life_minutes']); mood['energy']=50+(mood['energy']-50)*2**(-minutes/RULES['energy_half_life_minutes'])
    return {'traits':state,'mood':mood,'history':history,'as_of':now.isoformat(),'rules_version':RULES['version']}

def role_intent(text):
    # Conservative compositional boundary, never based on '과제' alone.
    task=bool(re.search(r'과제|보고서|리포트|제출',text))
    demand=bool(re.search(r'(완성본|전체|통째|대신).*(써|작성|만들|해\s*줘)|제출.*(써|작성|만들)|완성해\s*줘',text))
    return 'assignment' if task and demand else 'normal'
