# 일일·대화 퀘스트와 누적 말투 적응

2026-10-04. Unity 연결을 앞두고 Character Lab의 실제 테스트 상태/별도 테스트 DB에서 퀘스트와 성격의 행동을 구현했다. Unity 게임 API·운영 PostgreSQL에는 아직 적용하지 않았으며 서버는 꺼둔 상태다.

## 구현한 행동

### 일일 6000보

- 기본 세션에는 오늘의 **6000보 걷기**가 `created`로 존재한다. 기본 상태를 조회하는 것만으로 DB를 쓰지는 않는다.
- 가상 날짜 진행 또는 `/quest/tick`에서 날짜별로 한 번 생성한다. 완료·거절한 퀘스트를 같은 날 재생성하지 않는다.
- 수락 전후를 포함해 해당 날짜의 **검증된 걷기 증가분**을 합산한다. 자기보고·다른 날짜·다른 운동·중복 event는 완료 증거가 아니다.
- 수락하고 진행 상태로 전환한 뒤 검증된6000보가 있어야 완료한다. 5999보와 미검증 추가1보는 완료되지 않는다.
- 다음 날짜에 미수락 퀘스트는 만료되고, 수락한 미완료 퀘스트는 실패한다. 보상을 지급하지 않으며 실패 Mood는 날짜별 상한 아래 한 번 반영한다. 계획 없는 미수행으로 운동 스탯을 감소시키지는 않는다.
- 일일 목표6000은 사용자가 지정했다. 보상10 EXP와 자동 만료 정책은 명시적인 provisional 설정이다.

### 대화 중 100걸음 같은 작은 퀘스트

`현재 캐릭터 응답 생성`에서 유효한 `offer_quest`를 받으면 `/quest/offer`를 거쳐 실제 mini 퀘스트 인스턴스를 생성한다. dry-run에서는 현재 테스트 미리보기에 반영하고, DB 모드에서는 목표·기한을 확인한 뒤 별도 테스트 DB에 확정한다. 기존 A/B 비교는 가상 성격을 비교하므로 현재 상태와 다른 Case의 제안은 곧바로 실행하지 않는다.

```text
현재 검증된 상태로 Qwen 응답
→ action=offer_quest, target_id=walk_100
→ 서명·현재 상태·기록·목표·규칙 버전 검사
→ mini:walk_100:날짜 인스턴스 생성
→ 사용자 수락
→ 수락 후 해당 인스턴스에 연결된 검증 기록
→ 완료와 보상 한 번
```

대사만으로 퀘스트를 추론하지 않는다. 서버 카탈로그의 목표·단위·보상으로 생성하며 모델이 다른 값으로 바꿀 수 없다. `100걸음` 대사와 `2분 스트레칭` action, `500보` 대사와 `100보` action은 생성 시 차단한다. 여러 목표 숫자가 섞여 모호한 경우에도 검수·재생성을 안내한다. 숫자를 생략한 대사에서는 검증된 action의 목표를 사용한다. 일반적인 의미 오류 전체를 탐지하는 검증기는 아니다.

mini100과 daily6000은 다른 인스턴스다. 같은 실제100보는 오늘의 일일 진행에도 들어가지만 mini를 끝냈다고 daily가 완료되지는 않는다. 두 퀘스트의 보상 정책은 분리되어 있다.

반환 예시(계약 예시이며 새 Qwen 생성 샘플은 아님):

```json
{
  "quest_id": "mini:walk_100:2026-10-04",
  "catalog_id": "walk_100",
  "quest_scope": "mini",
  "title": "가볍게 100걸음",
  "status": "created",
  "goal": {"activity": "walk", "target": 100, "unit": "step"},
  "progress": {"verified_value": 0, "target_value": 100, "ratio": 0},
  "due_date": "2026-10-04",
  "reward": {"exp": 5, "paid": false},
  "can_accept": true,
  "can_complete": false
}
```

`execution.quest_instance_id`는 수락·기록 연결에 사용하고 `catalog_id`는 목표 종류를 표시한다. 목표와 진행 수치는 대사에서 다시 추출하지 않는다.

## 성격과 말투

핵심3축은 그대로 유지한다. Activity는 실제 활동, Affinity는 관계, Initiative는 제안과 수행 이력으로 주간 계산한다. 새 표현축 `roughness`, `bluntness`, `courtesy`의 기본값10/20/60은 기존 게임 규칙에서 재사용했다. 별도 Lab JSON 상태에 보관하므로 운영 컬럼을 변경하지 않았다.

| 상태 | 연결된 응답 정책 |
|---|---|
| 활동성·주도성 높음 | 활동 관련 상황에서 운동 후보 하나를 선택적으로 제안 |
| 활동성 또는 주도성 낮음 | 듣기·휴식 우선, 새 퀘스트 후보 억제 |
| 사용자 휴식 요청 또는 부정 Mood | 휴식 우선, 제안 강도 감소 |
| 거친 말투 누적 | 툴툴대는 구어체 → 기존 sassy 목소리와 직설적인 구조 |
| 공손한 말투 누적 | 거친 표현·직설성 감소, 배려 표현 회복 |

한 번의 욕설로 즉시 성격을 바꾸지 않는다. 신뢰0.6 이상, 서로 다른 원문3개 이상, 두 날짜 이상, 해당 표현이 절반 이상인 주간 증거가 필요하다. 인용·모델 변경 지시·중복 붙여넣기·낮은 신뢰도는 제외한다. 욕설 자체를 Affinity 감소로 해석하지 않는다.

현재 provisional 주간 증감은 거친 표현 `+5/+4/-3`, 공손한 표현 `-4/-3/+5`이다. Roughness35부터 약간 툴툴대는 지침,60부터 기존 sassy 목소리를 사용한다. 테스트에서는 초기10에서10주 누적으로60이 되어 sassy가 선택됐고, 공손한3주를 적용해48로 회복되며 기본 목소리로 돌아왔다. 이는 규칙·프롬프트 검사이며 새 실제 Qwen 말투 성공률을 뜻하지 않는다.

놀림을 그만하라는 요청과 힘든 고백에서는 해당 응답의 빈정거림을 중지한다. 운동을 싫어하지 않는다는 부정문과 실제 거절을 구분한다. 같은 성격이어도 현재 기분·사용자 의사에 따라 응답 정책은 달라진다.

## 검증

- 관련 Python **339 passed**. 신규 기능과 기존 Persona Lab·생활 기록·검수·규칙 회귀 포함. 기존 의존성 warning3개.
- 기존 Node 통신 검사 **5 passed**, Character Lab JS 문법 검사 통과.
- 유한 CPU 행동 시나리오 **83/83**. preset은14개로 확장.
- 생성·수락·검증·완료·중복 보상·날짜별 생성·만료·Mood 상한·5999/6000 경계·mini/daily 독립을 실제 순수 엔진으로 검사했다.
- HTTP 검사는 임시 SQLite와 제어된 모델 fixture로 실행했다. 원본 테스트 DB의 검사 전후 해시는 동일하다. fixture를 실제 Qwen 성능으로 집계하지 않는다.
- 서명/목표/ID 조작, dummy/fallback 실행, 현재 상태와 다른 A/B 제안, 오래된 기록·revision은 차단했다.
- 현재 상태 응답은 한 번만 생성하고 결과에 `single_state`를 표시한다. 기존 A/B 반환 구조는 호환된다.
- 긴 누적 이력은 모델에 최신 사실6개와 현재 상태로 투영하고 전체 audit는 보관한다. system에 있는 말투 지침을 context에 중복 넣지 않는다. 로컬 실제 tokenizer로 운동/거친말/회복 preset의 입력3433/3528/2946 token을 확인해 기존4096 한도 안에 들었다. 더 긴 사용자 입력/기억은 기존 예산 검사 대상이다.

증거: `runs/character-lab/quest-personality-regression-final.log`, `quest-personality-behavior-final.json`, `quest-personality-token-budget-final.json`.

재현:

```powershell
Set-Location E:\qwen-llm
.venv\Scripts\python.exe -m pytest tests/test_character_lab_gameplay.py tests/test_character_lab_quests.py tests/test_character_lab_personality.py tests/test_character_lab_growth_behavior.py tests/test_character_lab_offer_api.py -q
.venv\Scripts\python.exe scripts\verify_character_behavior.py --output runs\character-lab\new-gameplay-check.json
```

## 이번에 실행하지 않은 부분

GPU를 비워두라는 요청을 유지해 새 Qwen 생성과 브라우저 서버 실행은 하지 않았다. 새 프롬프트에서 활동적/소극적/툴툴대는/회복한 성격을 실제 모델로 비교하는 평가는 남아 있다. 모델·LoRA 재학습, 외부 다운로드, 대량 학습 데이터 생성은 하지 않았다.

운영용 실시간 스케줄러와 Unity DTO·센서·Animator 연결은 별도 작업이다. 현재 날짜 처리는 `virtual_test_date`이며 게임 서버가 접속/시간 tick을 호출하도록 나중에 연결해야 한다. 센서가 누적 걸음값을 보내면 증가분/수정 revision 계약부터 정해야 한다. 지금 `actual`은 증가분이므로 누적 값을 여러 새 이벤트로 반복 보내면 잘못 합산된다.

수정/신규 핵심: `src/character_lab_quests.py`, `src/character_lab_personality.py`, `src/character_lab_schema.py`, `src/character_lab_engine.py`, `src/character_lab_models.py`, `src/character_lab_api.py`, `src/persona_runtime.py`의 Lab 전용 프롬프트 투영, `src/character_lab_presets.py`, `web/persona-lab/character.js`, 두 신규 정책 JSON, 테스트5개 파일. 원래 Quest 카탈로그와 legacy voice 설정은 유지했다.
