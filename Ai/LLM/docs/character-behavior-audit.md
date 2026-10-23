# Character Lab 행동·대화·Unity 연동 검증

> 이 문서는 후속 구현 전의 감사 기록이다. 일일6000보·실제mini퀘스트 생성·만료·누적 말투 적응의 최신 결과는 [후속 구현 보고서](character-quests-personality.md)를 참조한다.

2026-10-04. 사용자가 요청한 시간 기반 퀘스트, 성격별 대화, 성장 전후 대화, Unity 반환 형식을 검사했다. 게임용 GPU를 비워둔 기존 요청을 유지해 서버와 Qwen을 새로 실행하지 않았다. 실제 답변 평가는 이미 보존된 Qwen 원문을 사용하며, CPU 계약·규칙 검사 및 dummy 통신 검사를 별도로 표시한다. 재학습과 학습 데이터 생성·검수 저장을 실행하지 않았다.

## 결론

| 질문 | 판정 | 근거와 한계 |
|---|---|---|
| 시간이 지나면 퀘스트가 자동으로 나오는가? | 게임 연결 미완성 | Character Lab 시간만 진행하면 퀘스트 생성 0개. 기존 시간 시뮬레이션은 가상 추천을 생성하지만 실제 타이머·게임 DB 저장·Unity 전달 경로가 아니다. |
| 성격마다 대화가 바뀌는가? | 차이 일부 확인, 품질 안정성 부족 | 높은 활동성·주도성은 작은 걷기 제안, 낮은 값은 휴식 응답 사례가 있다. 각 축의 독립적인 말투 효과는 충분히 입증되지 않았다. |
| 성격이 성장하면 답변도 바뀌는가? | 상태→프롬프트 연결 확인, 체감 변화 미보장 | 실제 주간 계산 결과가 Responder에 전달된다. 50→53은 연속 제어값만 조금 바뀌며 같은 단계·문장 지침을 유지한다. |
| Unity가 사용할 반환값인가? | 표현 필드 사용 가능, 전체 연동 미완성 | speech/emotion/animation/action은 검증한다. 그러나 8001 Lab A/B 결과와 8000 게임 API 단일 응답·상태 DTO가 다르다. |

## 이번에 새로 실행한 검사

- 관련 회귀 테스트 **159 passed**, 기존 의존성 deprecation warning 3개. PostgreSQL 통합 전체 suite를 이번에 다시 실행한 수치는 아니다.
- 신규 유한 행동 검증기 **80/80** 기대 동작 확인. 12 preset, 시간 1/7/30/366일, 3축×9값 상태 전달, 경계 정책, 실제 주간 변화 전달, 거절, 응답 계약·고장 주입, HTTP 422/409, 중복 성장 방지, DB 격리를 포함한다.
- 별도 읽기 감사의 48개 프로필 검사 및 16개 계약 프로브도 시행했다. 서로 겹치는 검사는 합산해 전체 테스트 수로 제시하지 않는다.
- `runs/persona-lab/test-characters.sqlite3` 파일의 검사 전후 SHA-256이 동일하다. API 저장 검사는 폐기되는 임시 SQLite에만 실행했고, Qwen 로더 및 PostgreSQL 연결은 호출 시 오류를 내도록 막았다.
- 자동 시간 퀘스트 생성과 만료 처리의 **부재**는 별도 observation이다. 검증기의 통과 수는 해당 기능 구현 완료를 의미하지 않는다.

재현:

```powershell
Set-Location E:\qwen-llm
.venv\Scripts\python.exe scripts\verify_character_behavior.py --output runs\character-lab\new-behavior-audit.json
.venv\Scripts\python.exe -m pytest tests/test_character_lab.py tests/test_persona_style_quests.py tests/test_persona_engine.py tests/test_persona_review.py tests/test_persona_comparison.py tests/test_agent.py tests/test_guard_scope.py tests/test_rules.py -q
```

검증기는 기존 파일을 덮어쓰지 않으므로 새 출력 경로를 사용한다. GPU 서버를 실행하지 않아도 된다.

## 1. 시간과 퀘스트

`src/character_lab_engine.py`의 `time.advance`는 가상 날짜와 Mood decay를 처리한다. `all_weekly`는 주간 성격 계산을 추가한다. 두 경로에서 새 퀘스트를 생성하거나 만료된 퀘스트를 닫지는 않는다.

- Initiative 25/50/80과 시간 7일: 생성된 퀘스트 0개.
- Initiative<40: Responder 호출 시 후보 제거. 40 이상: 상태·기록에 따라 후보 계산 가능.
- 현재 메시지의 운동 거절: 운동 후보 제외. 식사 후보는 남을 수 있다.
- 걷기 제안 거절 후 2시간: 걷기 후보 제외. 기존 72시간 쿨다운이 끝나면 다시 가능.
- 활성 동일 활동 및 주간 반복 한도: 재추천 제외.
- 10월 4일 마감인 수락 퀘스트를 7일 진행: 10월 11일에도 `accepted` 상태. 이후 진행은 마감 오류이고 선택기는 같은 활동을 계속 진행 중으로 취급한다. 자동 만료/실패 정책의 연결이 필요하다.

기존 상단 **03 시간 시뮬레이션**은 `src/persona_lab.py`의 batch 안에서 하루마다 합성 `quest_proposed`를 생성한다. 1/7/30일 실행에서 1/7/30개의 제안을 확인했다. `production_write=false`, `model_generated=false`다. 이 기능은 Character Lab 06 가상 날짜 및 게임 실시간 서비스와 분리되어 있다.

게임 API는 확인된 활동 입력을 받으면 pending suggestion job을 만들고, 별도 `POST /pets/{pet}/activity-suggestions/{event_id}?revision=...` 또는 채팅에서 유효한 제안이 나올 때 offer를 저장한다. 현재 자동 worker/timer/push와 Unity의 해당 suggestion 호출이 없다.

## 2. 성격과 대화

세 질문을 구분해야 한다. **서로 다른 고정 성격을 주었을 때의 차이**, **행동 때문에 성격 수치가 실제 바뀌는지**, **변한 수치가 다음 대사에서 체감되는지**는 서로 다른 검사다.

| 실제 상태 변경 | Responder 변화 |
|---|---|
| Activity 50→53 | encouragement .500→.506, 문장 지침과 기본 후보는 동일 |
| Affinity 50→53 | warmth .500→.512, 문장 지침과 구조는 동일 |
| Initiative 50→53 | initiative .50→.53, medium 정책 동일 |
| Activity 59→60 | high 지침 및 기본 후보 변경 |
| Affinity 59→60 | high 지침 및 기본 후보 변경 |
| Affinity 62→63 | warmth .698→.702, 공감→답→함께할 선택 구조 |
| Initiative 39→40 | low→medium, 후보 제공 시작 |
| Initiative 69→70 | medium→high, 구체적인 선택을 먼저 제안하는 지침 |

7일 운동 성공은 Activity 50→53, 매일 긍정 대화는 Affinity 50→53, 반복 제안 거절은 Initiative 50→48이 된다. 계산된 값을 다음 응답 context에서 그대로 확인했다. 같은 seed를 써도 한 주의 작은 변화가 눈에 띄는 대사 차이를 보장하지는 않는다.

매주 +3을 계속 받는 가정에서 초기50→Activity high60은 4주, Affinity의 따뜻한 구조63은 5주, Initiative high70은 7주가 걸린다. 이는 임계값 계산이며 모델의 표현 품질에 대한 보장은 아니다.

추가 제한:

- Lab은 이전 style stage를 전달하지 않아 legacy hysteresis가 유지되지 않는다.
- 독립 Initiative가 legacy Activity/Confidence 혼합 initiative 값을 덮어쓴다. Activity는 encouragement·지침·후보에 반영된다.
- 이 덮어쓰기는 negative Mood의 legacy initiative 감소도 덮어쓴다. 휴식 지침과 encouragement 감소는 유지된다.
- legacy short-term energy=60, motivation=50, stress=0을 고정 투영한다. 실제 피로 변화까지 검증한 것으로 해석하면 안 된다.

## 3. 보존된 실제 Qwen 결과

현재 Character Lab `qwen-real-v2.json`은 분석 기대값 6/6, A/B 2쌍/4응답이다. 최종 fallback은 0이지만 최초 유효 출력은 3/4다. 한 응답은 기억 ID를 Quest target으로 사용했다가 재시도에서 수정됐다.

- 높은 Activity85/Initiative80: “가볍게 100걸음을 해보자”와 `offer_quest/walk_100`.
- 낮은 Activity25/Initiative25: “잠깐 자리에 앉아 숨을 세 번 천천히 느껴 봐”와 `none/null`.
- “오늘 운동하기 싫어”에는 양쪽 모두 휴식을 수용하고 `none/null`.
- 별도 생활 기록 포함 브라우저 실험의 낮은 주도성 응답은 `offer_quest/null`을 두 번 출력해 fallback으로 차단됐다. 카탈로그에 없는 3분 걷기 대사도 있었다.

과거 Persona Lab 36쌍/72응답은 **별도의 legacy 평가**다. 최초 유효67, 재시도 성공4, fallback1이었으나 최종 대사·액션 불일치, 후보 오해, 날짜 왜곡 등 의미 오류7건이 있었다. `docs/persona-model-review.md`의 기존 결론도 네 축의 말투를 안정적으로 구분한다는 판정은 유보한다. 높은 JSON 성공률을 높은 대화 품질로 바꾸어 해석하지 않는다.

과거 14일 성장 비교도 상태·기록·Mood·후보가 함께 바뀌었다. 3 seed 중2에서 식사 기록→자전거 목표로 대사와 action이 함께 바뀌었지만, 다른1에서는 후보가 있는데 없다고 답했다. 따라서 이것만으로 성격 수치의 독립적인 효과를 증명할 수 없다.

## 4. Unity 반환 계약

`src/contracts.py`의 ModelOutput에는 `speech`, `emotion`, `animation`, `action`, `memory_ids`, `personality_update`가 있다. enum과 길이, action-target 관계를 검증한다. `src/agent.py`는 등록된 후보/활성 퀘스트 ID와 유효 Memory ID만 허용하고 모델의 성격·보상 확정을 차단한다.

잘못된 enum, 누락 필드, 가짜/빈/null Quest ID, 잘못된 memory, extra field, 과도한 대사, 모델의 성격 변경은 거부됐다. null target을 두 번 출력하는 고장 주입에서는 `fallback=true`, `neutral/idle`, `action=none/target_id=null`의 안전한 응답이 반환됐다. 이 결과는 제어된 테스트 fixture이며 실제 Qwen 성공 샘플이 아니다.

게임 채팅은 `src/app.py`에서 다음 envelope를 반환한다.

```text
schema_version, request_id, response,
state_used, state_after, state_version,
execution, metrics
```

Unity 표시에는 `response.speech/emotion/animation`을 사용하고, 제안 수락에는 **서버가 저장한 `execution.offer_id`**를 사용해야 한다. `response.action.target_id`는 카탈로그 목표 ID여서 수락할 offer ID와 다르다. 완료·진행률·보상은 구조화된 서버 상태에서 읽는다.

현재 연결 누락:

1. Unity 기본 주소는 8000, Lab은 8001 개발 전용이다.
2. 기존 `integrations/unity/HealthmonDtos.cs`의 Traits는 sociability/initiative/playfulness/courtesy/bluntness/roughness/bond이다. 새 activity/affection/initiative 및 운동·영양·EXP·진화 CharacterState와 다르다.
3. Lab 결과는 `results[0].a/b.output`의 비교 구조다. Unity 기존 단일 ChatResult로 그대로 읽을 수 없다.
4. 채팅 OpenAPI 200 전체 반환 schema가 `{}`다. 모델 JSON은 strict지만 HTTP 전체 envelope에 `response_model`이 없어 필드 누락 방지와 DTO 자동 생성 계약은 부족하다.
5. 실제 Unity 프로젝트·Editor가 저장소에 없어 Animator 연결 및 C# 플랫폼 빌드는 실행하지 않았다.

## 5. 이번에 수정한 오류

완료된 식사 퀘스트가 Quest selector에서 계속 활성으로 남는 증거 투영 오류를 수정했다. `history_projection`이 기존에는 완료 증거에 운동 기록만 연결해 식사 evidence가 비어 있었다.

이제 수락 이후 유효 식사 기록을 progress/complete evidence에 연결하고, 다른 퀘스트에서 소비한 증거는 제외한다. 기존 카탈로그의 음식명·새 음식 검증을 우회하지 않으며 운동 증거 분기는 보존했다. 정상 음식 완료, 새 음식 완료, 기존 음식의 신규성 거부, 빈 음식명의 거부 4가지 회귀 검사를 추가했다. 수락 전 기록과 unknown 분석 제외 및 입력 비변경성도 확인한다.

변경: `src/character_lab_models.py`, `tests/test_character_lab.py`. 검사 도구: `scripts/verify_character_behavior.py`. 신규 보고: 이 문서. 게임 API·Unity DTO·운영 DB·모델 설정은 변경하지 않았다.

## 6. 게임 연동 완료까지 필요한 작업

1. **서버가 저장하는 CharacterState 통합:** 별도 Lab 상태를 게임 캐릭터 상태에 적용할 공식 schema/migration/adapter 및 Unity DTO 계약을 정한다.
2. **시간 처리:** 접속 또는 주기 tick에서 경과 날짜, 주간 성격, Mood, 퀘스트 만료를 처리한다. 자동 실패/만료와 제안 빈도는 정책으로 명시하고 중복 방지를 적용한다.
3. **Quest 전달:** 후보·거절·활성 목표·쿨다운을 확인해 offer를 저장하고 Unity 조회/폴링/푸시로 전달한다. Qwen은 제안 대사를 만들고, 실제 생성·수락·보상은 서버가 확정한다.
4. **단일 HTTP 반환 계약:** 상태 버전, 서버 실행 결과, 캐릭터 대사/표정/모션을 typed response로 선언하고 C# DTO와 end-to-end 테스트한다.
5. **실제 모델 평가:** 핵심 축을 하나씩 독립 변경하고 같은 기억·Mood·후보·seed로 비교한다. 작은 성장과 임계값 통과를 따로 평가하며, 최초 JSON/재시도/fallback 및 목표와 대사의 일치를 분리 집계한다.

증거 파일:

- `runs/character-lab/behavior-regression-20261004.log`: 최종159 회귀 검사.
- `runs/character-lab/behavior-audit-20261004-final.json`: 최종80 CPU 행동 검사와 관찰.
- `runs/character-lab/qwen-real-v2.json`: 기존 실제 Qwen Analyzer/Responder 원문.
- `runs/character-lab/browser-low-trace.json`: 기존 실제 Qwen 실패 원문.
- `runs/character-lab/recorded-qwen-behavior-20261004.json`: 보존된 Qwen 출력의 CPU 계약 재검증.

서버는 종료 상태로 유지한다. 이번 결과는 테스트 도구와 연동 부품의 검증이며 실제 Unity 게임 연동 완료 판정은 아니다.
