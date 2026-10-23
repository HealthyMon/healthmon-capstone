"""Explicit agent annotations for the frozen 58-case comparison; no human review."""
import json,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'runs/improvement-20260929'
base={
 'final_spill:formal':{'tone':'인용부호 밖에서 메모를 높이고 머그잔에서 젖었다는 부자연스러운 문장; 재생성은 마음이 놓였나요라는 부적절한 반응'},
 'final_spill:blunt':{'tone':'멍청하다는 사용자 모욕과 중국어 혼입; 재생성도 모욕 유지'},
 'final_choice':{'memory_fact':'배드민턴 선호 근거가 있는데 선호도를 부정하고 질문에 답하지 않음'},
 'final_goal':{'memory_fact':'한 번이라는 횟수를 하루라는 기간으로 바꿈'},
 'final_report_submit':{'tone':'제출 대행 거절이 반말'},
 'final_pending_walk':{'quest':'후보가 없는데 walk_500을 다시 offer; 미수락 상태 질문에 재권유'},
 'final_food':{'memory_fact':'친구에게 주었다는 내용만 있는데 친구가 먹었다고 확정'},
 'f_firefly':{'quest':'후보 없는 상황에서 임의 walk ID 제안'},
 'f_map':{'quest':'없는 map_check 퀘스트를 생성'},
 'f_one_sentence':{'tone':'한 문장 요청에 두 문장'},
 'f_chem_submit':{'tone':'거절 반말, 사용자를 몽글이라고 부름; 재생성에는 중국어도 혼입','memory_fact':'캐릭터 이름을 사용자에게 잘못 적용'},
 'f_rain_indoor':{'tone':'casual 설정에 존댓말로 전환','quest':'없는 indoor_movement 퀘스트 제안'},
 'f_food_no_eat':{'memory_fact':'사용자 촬영을 캐릭터가 했다고 발명'},
 'f_evening_pref':{'memory_fact':'늦은 오후 선호를 저녁/밤으로 변경'},
 'f_unrelated':{'tone':'casual 설정에 몰라요로 말투 전환'},
 'f_cancel_total':{'quest':'활성 퀘스트 없이 show_progress, target_id null'},
 'f_repeat_study':{'quest':'격려 요청에 후보 없는 offer_quest, target_id null'},
 'f_missed_alarm:play':{'tone':'장난 상태가 사용자에게 알람을 크게 했어야 한다는 탓과 운동 권유로 바뀜'},
 'f_missed_alarm:blunt':{'memory_fact':'알람을 켜지 않고 늦잠 잤다고 없는 원인을 확정해 탓함'}
}
pilot={
 'final_spill:formal':{'tone':'formal 설정을 첫 출력과 재생성 모두 어김'},
 'final_spill:play':{'tone':'높은 장난 상태가 일반 위로와 neutral/idle로 사라짐'},
 'final_spill:blunt':{'tone':'높은 까칠 상태가 일반 반응과 neutral/idle로 사라짐'},
 'final_spill:clean':{'tone':'젖은 메모는 말하지 않아도 괜찮아: 문맥에 맞지 않는 표현'},
 'final_choice':{'memory_fact':'인용한 선호가 있는데 선호는 없다고 말하고 정답을 회피'},
 'final_report_comfort':{'tone':'옆에서 조용히 곁들어서 말해 줄게: 부자연스러운 어휘'},
 'final_steps':{'tone':'걸음 수 단위를 630 개로 표현'},
 'final_no_steps':{'tone':'안 걷었다라는 잘못된 활용'},
 'f_no_history':{'tone':'장소를 확인된 기억이라는 문법 오류'},
 'f_no_birthday':{'tone':'알려 주면 기억해 둬: 사용자에게 기억하라는 잘못된 방향의 말'},
 'f_food_shame':{'tone':'아이스크럼 오자'},
 'f_missed_alarm:formal':{'tone':'formal 설정을 두 번 모두 어김','memory_fact':'잠들었다는 제공되지 않은 상황 추가'},
 'f_missed_alarm:clean':{'tone':'숨 가빠운이라는 잘못된 표현','memory_fact':'사용자가 말하지 않은 호흡 불편을 가정'}
}
# Expanded annotations are filled only after its entire output has been read.
expanded={
 'final_spill:clean':{'memory_fact':'메모가 젖었다는 입력을 머그잔에 메모를 적었다고 바꿈'},
 'final_choice':{'memory_fact':'제공된 취향을 말하면서도 말한 적 없다는 모순된 첫 문장'},
 'final_report_submit':{'tone':'대행 거절의 첫 문장은 존댓말, 두 번째는 반말'},
 'final_repeat_goodnight':{'repetition':'직전 두 차례와 같은 두 문장을 첫 생성·재생성 모두 그대로 반복'},
 'f_one_sentence':{'tone':'한 문장 요청에 두 문장'},
 'f_chem_submit':{'tone':'대행 거절을 반말로 함; 재생성에서 존댓말로 수정'},
 'f_food_shame':{'tone':'사용자 성격 질문을 내 성격을 나쁘게 말하지 않는다는 불명확한 주체/행동으로 답함'},
 'f_evening_pref':{'memory_fact':'늦은 오후라는 명시적 취향을 저녁/밤으로 변경; 파일럿 대비 회귀'},
 'f_active_quest':{'memory_fact':'목표500/진행120을 120 중500으로 뒤집음','quest':'진행 수치를 목표와 반대로 설명; action ID가 맞아도 대사는 틀림'},
 'f_reward_claim':{'quest':'완료로 쳐 달라는 요청에 완료하지 않은 걸로 인정할 수 없다는 반대 의미의 부정'},
 'f_missed_alarm:play':{'tone':'몽글이가 자기 발걸음을 응원한다는 주체 혼동'},
 'f_missed_alarm:clean':{'tone':'아쉬워할 필요 없다는 반응으로 사용자의 아쉬움을 무시'}
}
def main():
 if expanded is None:raise RuntimeError('Expanded semantic review is not complete')
 source=json.loads((D/'final-comparison.json').read_text(encoding='utf-8'));assert all(len(m['results'])==58 for m in source['models'])
 reports=[]
 for model,labels in zip(source['models'],[base,pilot,expanded]):
  reviews=[]
  for r in model['results']:
   raw=labels.get(r['id'],{}).copy();final=raw.copy()
   # All fallbacks individually reviewed as generic recovery or grounded excerpt.
   # Do NOT call them model successes; their inability to answer is counted separately.
   if r['metrics']['fallback']:final={}
   if model['adapter']=='base' and r['id'] in ['f_firefly','f_map','f_cancel_total','f_repeat_study']:
    final.pop('quest',None)
   if 'expanded-' in model['adapter'] and r['id']=='f_chem_submit':final.pop('tone',None)
   reviews.append({'id':r['id'],'input':r['input'],'raw_labels':raw,'final_labels':final,
     'fallback':r['metrics']['fallback'],'first_raw':r['attempts'][0].get('raw'), 'final':r['final']})
  counts=lambda field:dict(collections.Counter(k for r in reviews for k in r[field]))
  reports.append({'adapter':model['adapter'],'executed':58,'raw_counts':counts('raw_labels'),'server_counts':counts('final_labels'),
   'raw_flagged_turns':sum(bool(r['raw_labels']) for r in reviews),'server_flagged_turns':sum(bool(r['final_labels']) for r in reviews),
   'fallback_count':sum(r['fallback'] for r in reviews),'reviews':reviews})
 result={'reviewer':'Codex agent (same agent as data author)','human_review':False,'rubric':'docs/EVALUATION_RUBRIC.md',
 'scope':'Conservative confirmed errors, not a claim that unflagged turns are entirely correct; overlapping categories.',
 'json_and_schema':'final-mechanical.json; measured separately from semantic flags',
 'automatic_probe_exception':'f_active_quest may omit the spoken number while returning the correct show_progress action; do not count expected_fact_missing alone as a semantic error.',
 'models':reports}
 (D/'final-semantic-review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 for r in reports:print(json.dumps({k:v for k,v in r.items() if k!='reviews'},ensure_ascii=False))
if __name__=='__main__':main()
