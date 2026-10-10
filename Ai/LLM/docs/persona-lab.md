> 2026-10-01 생활 기록 입력·9개 dry-run preset·말투/퀘스트 전후 비교 추가: [생활 기록 실행·결과 보고서](E:/qwen-llm/docs/persona-lifestyle.md), [정확한 학습 상태](E:/qwen-llm/docs/persona-training-audit.md).

# Persona Lab — Windows 로컬 사용법

작업 위치는 `E:\qwen-llm`이다. 이 화면은 새 `curiosity / affection / activity / confidence` 엔진을 테스트한다. 기존 7축 웹 베타, PostgreSQL, 학습 데이터, LoRA는 그대로 보존한다. `/workspace`나 Docker, 외부 서비스, 새 모델 다운로드가 필요하지 않다.

## 실행

PowerShell:

```powershell
Set-Location E:\qwen-llm
.\.venv\Scripts\python.exe -X utf8 scripts\serve_persona_lab.py --warmup
```

주소는 **http://127.0.0.1:8001/**. GPU가 부족하거나 다른 Healthmon 프로세스가 GPU lock을 소유하면 명시적인 오류를 표시한다. 기존 서버와 GPU 모델을 동시에 올리지 않는다. 종료는 실행한 콘솔에서 Ctrl+C, 백그라운드로 실행한 경우 아래 전용 명령을 쓴다.

이미 Persona Lab이 켜진 상태에서 실행 명령을 다시 입력하면, 모델을 중복 로드하지 않고 접속 주소를 안내한 뒤 종료한다. 이때 기존 서버는 계속 실행된다. PC를 종료하면 서버도 종료되고 다음 부팅 후에는 위 명령으로 수동 실행한다. 브라우저 탭을 닫는 것만으로 서버가 종료되지는 않는다.

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\stop_persona_lab.py
```

기본 모델은 `config/qwen3.5-9b.json`의 실제 경로 `E:\qwen-llm\models\qwen3.5-9b`, adapter는 `config/serving.json`의 `runs/expanded-20260929/checkpoint-epoch-1`이다. 네트워크 다운로드는 비활성화한다. 서버 로그와 PID는 `runs/persona-lab/`에 남는다.

별도 프로세스가 아닌 다른 서버에서 `src.persona_lab:app`을 올려도 `PERSONA_LAB_ENABLED=1`과 `APP_ENV=development`가 모두 없으면 **모든 화면/API/정적 파일은 404**다. `APP_ENV`, `ENVIRONMENT`, `NODE_ENV` 중 하나라도 production/prod이면 차단한다. loopback peer, localhost Host, 쓰기 요청의 동일 Origin 및 전용 헤더를 검사한다. 외부 연결이나 운영 사용자 인증을 제공하는 앱이 아니다.

## Preview

A/B 각각의 **캐릭터 말투**에서 `기본형 · 몽글이` 또는 `싸가지형 · 툴툴대는 친구`를 선택한다. preset의 `싸가지형 · 말투만 변경`도 같은 옵션이다. 네 성격값과 mood는 유지하며, 툴툴대기·빈정거림·건방진 장난을 별도 표현 지침으로 추가한다. 기분 preset이나 시뮬레이션 날짜를 불러와도 현재 말투 선택을 유지하고, 기본값 초기화와 일반 성격 preset은 기본형으로 돌아간다.

이 옵션은 현재 로컬 모델에 전달하는 Prompt를 바꾸며 새 LoRA 학습은 하지 않는다. 성장량·퀘스트·보상·기억은 바꾸지 않는다. 사용자가 장난을 그만하라고 하면 표현 지침보다 그 요청을 우선한다. 장기 상태의 테스트 DB 저장과 별개인 Preview 말투 설정이다. 기존 화면에서는 새로고침(F5)하면 새 선택지가 나타난다.

1. A/B의 네 축을 슬라이더로 바꾸거나 preset을 선택한다. mood, energy, recent_motivation, recent_stress는 별도 입력한다.
2. 같은 사용자 입력을 작성하고 실제 Qwen 또는 명확히 표시된 DUMMY를 선택한다.
3. 같은 seed·temperature·생성 설정으로 각 1회 또는 5회 생성한다. 단일 GPU이므로 A/B 생성은 순차 처리하고 결과를 나란히 보여준다.
4. 대사, emotion/animation, fallback, 선정 퀘스트와 이유를 확인한다. 각 결과의 상세 영역에 실제 최종 prompt, 입력 성격, 단계, style profile, Memory 출처, 생성 설정, 모든 생성 원문/repair를 제공한다.

5회 생성은 seed를 `입력 seed + 0..4`로 사용하고 각 A/B끼리는 같은 seed다. 같은 상태를 여러 seed로 비교하는 기능이며, 동일 출력 5회 복사를 의미하지 않는다. 재생성 시 seed는 해당 반복 seed+attempt index다. 동일 환경의 실제 재현 결과는 `runs/persona-lab/seed-reproducibility.json`에 기록한다. CUDA/SDPA의 환경 간 bit 단위 재현성을 보장하지 않는다.

기본 생성값은 max_new_tokens=240, temperature=0.7, top_p=0.9, repetition_penalty=1.05, max_time=90초다. 최초 모델 로딩과 5회 비교에는 시간이 걸린다. 스트리밍이 아닌 최종 JSON 응답 방식이다.

**Preview는 저장하지 않는다.** PostgreSQL에 연결하지 않고 별도 Lab SQLite도 생성·변경하지 않는다. 화면의 Memory는 사용자가 넣는 합성 테스트 입력이며 원래 사용자 기록을 자동으로 가져오지 않는다. DUMMY는 고정 UI 점검 문장이고 말투 평가에서 제외한다. 규칙 fallback 대사도 `output_origin=fallback`으로 구분하고 모델 말투 평가에서 제외한다.

## Simulation

- 6개 시나리오 또는 직접 이벤트 JSON을 선택한다. 1·7·14·30일을 실제 대기 없이 계산한다.
- Day 0은 시작일 자정, Day 1은 그날 마지막 순간이다. Day 30은 시작일로부터 30번째 날 종료 시점이다. 기본 시간대는 Asia/Seoul이다.
- 초기 성격/단기 상태는 실행 시 Preview A 값을 사용한다. 초기값 자체를 바꾸려면 `config/persona_rules.json`을 수정하고 서버를 재시작한다.
- 빠른 입력기로 운동, 음식, 대화, 퀘스트 성공/실패를 추가할 수 있다. 자세한 입력은 이벤트 JSON을 편집한다. `source=simulation`만 허용한다.
- 날짜별 성격·mood·energy·streak·퀘스트와 전체 Ledger를 확인한다. 선정 퀘스트는 합성 `quest_proposed` 사건으로 다음 날 기록에 반영되어 반복 제한을 검사한다. Day 0의 퀘스트는 비교용 미리보기이며 발행 횟수에 포함하지 않는다.
- 날짜 행의 A/B 버튼으로 **그날의 상태, 그때까지의 기록, 그날 시각**을 Preview에 가져온다. 나중 날짜의 기록을 과거 대화에 넣지 않는다. 숫자는 화면에서 반올림해 보이더라도 내부 입력에는 소수점을 유지한다.

`dry-run`이 기본값이다. 명시적으로 테스트 캐릭터를 만든 뒤 저장 체크를 켠 실행에만 `runs/persona-lab/test-characters.sqlite3`에 저장한다. 원래 PostgreSQL과 완전히 다른 파일이며, API가 만든 `lab-...` 테스트 ID만 받는다. 단순히 임의 ID에 lab- 접두사를 붙여도 등록되지 않은 캐릭터에는 저장할 수 없다. 원본 사용자/production 데이터에 commit하는 경로는 없다. 합성 기록은 실제 센서 검증을 뜻하지 않는다.

같은 ID·같은 내용은 한 번만 저장한다. 같은 ID/키로 다른 내용을 넣으면 충돌을 반환하고 해당 배치 전체를 rollback한다. 저장은 append-only이고, 계산한 최종 상태와 Ledger가 snapshot으로 함께 저장된다. 초기값이 다른 시뮬레이션을 기존 테스트 캐릭터에 붙이는 것도 차단한다.

## 이벤트와 API

모든 이벤트는 event_id, user_id, character_id, event_type, occurred_at(시간대 포함), source, verification_status, confidence(0~1), payload, idempotency_key를 가진다. Lab API에서는 아래 예처럼 같은 Origin과 헤더가 필요하다.

```python
import httpx
client = httpx.Client(base_url="http://127.0.0.1:8001", timeout=360,
    headers={"Origin": "http://127.0.0.1:8001", "X-Persona-Lab": "1"})
preview = client.post("/api/preview", json={
    "mode": "qwen", "text": "오늘은 무엇을 해볼까?",
    "a": {"personality": {"curiosity":20,"affection":50,"activity":50,"confidence":50}},
    "b": {"personality": {"curiosity":80,"affection":50,"activity":50,"confidence":50}},
    "repetitions": 1, "generation": {"seed":20261001}
})
preview.raise_for_status()
```

| API | 용도 |
|---|---|
| GET /api/health | 선택 adapter와 로딩 상태 |
| GET /api/config | preset, 시나리오, 실제 rules, Quest Catalog |
| POST /api/preview | 저장 없는 동일 조건 A/B |
| POST /api/simulate | 기본 dry-run, 명시적 테스트 캐릭터 commit |
| POST /api/characters | 별도 합성 캐릭터 생성 |
| GET /api/characters/{id} | 저장된 테스트 초기값·이벤트 조회 |
| POST /api/characters/{id}/events | 테스트 사건 append, 재계산된 상태·Ledger 반환 |

Preview에 `events`로 공통 이력을 넣거나 `events_a/events_b`, `now_a/now_b`로 날짜별 이력을 지정할 수 있다. 일반 축별 비교에서는 입력·Memory·생성 설정을 동일하게 유지한다. 장기 시나리오 비교는 기록 자체가 실험 변인이므로 이력을 별도로 기록한다.

| 사건 | 주요 payload |
|---|---|
| exercise_recorded | exercise_type, 양수 steps 또는 minutes/duration_minutes 또는 amount+unit |
| food_recorded | food_name, food_group, fast_food, balanced, 선택적 calories/nutrients |
| conversation / positive_interaction | text, meaningful, asks_character_state, topic, negative, greeting |
| quest_proposed / quest_accepted | Catalog quest_id, 시도별 quest_instance_id |
| quest_progressed | 위 ID, 증가하는 progress(0~1), evidence_event_ids |
| quest_completed | 위 ID, 수락 이후 실제 목표 수량을 채운 검증 evidence_event_ids |
| quest_failed | 위 ID, 먼저 수락한 시도. 취소/거절은 outcome=cancelled/declined |
| inactivity_period | anchor_only:true로 시작 시각 지정; 사용자 임의 감소량은 받지 않음 |

성격 변화에는 verified + 신뢰 source + confidence≥0.8이 필요하다. 미검증 운동·음식·퀘스트는 성장·novelty·streak 근거가 될 수 없다. 운동했다는 대화를 운동 이벤트로 변환하지 않는다. 없는 음식군/칼로리/영양소는 unknown이며 추론하지 않는다. `fast_food` 또는 `balanced`는 신뢰된 기록 제공자의 분류 또는 합성 설정이지 음식명만으로 계산한 영양학적 판정이 아니다.

## 재현 명령

```powershell
# DB/GPU 없이 규칙·스타일·Lab 격리 테스트
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_persona_engine.py tests/test_persona_style_quests.py tests/test_persona_lab.py tests/test_persona_review.py -q

# 6개 30일 시나리오와 상한 검증만
.\.venv\Scripts\python.exe -X utf8 scripts/evaluate_persona_lab.py --simulations-only

# Lab 실행 중에 실제 epoch 1 LoRA 비교; 기존 평가 결과를 보존하려면 먼저 결과 폴더를 복사
.\.venv\Scripts\python.exe -X utf8 scripts/evaluate_persona_lab.py --repetitions 3

# 같은 코드·설정의 중단된 평가를 재개: 완료된 쌍은 유지하고 나머지만 생성
.\.venv\Scripts\python.exe -X utf8 scripts/evaluate_persona_lab.py --repetitions 3 --resume

# 원본을 수정하지 않는 데이터 감사, BGE-M3는 CPU
.\.venv\Scripts\python.exe -X utf8 scripts/audit_persona_data.py --semantic
```

## 남는 경계

RTX 3090에서 연속 긴 context 평가 중 한 요청이 360초를 넘어 중단된 적이 있다. 생성 후 임시 CUDA cache 해제를 추가하고 서버를 재시작한 뒤 남은 비교를 마쳤다. 실제 응답 시간은 입력 길이·repair·GPU 상태에 따라 달라진다. 모델·Prompt·생성 설정을 바꿨다면 `--resume` 결과를 같은 조건의 평가로 합치지 말고 기존 결과를 별도 보존한 후 새 평가를 시작한다.

이 구현은 별도 4축 개발 엔진과 실제 로컬 Qwen 비교 환경이다. 기존 `/pets/...` 7축 서비스의 DB나 사용자 기록을 자동 변환하지 않는다. 실제 운동·식생활 생산자 인증, 운영 저장소 연결, 서비스의 버전 전환은 별도 작업이다. Lab의 source 문자열만으로 실제 사건의 진위를 보증할 수 없다. 모델의 말투·숫자·기억 정확성은 [실제 결과 보고서](persona-system-audit.md)의 판정을 따른다.
