# Character Lab 구현·검증 보고서

2026-10-04, `E:\qwen-llm`. 기존 Persona Lab에 관리자·개발·테스트용 Character Lab을 통합했다. 접속 주소는 **http://127.0.0.1:8001/** 이며 현재 서버는 기존 Qwen/epoch 1 LoRA를 로드한 상태다.

**최종 자동 테스트: 302 passed.** 실제 Qwen 분석 재검사 6/6, 기본 응답 A/B 2쌍은 fallback 0건이었다. 생활 기록을 포함한 추가 브라우저 A/B에서는 B가 잘못된 quest action을 두 번 출력해 fallback으로 차단됐다. 이 원문과 수정 응답도 보존했다. 원본 학습 데이터·기존 테스트·기존 모델 설정·checkpoint는 보존했고 재학습, 외부 다운로드, 대량 데이터 생성은 수행하지 않았다.

## 1. 재사용한 기존 구현

- `src/persona_lab.py`: 로컬 FastAPI, production 차단, loopback/Origin/Host 검사, 정적 UI, 기존 말투·생활·시간 시뮬레이션.
- `src/persona_store.py`: 기존 별도 SQLite 파일 경로. 원래 `lab_characters/lab_events/lab_snapshots`를 변경하거나 변환하지 않고 신규 테이블을 추가했다.
- `src/persona_runtime.py`: 기존 offline Qwen/LoRA 로딩, GPU lock, 동일 seed/generation 설정 A/B, 실제 prompt/raw attempts/repair/fallback 추적.
- `src/agent.py`, `src/contracts.py`: 기존 응답 계약과 사실·Memory·Quest 검증. 잘못된 `offer_quest target_id=null`도 여기서 차단됐다.
- `src/persona_style.py`, `src/persona_quests.py`, `config/quest_catalog.json`: 기존 스타일 계산, 검증된 기록 기반 퀘스트 선정·재제안 대기·거절·난이도 정책. Character Lab의 Initiative 정책을 그 위에 적용한다.
- `src/persona_comparison.py`: 기존 A/B 응답 차이·검수 단서. 단서 계산은 의미 정확도 자동 인증이 아니다.
- 기존 Qwen assistant-only ChatML 인코딩을 `src/chatml.py`로 분리해 기존 학습 코드와 신규 변환 명령에서 함께 사용한다. 학습은 실행하지 않았다.

## 2. 추가·수정한 파일

신규 구현:

| 파일 | 역할 |
|---|---|
| `config/character_lab_rules.yaml` | 규칙, 출처, 임시값과 경계값 |
| `src/character_lab_schema.py` | 상태·이벤트·분석 schema, clamp, JSON 서명 정규화 |
| `src/character_lab_engine.py` | 순수 backend 성장·주간 성격·Mood·시간·EXP·진화 규칙 |
| `src/character_lab_models.py` | ConversationAnalyzer/FoodAnalyzer/PersonaResponder 분리, 기존 기록·Quest 어댑터 |
| `src/character_lab_store.py` | 별도 test namespace, 원자적 commit·revision·검수·Export |
| `src/character_lab_api.py` | Character Lab API와 수정 불가능한 원문 draft 서명 |
| `src/character_lab_presets.py` | 12개 명시적 합성 preset |
| `src/persona_generation.py` | 기존 Generation/Memory 계약을 공통 모듈로 이동 |
| `src/chatml.py` | 기존 assistant-only 인코딩 공통 함수 |
| `web/persona-lab/character.js`, `character.css` | 7개 영역 UI, 저장 전 before/after, 분석·응답 검수 |
| `migrations/character_lab/001_up.sql`, `001_down.sql` | 별도 SQLite migration과 테스트용 rollback |
| `tests/test_character_lab.py` | 54개 규칙·API·격리·migration·검수·변환 검사 |
| `scripts/convert_character_dataset.py` | 두 task의 JSONL을 독립 ChatML로 변환 |
| `scripts/verify_character_lab_real.py` | 유한한 실제 Qwen 검사, 원문과 실패 기록 |
| `scripts/verify_character_lab_regression.py` | 별도 PostgreSQL DB에서 기존 전체 테스트 실행·원본 DB 해시 비교 |
| `docs/character-lab.md` | 이 보고서 |

수정: `src/persona_lab.py`, `web/persona-lab/index.html`, `web/persona-lab/app.js`, `scripts/train_lora.py`(공통 인코딩 함수 호출만), `requirements.txt`(이미 설치된 PyYAML 명시), `START_HERE.md`.

검증 산출물은 `runs/character-lab/`에 저장했다. 기존 데이터 폴더에 새 학습 파일을 쓰지 않았다.

## 3. DB와 migration

저장 위치: `runs/persona-lab/test-characters.sqlite3`의 신규 테이블만 사용한다.

| 테이블 | 저장 항목 |
|---|---|
| `character_lab_sessions` | `clab-` ID, 고정 `character-lab-test` namespace, 전체 가상 상태·이력, Initiative, revision |
| `character_lab_events` | session/event PK, before/after·source·규칙·시간·dry-run 로그 |
| `character_lab_reviews` | Analyzer/Response 구분, 원문 prediction/context, correction, status, reviewer note, created/reviewed 시각, model/prompt identifier, revision |
| `character_lab_schema_version` | migration version 1 |

신규 저장을 명시적으로 요청할 때만 migration을 적용한다. dry-run은 migration/INSERT/UPDATE를 실행하지 않는다. 저장된 세션을 읽을 때는 SQLite `mode=ro`를 사용한다. commit은 `BEGIN IMMEDIATE`와 `expected_revision`으로 충돌을 방지하고, 이벤트 ID 충돌 시 전체 batch를 rollback한다.

실제 SQLite 임시 DB에서 **적용 → rollback → 재적용 → 중복 적용**을 검사했으며, 기존 sentinel 테이블이 유지됐다. down migration은 검증용 임시 DB에만 실행했다. 기존 PostgreSQL migration 파일과 운영 테이블은 변경하지 않았다.

## 4. API 목록·계약

모두 기존 Persona Lab의 접근 middleware 아래에 있다. 기본 요청은 `dry_run=true`다.

| 경로 (`/dev/character-lab` 뒤) | Method | 기능 |
|---|---|---|
| `/state` | GET | 기본 상태·규칙·필드 alias 또는 선택 test session 재조회 |
| `/sessions` | POST | 별도 test session 명시적 생성 |
| `/run` | POST | 혼합 이벤트 batch의 dry-run/commit |
| `/state` | POST | manual_override |
| `/exercise`, `/food`, `/conversation`, `/quest`, `/time`, `/evolution` | POST | 해당 종류 이벤트의 규칙 적용 |
| `/conversation/analyze` | POST | 분석만 수행, signed review draft 반환 |
| `/food/analyze` | POST | 음식 분석만 수행, 미제공 값 unknown |
| `/conversation/respond` | POST | 공통 Memory·Quest·seed·모델의 A/B 응답, signed response drafts |
| `/logs` | GET | 선택 test session의 전체 로그 |
| `/reviews` | GET/POST | 검수 목록/명시적 검수 저장·수정·제외 |
| `/export?kind=analyzer\|response` | GET | 별도 JSONL 다운로드 |
| `/presets` | GET/POST | 12개 preset 목록/이벤트·상태·날짜별 미리보기 |

기존 `/api/preview`, `/api/simulate`, `/api/lifestyle/*`, `/api/characters/*`는 유지한다. preset POST는 항상 dry-run이며 UI에서 이벤트 미리보기 후 별도 `/run`으로 실행 모드를 선택한다.

규칙 적용 예:

```json
{
  "commands": [{
    "kind": "exercise",
    "event_id": "unique-test-event-1",
    "payload": {
      "exercise_type": "squat", "category": "lower",
      "actual": 50, "target": 50, "unit": "count",
      "verification_status": "verified"
    }
  }]
}
```

POST에는 같은 Origin과 `X-Persona-Lab: 1`이 필요하다. commit에는 `session_id`, `expected_revision`, `dry_run:false`를 지정하며 client snapshot으로 DB 상태를 덮어쓸 수 없다. 실사용자 ID는 거부한다. UI는 저장 전에 선택 대상·before/after를 표시하고 **표시된 테스트 DB 변경 확정**으로 저장한다.

## 5–6. 접속·실행 명령

```powershell
Set-Location E:\qwen-llm
.venv\Scripts\python.exe scripts\serve_persona_lab.py --warmup
```

브라우저: http://127.0.0.1:8001/. 이미 실행 중이면 기존 서버를 이용한다. 종료:

```powershell
.venv\Scripts\python.exe scripts\stop_persona_lab.py
```

기본 Character Lab 메뉴는 현재 상태 / 운동 / 식사 / 대화·성격·응답 / 퀘스트 / 시간·레벨·진화 / 로그·검수·Export의 7개 영역이다. 기존 Persona 비교와 lifestyle UI도 상단 탭에 있다.

`APP_ENV=development`, `PERSONA_LAB_ENABLED=1`과 loopback이 모두 필요하다. production/prod 환경 변수는 모든 Character Lab 경로를 404로 차단한다. 이 기능에는 실제 사용자 캐릭터를 변경하는 경로를 제공하지 않는다.

## 7. 운동 규칙

`achievement_rate = actual / target * 100`, target은 양수만 허용한다. verified 기록만 성장에 반영한다.

| 달성률 | 변화 |
|---|---:|
| ≥120% | +3 |
| ≥100% | +2 |
| ≥70% | +1 |
| ≥40% | 0 |
| 0% 초과·40% 미만 | -1 |
| 0% | 조건 충족 시 -2, 그 외 0 |

0 수행의 -2는 명시적 목표 또는 수락된 활성 운동 퀘스트가 있고, due date가 가상 현재 날짜보다 과거이며, verified actual=0인 경우에만 적용한다. 계획 없는 날과 미검증 기록에는 미수행 패널티를 주지 않는다.

upper/lower는 해당 축에, full은 두 축에 절반씩 적용한다. 내부 소수점을 유지한다. 각 축·날짜의 증가 최대 +3/감소 최대 -2를 각각 제한하며 clamp를 적용한다. 날짜는 현재 가상 날짜와 일치해야 한다. 과거 기록을 뒤늦게 삽입하는 대신 가상 시간을 순서대로 진행해 재현한다. 날짜 직접 수정은 manual_override로 로그를 남긴다.

## 8. 식생활 규칙

기존 기능에는 음식명/음식군 기록은 있었지만 요청한 정성 영양 5항목 분석과 Nutrition/EnergyBalance 엔진은 없었다. 신규 FoodAnalyzer는 분류 JSON만 생성한다. 자연어 분석과 관리자 직접 입력을 구분해 같은 backend에 적용한다.

5개 항목의 proper 이탈 횟수 0/1/2/3/4/5에 대해 Nutrition +2/+1/0/-1/-2/-2. amount low/proper/high는 EnergyBalance -2/0/+2, extreme의 low/high는 -3/+3. 한 항목이라도 unknown이면 Nutrition/EnergyBalance를 자동 적용하지 않고 review_required로 남긴다. 칼로리·수치 영양소는 만들지 않는다.

이 규칙과 출처는 YAML의 **provisional** 영역에 명시했다. 실제 Qwen의 `치킨, 감자튀김, 콜라` 분석은 protein/carbohydrate/fat/amount unknown, vegetable low, confidence 0.2였다. 자동 성장 적용이 차단되는 대상이다.

## 9. Mood 규칙

숫자 Mood는 Character Lab의 단기 상태다. 기존 categorical mood는 기존 Persona 기능에서 보존하며 응답 style adapter에서만 숫자의 부호를 기존 mood로 투영한다.

성공 +5, 크게 초과 +8, quest 완료 +5, 캐릭터 긍정 +5, 활동 긍정 +3, 운동 미달 -3, quest 실패 -3, low motivation -5, 캐릭터 직접 부정 -5. 하루 증가/감소 각각 15 상한, 전체 값 -100~100. 날짜마다 ×0.7 decay, 절댓값 0.1 미만이면 0. 같은 날짜 decay는 중복 적용하지 않는다.

기존의 24시간 categorical/energy 처리와 숫자 Mood 규칙을 혼합하지 않는다. 숫자 Mood 규칙은 provisional로 표시했다.

## 10. 장기 성격

오늘 이전의 완료된 7일을 사용한다. 7일이 쌓이기 전 갱신은 거부하며, 이미 반영한 기간과 같은/겹치는 기간은 중복 적용하지 않는다. 기존 `persona-growth.v1` 이벤트별 4축 규칙은 기존 탭에서 그대로 동작한다. 이번 주간 Character Lab 정책은 요청한 별도 테스트 정책이며 기존 데이터를 재계산하거나 변환하지 않는다.

- **Activity:** verified 운동 날짜와 실제 달성률을 사용한다. 5일·평균100% 이상 +3, 4일·평균70% 이상 +2, 3일 이상 +1, 2일 0, 1일 이하 -1, 1일 이하이면서 low motivation 2회 이상 -2. 평균은 날짜별 actual 합/target 합의 평균이다. 운동 의도 대화만으로 상승하지 않는다.
- **Affinity(affection):** 유효 대화 7일과 캐릭터 긍정 2회 이상 +3, 4~6일 +2, 2~3일 +1, 1일 0, 0일 -1. 캐릭터 직접 부정 2회 이상은 -2. exercise/food/quest 대상의 affection 예측은 관계 이벤트로 사용하지 않는다. 욕설 자체는 관계 부정 근거가 아니다.
- **Initiative:** 창 내에 제안·해결된 캐릭터 제안 중 수락하고 실제 완료한 비율. ≥80/60/40/20/0%에 +3/+2/0/-1/-2. 미해결 제안은 분모에서 제외하고 분모 0이면 유지한다. 완료에는 실제 합성 검증 기록 또는 명시적 admin_verified가 필요하다.
- 분석 신뢰도 <0.6은 장기 대화 집계에서 제외한다. 낮은 신뢰도 문장 때문에 negative 관계 횟수가 올라가지 않는다. 유효 대화가 전혀 없으면 대화 없음의 기본 -1은 별도로 적용될 수 있다.

`repeated=2`, almost daily=7, 평균 계산법, Initiative 분모 정의 등 불명확한 세부 정의는 YAML의 provisional definitions와 보고서에 공개했다. 기존 curvature/legacy axis 이벤트 규칙을 임의로 삭제하지 않았다.

## 11–12. Level/EXP·진화의 출처

기존 설정에는 4축 personality 변화, quest catalog, legacy reward 값이 있으나, 요청한 Level/EXP·상하체·체형 진화 엔진과 레벨 임계값은 없었다. 따라서 아래는 **확정 게임 규칙이 아니라 provisional 테스트 값**이다.

| 항목 | provisional 값 |
|---|---|
| verified 양수 운동 기록 EXP | 5 |
| 알려진 분석의 식사 기록 EXP | 3 |
| 일일 대화 EXP | 1, 하루 최대 3 |
| custom quest EXP | 관리자 입력값, 기본 5, 범위 0~10000 |
| 레벨 필요 EXP | 현재 level ×20, level-up 때 소비 |
| level 범위 | 1~100, 감소하지 않음 |
| 진화 레벨 | 10/20/30 |
| strong 상·하체 | 70 이상 |
| 상·하체 우세 차이 | 15 이상 |
| 체지방/저섭취 EnergyBalance | +40/-40 |
| healthy Nutrition | 60 이상 |

event_id 중복 지급을 막고, quest reward_paid는 한 번만 설정한다. legacy `config/rules.json`의 5/8은 퀘스트 reward 참고값이며 기존에 실제 EXP 엔진이 있었던 것처럼 주장하지 않는다.

Level은 진화 단계, 생활 스탯은 외형을 결정한다. 균형/상체/하체 운동형, fat_gain, underfed, ordinary, 회복형을 판정한다. previous evolution과 stage를 보존하고 `generation_required`는 현재 stage/body와 판정 외형이 달라질 때만 true다. 회복형을 다시 판정하거나 적용해도 불필요한 외형 변경을 반복하지 않는다. 실제 3D 모델 생성 작업은 실행하지 않는다.

## 13. 자동·수동 검증 결과

최종 [전체 테스트 로그](../runs/character-lab/tests-full.log): **Python 302 passed, 3 dependency deprecation warnings**. 기존 `tests/test_web_api.mjs`의 Node transport 검사도 **5 passed**여서 자동 검사는 총 307개가 통과했다. 신규 Python 테스트는 54개이며 기존 테스트 파일은 수정하지 않았다.

검증 항목: 운동 달성/미달/목표 없는 날/전신 분배/일일 상한/검증 상태/target validation, Nutrition 6단계/EnergyBalance/unknown 보류, 대화 대상 보호/욕설/낮은 분석 신뢰도/의도보다 실제 행동, 세 축의 주간 갱신/Initiative 수행 비율·분모0/기간 중복, Mood ±15/×0.7, 시스템 시간 격리, quest evidence/전이/중복 보상, Level 비감소/level-up/진화·회복·generation_required, 검수 correction/제외·dummy Export 필터, 실 tokenizer ChatML 마스킹, dry-run DB 무변경/test namespace/production 차단, migration 적용·rollback·재적용.

전체 기존 Memory/대화/Quest/pgvector 검사는 신규 PostgreSQL DB `character_lab_test_74d5ede9a63b`에서 실행했다. 운영 DB의 11개 기존 테이블을 읽기 전용으로 해시 비교했고 모두 동일했다. 테스트 DB는 삭제하지 않았다. [DB 격리 결과](../runs/character-lab/regression-result.json), [원본 파일 보존 결과](../runs/character-lab/preservation-after.json)를 보존했다.

브라우저 실제 클릭 검증:

- squat 10/50 → LowerBody 50→49.
- full 50/50 → UpperBody/LowerBody 각각 50→51.
- 직접 입력한 proper 5개 → Nutrition 50→52, EnergyBalance 0 유지.
- 별도 session 생성, 사건 저장, 초기화, DB 재조회, revision 확인.
- 저장 전 대상·UpperBody 51→82 표시 후 확정 저장.
- manual 분석 negative→neutral correction 저장, 같은 row 제외로 재검수.
- 실제 Qwen fallback의 원문 열람, 잘못된 결과의 단순 승인 차단, 수정 응답 저장.
- 브라우저 Analyzer JSONL 실제 다운로드 확인. 내려받은 1행의 JSON 데이터는 workspace Export와 동일했다(HTTP LF/Windows 파일 CRLF 줄바꿈 차이). 기존 파일이 있을 때 새 이름으로 저장되어 덮어쓰지 않았다.

[수동 검증 기록](../runs/character-lab/ui-verification.json).

![Character Lab 최종 화면](../runs/character-lab/browser-state-final.png)

## 14. 실제 Qwen 결과

기존 `models/qwen3.5-9b` BF16 + `runs/expanded-20260929/checkpoint-epoch-1`을 offline으로 사용했다. dummy와 실제 추론을 구분했다.

| 검증 | 결과 |
|---|---|
| 초기 Analyzer v1 | 5/6 기대 필드 일치. 퀘스트 거절 none 오류와 감사 표현 accept 오류 발견 |
| 보완 Analyzer v2 | 6/6 기대 필드 일치, invalid JSON 0 |
| 음식명만 입력 | unknown/낮은 신뢰도 유지, 임의 칼로리 생성 없음 |
| 동일 입력·Memory·active Quest·seed·파라미터 A/B 2쌍 | 4개 검증된 Qwen 응답, fallback 0 |
| 생활 기록 포함 추가 브라우저 A/B | A 검증됨, B raw model 2회 모두 잘못된 action → fallback |

기본 비교의 `오늘 할 수 있는 작은 목표를 추천해 줘`에서 A(Activity85/Affinity80/Initiative80)는 `walk_100`을 제안하고, B(25/80/25)는 action none이었다. 운동 거절 입력에서는 양쪽 모두 운동 퀘스트를 강요하지 않았다. 대사·Prompt·raw attempts·model/checkpoint·generation 설정은 [실제 결과 JSON](../runs/character-lab/qwen-real-v2.json)에 있다.

이는 소수의 합성 개발 사례 결과이며 일반적 분석 정확도나 모델의 전체 성격 표현 품질을 확정하지 않는다.

## 15. 실패·제한·미실행

- 초기 분석 오류는 v2 prompt의 대상·수락 예시로 보완하고 재검사했다. 초기 결과도 `qwen-real.json`에 남겼다.
- 생활 기록이 있는 낮은 Initiative 응답은 `offer_quest target_id=null`을 출력하고 repair에서도 반복했다. 기존 validator가 차단했으며 DB/보상 변화는 없었다. [raw trace](../runs/character-lab/browser-low-trace.json), 아래 브라우저 검수 화면에 보존했다. 모델 정확도 문제를 규칙 성공으로 보고하지 않는다.
- 브라우저의 1.0→1 JSON 직렬화 때문에 검수 서명이 실패했던 문제를 canonical JSON으로 수정했다. 실제 브라우저와 회귀 테스트에서 재검증했다.
- 검증 중 tokenizer fixture의 필수 응답 필드 누락과 GPU 서버가 켜진 상태의 기존 GPU lock 테스트 충돌이 있었다. fixture의 완전한 계약을 보완하고 서버 종료 후 최종 전체 검사를 다시 실행해 302개가 통과했다. 테스트를 삭제·skip·약화하지 않았다.
- 식사량 미제공 분석은 의도적으로 unknown이며 자동 성장 완료로 처리하지 않는다.
- LoRA 학습, 외부 데이터 다운로드, 대량 학습 예제 제작, 실제 사용자 상태 쓰기, Unity 실행·실제 외형 생성은 수행하지 않았다. 이 작업의 Lab 검증에 Unity는 필요하지 않다.
- response ChatML은 현재 예제도 2126토큰 이상이며 legacy 학습 기본 길이 1024에 그대로 넣을 수 없다. 조용히 truncate하지 않고, 차후 별도 task 데이터 loader와 학습 길이를 정해야 한다.

![실제 Qwen 실패와 수정 검수](../runs/character-lab/browser-qwen-review.png)

## 16–18. 검수·Export 예시

원본 model prediction은 서명으로 보호하고, correction은 별도 컬럼에 저장한다. status는 pending/approved/corrected/excluded. 서버 재시작 후 미저장 draft는 새로 생성해야 하며, 저장된 review는 목록을 다시 불러오면 새 서명으로 재검수할 수 있다.

Analyzer 저장 예는 실제 `그 퀘스트는 오늘 안 할래`의 원문·v2 prediction과 수동 정답(analysis_confidence를 0.95→0.9로 검수한 예)을 각각 보존한다. Response 저장 예는 실제 Qwen 원문과 수정된 휴식 응답, 브라우저 fallback 원문과 수정 응답이다. 메모에 **automated development verification / synthetic / not human approval / not production training data**를 남겼다. UI의 의도적으로 잘못 입력한 manual 분석 row는 corrected 저장 후 excluded로 바꿨다.

현재 예제 Export: Analyzer 1행, Response 2행. 자동 검증 예제가 사람이 승인한 최종 학습 데이터라는 뜻은 아니다.

```json
{"text":"그 퀘스트는 오늘 안 할래","label":{"target":"quest","sentiment":"negative","motivation":"low","character_affection":"neutral","acceptance":"reject","analysis_confidence":0.9}}
```

```json
{"user":"오늘 운동하기 싫어","state":{"activity":85,"affinity":80,"initiative":80,"mood":0},"memory":[{"content":"나는 짧게 걷는 것이 좋아."}],"response":"오늘은 운동하기 싫은 날이구나. 무리하지 말고 쉬어도 괜찮아."}
```

위는 설명용 축약이다. 실제 파일에는 전체 상태·Memory 출처·Quest context·model/prompt/rule identifier·검수 메모·시각이 들어 있다.

- [conversation_analyzer_dataset.jsonl](../runs/character-lab/conversation_analyzer_dataset.jsonl)
- [character_response_dataset.jsonl](../runs/character-lab/character_response_dataset.jsonl)
- [검수 table 예시](../runs/character-lab/review-examples-final.json)

approved/corrected만 Export한다. pending/excluded/dummy는 제외한다. invalid/fallback의 단순 승인은 거부하지만 사람이 수정할 수 있는 correction 경로는 제공한다. Analyzer classification과 Response speech를 같은 assistant target으로 합치지 않는다. 기존 Qwen 응답 prompt가 JSON speech 계약을 요구하므로 Response ChatML에는 자연어 대사를 기존 speech envelope로 감싸며 **분석 label을 포함하지 않는다**.

실제 로컬 tokenizer와 기존 인코딩 함수로 두 Export를 읽었다. Analyzer 391토큰, 최초 Response 예제 2126토큰. prefix labels는 전부 -100, assistant target만 학습 label에 남는다. 변환은 모델 가중치를 로드하거나 학습하지 않는다.

```powershell
.venv\Scripts\python.exe scripts\convert_character_dataset.py --kind analyzer --input runs/character-lab/conversation_analyzer_dataset.jsonl --output runs/my-analyzer-chatml.jsonl
.venv\Scripts\python.exe scripts\convert_character_dataset.py --kind response --input runs/character-lab/character_response_dataset.jsonl --output runs/my-response-chatml.jsonl
```

이미 있는 output은 덮어쓰지 않는다. [Analyzer 변환 결과](../runs/character-lab/analyzer-chatml-final.jsonl), [Response 변환 결과](../runs/character-lab/response-chatml-final.jsonl).

## 19. 필드 호환

| 표시/개념 | 실제 저장/처리 |
|---|---|
| Activity | 기존 개념 `activity` |
| Affinity | `affection`; API 입력 `affinity` alias 허용, 신규 affinity DB 컬럼 없음 |
| Initiative | Character Lab `initiative`, session table의 신규 REAL 필드와 JSON snapshot |
| legacy curiosity/confidence | 삭제·자동 변환하지 않고 그대로 보존·표시 |
| 모델 분석 신뢰도 | 오직 `analysis_confidence` |
| Mood | Character Lab numeric mood; 기존 categorical mood는 기존 화면에 유지 |

기존 7축 beta의 Initiative와 4축 Persona 데이터도 파괴하거나 자동 이주하지 않았다. Character Lab은 별도 test namespace다.

## 20. 구현 범위와 남은 작업

7개 영역, 요청한 성장·식생활·대화 분석·주간 성격·Quest 전이·가상 시간·EXP/진화 판정·검수·분리 Export·12 presets를 구현했다. presets는 모두 이벤트 목록, before/after, 날짜별 결과, 규칙, 전체 로그를 반환하고 UI 초기화는 저장된 기록을 삭제하지 않는다.

남은 제품 작업은 provisional 규칙 확정, 실제 서비스/Unity 연결, 실제 3D 생성, 넓은 사람 검수 평가와 낮은 Initiative 응답 품질 개선이다. 실제 사용자 상태 쓰기는 이 Lab에 구현하지 않았다. 기존 `train_lora.py`의 legacy 데이터 loader에 신규 두 task 파일을 바로 넣는 기능도 제공하지 않으며, 재학습 전에 독립 task 데이터 loader·길이·split 계획을 별도로 정해야 한다.

## 21. 재학습 전 확보할 데이터

- Analyzer: 감정 대상이 섞인 문장, 욕설·반어·부정의 부정, 운동/음식 불만 대 관계 부정, 감사 대 수락, 명시적 거절 대 모호한 응답, 낮은 신뢰도·unknown을 사람이 정정한 label.
- FoodAnalyzer: 음식명만 있는 경우와 실제 양·구성이 제공된 경우를 구분한 unknown/proper/low/high 정답. 미제공 칼로리는 정답에 만들지 않는다.
- Responder: 동일 Memory/Quest/seed로 비교한 Activity/Affinity/Initiative·Mood별 응답, 실제 근거를 사용하는 사례와 없는 기록을 인정하는 사례, rest/refusal 존중, 낮은 Initiative의 action none, 잘못된 quest action과 repair 실패의 correction.
- 각 task별 prompt/schema version, checkpoint identifier, 사람이 검수한 status/note, 근거 출처, 사용자/시나리오별 분리된 train/validation/test. 자동 검증 예제와 사람 승인을 구분해야 한다.

전체 자동 검사 재현은 GPU lock 테스트를 위해 모델 서버를 먼저 종료한다. PostgreSQL은 기존 데이터를 초기화하지 않고 실행 중이어야 한다.

```powershell
.venv\Scripts\python.exe scripts\stop_persona_lab.py
.venv\Scripts\python.exe scripts\verify_character_lab_regression.py
.venv\Scripts\python.exe scripts\serve_persona_lab.py --warmup
# 서버 실행 뒤, 새 output 경로로 실제 Qwen 재검사
.venv\Scripts\python.exe scripts\verify_character_lab_real.py --output runs/my-character-qwen-check.json
```

## 최종 판정

| 질문 | 판정 |
|---|---|
| A. 운동·식생활이 성장 스탯에 반영되는가? | **예.** 요청한 sandbox 규칙·보호 조건·상한을 자동/브라우저에서 확인. provisional 값은 제품 확정 필요 |
| B. 분석이 감정 대상을 구분하는가? | **검사한 사례에서는 예.** 실제 v2 6/6. 폭넓은 정확도는 미확정 |
| C. 실제 행동·대화가 장기 성격에 규칙대로 반영되는가? | **예.** 합성 verified 행동, 관계 대상·신뢰도·수행 비율과 주간 중복 보호를 검증 |
| D. 성격에 따라 Qwen 응답·Quest Agent가 달라지는가? | **차이를 확인했다.** 기본 실제 A/B는 통과, 생활 이력이 있는 낮은 Initiative 응답에는 fallback 실패가 남음 |
| E. 오류를 정정해 학습 데이터로 저장할 수 있는가? | **예.** 분석/응답 correction 저장과 독립 JSONL·실 ChatML 변환 확인. dummy/excluded는 제외 |
| F. 추가 데이터 제작·LoRA 재학습을 시작할 수 있는가? | **사람 검수 데이터 제작은 가능. 즉시 재학습은 권장하지 않음.** 규칙 확정, 넓은 검수 자료·평가 split, 실패 사례, 신규 task loader와 길이 계획이 먼저 필요. 이번에는 재학습하지 않음 |
