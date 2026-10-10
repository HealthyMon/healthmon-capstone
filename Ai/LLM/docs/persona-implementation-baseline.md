# 기존 구현의 실제 상태 감사

감사일: 2026-10-01. 대상: `E:\qwen-llm`의 기존 대화 베타와 legacy 성격 엔진. 새 `persona_*.py` 구현의 완료 보고와 구분하기 위한 기준선 문서다.

**기존 서비스는 7축 성격을 가진 로컬 대화 베타다. 사용자 요청의 curiosity/affection/activity/confidence 네 축 시스템이 기존 DB와 채팅 API에 이미 연결되어 있지는 않았다.** 대화·활동을 근거로 한 결정론적 재계산, 기억의 정정·삭제, 확인된 걸음으로 퀘스트 진행과 보상을 계산하는 코드와 과거 실제 실행 기록은 있다. 네 축의 장기 육성, 주간 상한, streak, 단계 hysteresis, 성격 기반 퀘스트 선택, Persona Lab은 기존 베타에 없었다.

## 감사 범위와 증거 수준

직접 확인한 소스는 `src/rules.py`, `src/app.py`, `src/prompts.py`, `src/model.py`, `src/beta.py`, `src/agent.py`, `src/contracts.py`, `src/db.py`, `config/rules.json`, `config/serving.json`, migration 001/002, 기존 테스트·평가 스크립트, 웹 HTML/JavaScript, 원본 데이터와 보존된 원시 평가 결과다.

- **이번 실행:** DB/GPU를 호출하지 않는 기존 테스트 15개 통과. 기존 규칙 엔진과 프롬프트 함수를 메모리에서 직접 실행했다. 데이터 감사도 실제 원본 파싱·CPU BGE 계산까지 완료했다.
- **과거 실행:** 2026-09-29의 원시 모델 응답·HTTP/flow 기록과 당시 테스트 로그를 읽었다. 문서의 `ready` 선언만으로 완료를 인정하지 않았다.
- **이번에 하지 않은 것:** PostgreSQL 시작, DB 접속·쓰기·마이그레이션, 기존 베타의 브라우저/HTTP 재검증, 기존 평가 스크립트의 GPU 실행. 따라서 당시 서버의 성공 기록을 현재 실행 중이라는 뜻으로 사용하지 않는다.
- **분류 원칙:** 순수 함수가 통과한 범위, 과거 실제 모델/DB 실행이 남은 범위, 코드만 확인한 범위를 각각 적는다. 테스트 파일의 존재나 controlled backend의 성공을 실제 Qwen 품질로 환산하지 않는다.

## 요청 항목별 분류

요청 목록과 직접 관련된 이벤트·Ledger까지 17개 항목으로 정리했다. 한 항목 안에서도 구현된 부분과 빠진 부분을 분리했다.

| # | 감사 항목 | 분류와 검증 시점 | 실제 구현과 한계 |
|---|---|---|---|
| 1 | 현재 성격축과 저장 위치 | **실제 구현 및 실행 검증 완료 — 이번 순수 함수**, DB 저장은 코드 및 과거 기록 확인 | `rules.json`의 sociability/initiative/playfulness/courtesy/bluntness/roughness/bond. `replay(sources)`가 상태를 재계산하고 PostgreSQL `state_snapshots.state`, `exchanges.state_used/state_after`에 JSON 저장. pets 테이블에 네 축 전용 컬럼은 없음 |
| 2 | 성격 변화 규칙 | **실제 구현 및 실행 검증 완료 — 이번** | 반복 텍스트 제외, 근거 소비, 복수 session, 일일 한도, 삭제 후 재계산 존재. 새 네 축·주간 상한·연속 기록·비활동 감소·hysteresis는 **기존 미구현** |
| 3 | mood 및 단기 상태 | **실제 구현 및 실행 검증 완료 — 이번** | `mood={valence,energy}`와 시간 감쇠 존재. recent_motivation/recent_stress 및 범주형 tired/proud 등의 상태는 **기존 미구현** |
| 4 | 운동 기록 처리 | 규칙은 **이번 실행 검증**, API는 **과거 실제 실행 기록** | `walk/steps` 이벤트, producer 인증, confirmed/source 구분, revision/id 중복 방지, 정정·삭제 재계산. 실제 웨어러블 수집기는 **mock/dummy만 존재**: `mock_activity.py`는 synthetic producer |
| 5 | 식생활 기록 처리 | 규칙은 **이번 실행 검증**, API는 **과거 실행 기록** | `food/serving/label`과 confirmed 구분. 3종 label/2일 조건에서 sociability 상승. 음식군·7일 식생활·균형식·반복 패스트푸드·영양소 unknown 정책은 **기존 미구현**. 음식 인식기 연결도 없음 |
| 6 | 대화 상호작용 처리 | **실제 구현 및 실행 검증 완료 — 이번** | 한국어 정규식 태그, 5개 메시지마다 검토, 서로 다른 근거 3개·session 2개 조건. 대화 의미 전체를 분류하는 모델은 아니며 긍정 상호작용의 별도 이벤트형 없음 |
| 7 | 퀘스트 제안·수락·진행·성공·실패 | 제안/수락/진행/보상은 **과거 실제 실행 기록**; 실패 육성은 **미구현** | offered→active→completed, 거절·만료·정정 시 revoked/reward reversal. `quest_failed` 이벤트, 7일 안 3회 실패 누적, 완료에 따른 성격 보너스 없음 |
| 8 | 성격값의 Persona Prompt 전달 | **실제 구현 및 실행 검증 완료 — 이번 함수 확인** | 채팅의 `current()`→context.traits/mood→`messages()`→Qwen template 경로. 숫자는 user JSON에 전달되고 일부 기존 축에는 시스템 말투 안내가 붙음. 요청된 명시적 8개 style profile 속성은 없음 |
| 9 | 성격값이 실제 답변에 미치는 영향 | **구현됐지만 오류가 있음 — 과거 원시 Qwen 결과 확인** | 동일 입력의 formal/play/blunt 대사가 달라지는 사례가 있음. 일부 톤 무시·혼합 말투·반복·기억/수치 오류도 원시 결과에서 확인. 모든 기존 축 또는 새 네 축의 독립 효과는 입증되지 않음 |
| 10 | 성격·기록을 사용한 퀘스트 선택 | 기록의 일부 gate는 **코드 및 과거 실행 확인**; 성격 선택은 **미구현** | 피곤/거절 문구, 기존 active/completed/rejected, 확인된 walk 존재, cooldown 사용. traits·energy·동기·스트레스·최근 실패를 읽지 않음. 후보가 항상 `quest_templates[:1]`여서 walk_500만 제안 가능 |
| 11 | base model/LoRA 경로 | **실제 파일 확인 완료 — 이번** | Qwen base와 선택 adapter 파일이 실제 존재. 경로와 크기는 아래 참조. 이번 baseline 감사에서는 GPU에 로드하지 않음 |
| 12 | 서비스가 선택한 checkpoint | **실제 구현 및 실행 검증 완료 — 이번 선택 함수 테스트** | `config/serving.json`의 expanded epoch 1. `scripts/serve.py`는 명시 인자→ADAPTER_PATH 환경변수→config 순서, `--base`는 adapter 해제. 현재 프로세스가 무엇을 로드했는지와 설정상의 기본값은 구분 |
| 13 | train/validation/test 실제 개수 | **실제 실행 검증 완료 — 이번 원본 파싱** | 현재 v3 216/43/58. 모든 과거 버전·중복·분포도 재계산. 모든 기존 데이터에서 새 네 축 라벨 없음. 상세는 `persona-data-audit.md` |
| 14 | 기존 평가 도구 | **구현 및 과거 실제 실행 기록 존재** | base/adapter 비교, raw/final 구분, 동일 seed, checkpoint 비교, 메모리 ablation, 20×10 flow 있음. flow와 integration은 실제 DB를 변경하므로 이번 감사에서 실행하지 않음 |
| 15 | 기존 웹 대화 UI | **구현 및 과거 실제 실행 기록 존재**, 알려진 한계 있음 | 실제 채팅·정정/삭제·퀘스트 화면, emotion/animation SVG 반응. 같은 컴퓨터 전용 cookie 및 공유 개발계정. 이번에는 브라우저 미재검증. fallback 이력과 새로고침 중 pending 복구 제한 있음 |
| 16 | 기존 관리자/개발용 테스트 화면 | 웹 Persona Lab은 **미구현**, CLI는 **코드 존재** | `try_personality.py`가 legacy 스타일 한 개를 강제로 주입해 실제 Qwen을 부르는 CLI. 합성 상태이며 자연 성장 기록이 아님. 슬라이더/A·B/30일 simulation/일자별 Ledger UI는 기존 베타에 없음 |
| 17 | 이벤트 구조와 변화 Ledger | 일부 **실제 구현**, 요구 상세 필드는 **미구현/필드 수준** | sources의 message/activity, id/revision/time/payload/valid, history의 axis/delta/date/evidence_refs 존재. 10종 이벤트·별도 idempotency_key·verification_status/confidence·before/raw_delta/streak_bonus/cap_adjustment/after/reason_code Ledger는 없음. ModelOutput.personality_update 타입은 **필드/인터페이스만 존재**, validator가 non-null을 거부 |

`tests/test_postgres.py`의 `Controlled`, `tests/test_agent.py`의 간단한 backend는 **테스트용 mock/dummy**다. 장애·경계·권한 검증에는 유효하지만 실제 Qwen이 정확하게 답했다는 근거가 아니다. 이번 분류에서 구현 없는 기능을 테스트만으로 완료 처리한 항목은 없다.

## 기존 규칙의 실제 수치와 실행 결과

초기값은 sociability 50, initiative 50, playfulness 50, courtesy 60, bluntness 20, roughness 10, bond 30이다. mood 초기값은 valence 0, energy 50이다.

| 설정 | 기존 실제 값/동작 |
|---|---|
| `max_delta` | 2. 다만 현 코드의 제안 자체는 +1로 하드코딩돼 있음 |
| `daily_absolute_limit` | 축별 절댓값 합계 5/일 |
| `dialogue_review_every` | 5개 message마다 검토 |
| `dialogue_min_evidence` / `dialogue_min_sessions` | 서로 다른 근거 3개 / session 2개 |
| 대화 유사도 제외 | 정규화 텍스트의 SequenceMatcher ratio >0.8 |
| `activity_min_events` / `activity_min_dates` | 양수 amount 3개 / 날짜 2개 |
| `valence_half_life_minutes` | 30분, 0으로 감쇠 |
| `energy_half_life_minutes` | 60분, 50으로 회복 |
| 퀘스트 후보 | walk_500(target 500, reward 5), walk_1000(target 1000, reward 8)가 config에 있으나 선택기는 첫 후보만 반환 |
| 퀘스트 cooldown / expiry | 30분 / 120분 |

대화 태그는 play→playfulness, bond→bond, courtesy→courtesy, blunt→bluntness, rough→roughness다. 피로 태그는 valence −10/energy −8, 긍정·장난 태그는 valence +8, 확인된 양수 walk는 valence +10/energy −5다. 수치는 코드에 포함돼 있어 설정 파일만 바꿔 모든 변화를 조절할 수 있는 구조는 아니다.

이번 감사에서 합성 sources를 기존 `replay()`에 직접 전달한 결과:

| 메모리에서만 실행한 입력 | 실제 결과 |
|---|---|
| backend/confirmed walk 3회, 2일 | initiative 50→51 |
| backend/confirmed food, 서로 다른 label 3종, 2일 | sociability 50→51 |
| 미검증 walk 3회 | 모든 기존 축 초기값 유지 |
| 위 walk 기록 뒤 계산 시점만 Day 30으로 이동 | initiative 51 유지. 비활동 감소 없음 |
| context의 initiative 50→90, 나머지 고정 | user JSON의 숫자는 90으로 바뀜. system style guidance 문자열은 동일 |

이 결과는 DB·센서·Qwen을 사용한 결과가 아니다. **실제 Python 규칙 함수에 합성 이벤트를 입력한 실행 결과**다. 마지막 행은 프롬프트 구성 확인이며 모델 답변 차이를 측정한 것이 아니다.

기존 history에는 다음 수준의 근거가 남는다.

```json
{
  "axis": "initiative",
  "delta": 1,
  "date": "2026-09-28",
  "rules_version": "rules.v1",
  "evidence_refs": [
    {"kind": "activity", "id": "e0", "revision": 1},
    {"kind": "activity", "id": "e1", "revision": 1},
    {"kind": "activity", "id": "e2", "revision": 1}
  ]
}
```

이 history는 요청된 새 Personality Change Ledger 전체 필드를 충족하지 않는다. 특히 원래 제안량과 cap으로 잘린 양, streak 보너스, 변화 전후 수치를 구분해서 저장하지 않는다.

## 저장·API 경계

`migrations/001_initial.sql`에는 pets, sources, memories, requests, exchanges, quest_offers, reward_ledger, state_snapshots, outbox가 있고, 002는 suggestion_jobs를 추가한다. sources.kind는 message/activity 두 종류만 허용한다. 사용자 소유권은 pets.owner_id와 `owned()` 검사로 연결되며, 사건 자체에 별도 user_id/character_id/verification_status/confidence/idempotency_key 열이 있는 구조는 아니다.

활동 API는 `ActivityInput`의 `event_id`를 `activity:<event_id>` source ID로 바꾸고 동일 revision·동일 payload 재전송은 duplicate로 반환한다. 변경은 revision+1을 요구한다. source가 sensor/backend이거나 confirmed이면 producer token을 요구하며 photo+confirmed는 schema에서 거부한다. 사용자 채팅 “운동했어”를 자동으로 확인된 활동으로 바꾸는 코드는 없다.

`reconcile_quests()`는 수락 시각부터 만료 전까지 확인된 backend/sensor amount를 합산하고 목표·보상은 서버 template 값으로 계산한다. 정정·삭제 뒤에는 보상 차액을 ledger로 보정한다. 그러나 퀘스트 성공/실패를 성격 이벤트로 replay에 전달하는 경로는 없다. 만료 처리도 독립적인 실패 누적 엔진이 아니라 일부 API 진입 시 status를 바꾸는 수준이다.

식생활에는 섭취량 serving과 label만 있다. 칼로리·영양소 인식기, 음식군 taxonomy, 식생활 장기패턴, unknown 영양소 처리 모델이 연결됐다고 볼 수 없다. Qwen 클래스로 multimodal 모델을 사용하더라도 기존 `generate()`는 텍스트 chat template만 전달하므로 사진 인식이 구현된 증거가 아니다.

## 모델 경로·프롬프트·출력 검증

- Base: `E:\qwen-llm\models\qwen3.5-9b`. config revision `c202236235762e1c871ad0ccb60c8ee5ba337b9a`. index가 가리키는 4개 safetensors 파일 존재를 다시 확인했고 합계는 19,306,310,880바이트다.
- 선택 LoRA: `E:\qwen-llm\runs\expanded-20260929\checkpoint-epoch-1`. adapter config 및 86,630,872바이트의 adapter_model.safetensors가 실제 존재한다.
- BGE-M3: `E:\qwen-llm\models\bge-m3`. 메모리 검색 임베딩용이며 기존 코드에서 CPU로 로드한다.
- `QwenBackend`는 BF16, CUDA:0, sdpa, local_files_only, max_new_tokens 240, temperature 0.7, top_p 0.9, repetition_penalty 1.05를 사용한다. GPU file lock이 존재한다. 일반 채팅 API는 생성마다 seed를 받는 인터페이스가 없다.

기존 `style_guidance()`는 speech_level과 일부 축의 threshold를 사용한다. bluntness≥70, playfulness≥70, courtesy≥75, roughness≥70 등에 직접 문장을 붙인다. bluntness와 playfulness는 if/elif여서 동시에 높으면 bluntness 분기가 우선한다. sociability/initiative/bond는 user context 숫자로는 전달되지만 각각의 명시적인 style rule이 없다. 새 네 축 단계와 hysteresis, question_frequency/warmth/initiative/assertiveness 등의 profile은 기존 프롬프트에 없었다.

`agent.validate()`는 JSON schema, memory ID, 후보 Quest ID, 성격 변경 금지, 일부 확인·보상 단정 문구, 설정된 존댓말/비속어를 검사한다. 최대 2번 생성 후 fallback으로 간다. 모델 speech의 모든 숫자·상대적 선호·사실을 의미적으로 검증하는 시스템은 아니다. `personality_update` 필드가 타입으로 선언돼 있어도 실제 값이 있으면 거부한다.

## 과거 실제 실행에서 확인되는 범위와 오류

과거 결과를 현재 실험처럼 보고하지 않기 위해 날짜와 원시 근거를 분리한다.

| 2026-09-29 보존 결과 | 이번 읽기에서 직접 확인한 내용 | 해석 범위 |
|---|---|---|
| `runs/flows-development.json` | 20 flows, 200 turns, 변화 대상 8개/유지 대상 8개 통과 기록, fallback 2 turns, HTTP error 0 | 실제 모델·DB의 개발 flow. 합성 입력과 시간 조작을 사용했고 200개 독립 frozen test가 아님 |
| `runs/improvement-20260929/final-comparison.json` | base/pilot epoch 3/expanded epoch 1 각 58개 원시 attempt와 final 존재 | 같은 case와 seed 설정을 사용한 과거 실제 생성 기록 |
| `runs/real-integration-v2.json` | 실제 Qwen+LoRA/PostgreSQL/pgvector/BGE로 기록됐고 raw response가 보존됨 | 합성 사용자의 통합 테스트. 현재 DB 접속 성공을 의미하지 않음 |
| `docs/BETA_VERIFICATION.json` | 브라우저 5 turns를 base 3/선택 LoRA 2로 구분해 기록 | 모든 5 turns를 선택 LoRA 결과라고 합산하면 안 됨 |
| `runs/all-tests-final.log` | 당시 21 passed, 3 warnings 기록 | 당시 실행이며 현재 전체 회귀 통과와 다름 |
| `runs/restart-check.json` | 실제 PostgreSQL 재시작 통과 기록 | 이번에는 재시작하지 않았고 Docker 검증도 아님 |

선택 epoch 1의 원시 결과에는 동일한 “머그잔을 엎질러서 적어 둔 메모가 젖었어” 입력에 formal/play/blunt 응답이 달라지는 사례가 있다. formal은 공손한 위로, play는 “머그잔이 메모를 납치했네”, blunt는 “흥, 메모가 젖었네”로 표현됐다. 이는 옛 일부 스타일 구분의 실제 사례이지만, 형용사·감탄사 편중과 각 축 독립성 문제를 해소한 증거는 아니다.

오류도 원시 context와 final을 직접 대조할 수 있다.

- `final_choice`: context memory는 “탁구보다 배드민턴을 좋아해”다. final은 “지금까지 운동 선호도에 대해 말한 적은 없어. 탁구보다 배드민턴을 좋아한다고 했어.”로 모순된다.
- `f_active_quest`: 서버 template target은 500, progress는 120인데 final은 “120걸음 중 500걸음을 채웠어”라고 뒤집어 설명한다. action ID는 맞아도 speech의 수치 의미는 틀릴 수 있다.
- 브라우저 선택 LoRA 기록: “걷기보다 수영이 좋아”를 “걷기는 취향이 아니야”로 과장한 응답이 보존돼 있다.

과거 semantic review에서 epoch 1은 58건 중 raw tone 6, memory_fact 4, quest 2, repetition 1개 범주에 표식이 있고 fallback은 1건이다. 범주가 겹치므로 합산 오류율로 사용하면 안 된다. 검수자는 데이터 작성과 같은 Codex agent이며 사람 검수는 없다. 이번 문서는 위 원시 사례를 읽어 오류의 실재를 확인했지만, 전체 58건을 새로 블라인드 채점하지는 않았다.

## 이번에 실행한 기존 회귀 테스트

DB 연결·GPU 로드 여부를 먼저 소스에서 확인하고 아래만 실행했다.

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m pytest -p no:cacheprovider -q `
  tests\test_rules.py tests\test_agent.py tests\test_guard_scope.py `
  tests\test_serving_config.py `
  tests\test_improvement.py::test_repair_contains_failed_assistant_and_repeat_second_is_checked `
  tests\test_improvement.py::test_activity_evidence_is_not_missing_memory_and_unrelated_fact_is_not_nickname
```

**실제 결과: 15 passed, 1 warning in 0.50s.** 경고는 Starlette TestClient/httpx의 기존 deprecation이다. 새 pytest cache나 bytecode를 작성하지 않는 옵션을 사용했다.

확인한 범위는 mood 감쇠, 기존 변화 조건·일일 cap, 동일 문구 근거 재사용 방지, 삭제 반영, role boundary, memory/quest ID 경계, repair와 반복 응답 fallback, 실제 활동 근거와 기억 부재의 구분, 선택 adapter 기본값/override다.

다음은 실행하지 않았다.

- `test_improvement.py` 전체: real retrieval/quest opt-out의 2개 테스트가 실제 DB에 pet/event를 쓰므로 순수 테스트가 아니다.
- `test_postgres.py`, `test_beta.py`: 실제 DB 생성·수정·삭제 및 일부 BGE 실행을 포함한다.
- `test_gpu_lock.py`: 외부 GPU lease가 이미 잡힌 상태에서 테스트가 충돌할 수 있어 이번 동시 작업에서는 실행하지 않았다. 테스트 코드상 CUDA 생성 전에 lock 충돌을 확인하는 구조는 읽었다.
- evaluate_flows/integration/restart 스크립트: DB를 변경하거나 GPU를 로드하므로 실행하지 않았다.

기존 테스트 15개 통과를 새 네 축 시스템의 cap/streak/30일 재현성 시험 결과로 사용하면 안 된다. 새 구현의 테스트 결과는 별도 최종 보고서에서 다룬다.

## 이번 새 구현과 기존 서비스의 경계

새 네 축 코드는 `src/persona_engine.py`, `src/persona_style.py`, `src/persona_quests.py`, `src/persona_runtime.py`, `src/persona_lab.py`, 관련 config 및 `web/persona-lab/`에 별도로 분리되어 있다. `scripts/serve_persona_lab.py`는 별도 개발용 FastAPI 화면을 실행하며 기존 PostgreSQL 시작이나 migration을 호출하지 않는다. 테스트 캐릭터를 저장하는 경우에도 `src/persona_store.py`의 별도 `runs/persona-lab/test-characters.sqlite3`를 사용한다.

**기존 `src/app.py`의 `/pets/{pet}/chat`과 기존 7축 DB 상태를 새 네 축으로 마이그레이션하지 않았다.** 기존 사용자 상태를 보존하면서 Lab에서 새 엔진과 실제 모델 반응을 검증하는 구조다. 따라서 “기존 웹 베타의 모든 대화·운동 이벤트가 이미 새 네 축에 누적된다”거나 “기존 캐릭터가 자동으로 새 육성 규칙을 사용한다”고 보고하면 안 된다. 기존 서비스로 연결하려면 별도의 축 전환 정책·이벤트 변환·데이터 이행 검증이 필요하다.

이 baseline 감사의 산출물은 이 문서 하나다. 기존 소스·config·데이터·checkpoint·PostgreSQL 파일은 이 감사에서 수정하지 않았다. 새 구현의 실제 완료 범위와 남은 일은 `persona-system-audit.md`, `persona-lab.md`, 실제 Qwen 평가·시뮬레이션 산출물과 함께 판단한다.
