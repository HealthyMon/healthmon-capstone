# 육성 AI / Persona Lab 구현·실행 감사

2026-10-01 · Windows 로컬 `E:\qwen-llm` · RTX 3090 · 현재 epoch 1 adapter 기준

**네 축 규칙 엔진과 로컬 Persona Lab은 구현하고 실행 검증했다. 현재 LoRA가 네 축별 말투와 퀘스트 설명을 일관되게 표현한다는 완료 기준은 아직 충족하지 못했다.** 수치·Catalog·저장 경계의 정상 동작과 실제 모델 대사의 품질을 분리해 보고한다.

기존 프로젝트는 요청에 적힌 네 축이 아니라 **7축 서비스**였다. 기존 DB의 축을 임의 환산하거나 덮어쓰지 않았다. 새 네 축은 별도 Lab과 재사용 가능한 순수 규칙 모듈에 연결했다. 기존 `/chat` 서비스를 네 축으로 전환한 작업은 아니다.

상세 근거: [기존 구현 감사](E:/qwen-llm/docs/persona-implementation-baseline.md), [Lab 사용법](E:/qwen-llm/docs/persona-lab.md), [데이터 감사](E:/qwen-llm/docs/persona-data-audit.md), [실제 모델 의미 검토](E:/qwen-llm/docs/persona-model-review.md).

**후속 업데이트 — 싸가지형 추가:** A/B별 `캐릭터 말투`와 `싸가지형 · 말투만 변경` preset을 추가했다. 같은 네 축·단기 상태에서 표현 지침만 바뀌며 성장·퀘스트·보상에는 영향을 주지 않는다. 새 학습 없이 기존 로컬 Qwen3.5-9B + epoch 1 LoRA를 그대로 사용한다. 2026-10-01 현재 신규 기능을 포함한 Persona 테스트 **89개 통과**(아래 최초 보고의 88개에 불변성 테스트 1개 추가). 기존 순수 회귀 15개는 앞선 실행 결과이며 이번에 재실행하지 않았다.

최종 말투 지침 v1.1으로 동일 성격·상태·입력·seed를 고정한 3상황 A/B, 총 **6개 실제 Qwen 응답**을 확인했다. 모두 fallback 없이 반환됐다. “할 일은 많다고? 소파가 그 말을 듣고 잠들었겠네.”처럼 빈정거리는 비유가 나타났고, “장난은 잠깐 쉬고” 요청에는 “장난은 잠시 접어두자. 왜 속상한지 편하게 말해 봐.”라고 답했다. 다만 퍼즐 농담은 여전히 딱딱하고 어색한 문장을 포함했다. **목소리 선택 기능은 완료됐지만, 재미와 자연스러움이 항상 충분하다는 판정은 아니다.** 샘플은 상황당 seed 1개이며 네 축 전반의 품질 판정 B/C는 바뀌지 않는다.

최종 원문: [sassy-model-comparisons.json](E:/qwen-llm/runs/persona-lab/sassy-model-comparisons.json). 첫 지침으로 생성한 6개 응답도 `sassy-model-comparisons-v1.json`에 보존했다. 새 설정은 `config/persona_voices.json`, 적용 모듈은 `src/persona_voice.py`이며 `persona_runtime.py`, `persona_lab.py`, Lab JS/CSS, API 테스트·사용 문서를 함께 수정했다. 최초 감사 36쌍/72개 결과는 덮어쓰지 않았다.

## 1. 기존에 실제 구현돼 있던 기능

기존 `src/rules.py`는 sociability/initiative/playfulness/courtesy/bluntness/roughness/bond를 사용했다. 기본값은 50/50/50/60/20/10/30이다. PostgreSQL `state_snapshots`와 `exchanges`에 상태를 저장한다. 대화 근거 누적, 중복 문구 제외, 일일 한도, 시간에 따른 mood 감쇠, 삭제·정정 후 재계산이 구현돼 있었다.

운동은 확인된 walk/steps, 식생활은 food/serving/label을 처리했다. 실제 센서·음식 인식기 연결은 없었다. 퀘스트 수락·확인된 활동으로 진행·보상·정정 시 취소 코드와 과거 실제 실행 기록은 있지만, 후보 선택은 사실상 첫 walk_500에 고정돼 있었다. 새 네 축, weekly cap, streak, hysteresis, 성격 기반 후보 선택, 웹 Persona Lab은 없었다.

이번에는 기존 순수 테스트 15개와 규칙/프롬프트 함수를 실행했다. 기존 웹·PostgreSQL 통합은 원시 과거 결과를 읽었으며 현재 서버가 검증됐다는 뜻으로 사용하지 않았다. 17개 감사 항목의 **실제 실행 / 코드 / 필드 / dummy / 오류 / 미구현** 분류와 실행 시점은 기존 구현 감사 문서에 정리했다.

## 2. 새로 구현한 기능

- curiosity/affection/activity/confidence의 결정론적 이벤트 재생, 별도 mood/energy/motivation/stress, 설정 파일 기반 변화량·제한·초기값.
- 10종 이벤트와 출처·검증·신뢰도·idempotency key, 중복/충돌 차단, streak, rolling 7일 cap, 비활동 유예, 단계 hysteresis, 원인별 Ledger와 합산 설명.
- 8개 말투 속성의 style profile, 네 축 전용 Prompt, 검증된 활동·수락된 퀘스트·기억 출처의 Context 전달.
- 9개 Quest Catalog와 최근 성공·실패·거절·에너지·성격·반복 횟수에 따른 선택. 목표·보상 ID·검증 방식은 규칙이 결정.
- 별도 localhost Persona Lab: A/B 슬라이더·preset·1/5회 생성·동일 seed와 생성 설정·최종 Prompt/Context/원문/repair/fallback 표시.
- 1/7/14/30일 synthetic simulation, 여섯 시나리오, 날짜별 상태/퀘스트/Ledger, 선택 날짜의 실제 모델 대화, 기본 dry-run과 별도 테스트 캐릭터 commit.
- 실제 데이터 통계·중복·CPU BGE 의미 유사도 감사와 실제 로컬 epoch 1 비교 결과 보존.

## 3. 구현하지 못한 기능과 이유

**일관된 네 축 말투 품질은 미달이다.** 기존 LoRA는 네 축 라벨이 없는 데이터로 학습됐다. 새 Prompt를 적용해도 confidence/affection의 독립 차이가 약하고, 후보 ID는 맞는데 설명이 다른 활동을 말하거나 후보가 없다고 답하는 사례가 남았다. 정형 JSON 검증을 의미 정확성으로 간주하지 않았다.

실제 센서/음식 인식기, 사람 검수 데이터, 기존 PostgreSQL의 네 축 마이그레이션·인증된 이벤트 수집 연결, 실제 보상 지급 연결은 이번 Lab에 구현하지 않았다. Lab의 `source=simulation`은 테스트 입력이며 실제 사용자의 운동을 입증하지 않는다. Unity·외부 배포·대규모 데이터 생성·LoRA 학습은 요청 범위에서 제외됐다.

## 4. 성격 변화 공식

이벤트를 시간과 ID로 정렬하고, 사용자/캐릭터가 섞이지 않은 스트림에서 검증·중복·수락·근거를 확인한 뒤 replay한다.

```text
제안량 = raw_delta + streak_bonus
적용량 = 이벤트 잔여 한도 → 일일 잔여 한도 → 최근 7일 잔여 한도
         → streak 합산 잔여 한도 → 0~100 범위로 제한한 제안량
after = before + final_delta
cap_adjustment = final_delta - raw_delta - streak_bonus
```

증가·감소 예산은 따로 누적한다. 같은 날 +1 후 −0.5를 주었다고 증가 예산이 다시 생기지 않는다. 주간은 서울 날짜 기준 현재 날짜와 앞선 6일의 rolling window다. streak 보너스는 전체 축 합산 주간 +1.5 한도이며 일일/축별 주간 한도도 함께 지킨다. 중복 이벤트는 추가 지급이 없고 동일 ID/key에 내용이 충돌하면 관련 충돌 그룹 전체를 제외한다.

운동 퀘스트 완료 confidence +0.6은 일반 이벤트 한도 +0.5가 우선해서 최대 +0.5다. 운동 규칙의 완료 +0.6과 퀘스트 규칙의 완료 +0.6을 두 번 지급하지 않는다. 요청의 설명용 ‘7일 +4.1’ 예시는 주간 +3.0 제한과 충돌하므로 그대로 재현하지 않았다.

단기 수치는 중립값을 향해 24시간 반감기로 회복하고, mood는 사건 후 18시간 유지 뒤 중립으로 돌아간다. `neutral + (현재값-neutral) × 2^(-경과시간/24h)`를 사용한다. 단기 변화는 장기 축의 감소로 대체하지 않는다.

## 5. 설정 파일의 실제 초기 수치

설정은 [persona_rules.json](E:/qwen-llm/config/persona_rules.json), [persona_styles.json](E:/qwen-llm/config/persona_styles.json), [quest_catalog.json](E:/qwen-llm/config/quest_catalog.json)에 있다. 변경 후 서버를 재시작한다.

| 항목 | 실제 값 |
|---|---|
| 네 장기 축 | 각 50.0, 범위 0~100 |
| 단기 초기값 | mood neutral, energy 60, recent_motivation 50, recent_stress 0 |
| 일반 이벤트 | 축별 절댓값 최대 0.5 |
| 일일 / rolling 7일 | 축별 +1.0/−0.5, +3.0/−1.0 |
| streak | 전체 축 합산 최근 7일 +1.5 |
| 검증 | verified + source backend/sensor/simulation + confidence ≥0.8; Lab은 simulation만 수용 |
| 반복 대화 | 정규화 유사도 0.88, 7일 창; 대화 affection +0.4/일 추가 제한 |
| 단계 | very_low <25, low <40, medium <60, high <75, very_high ≥75 |
| hysteresis | 진입 경계와 하향 이탈 간 3점 완충; high 진입 60, medium 복귀 ≤56 |
| Catalog 반복 제한 | 같은 퀘스트 최근 7일 최대 3회; 제안·수락 동일 attempt 중복 계수 안 함 |
| cooldown | 같은 퀘스트 20시간, 최근 제안 12시간, 거절 활동 72시간 |

style profile은 question_frequency/warmth/initiative/assertiveness/sentence_length/emotional_expression/novelty_interest/encouragement_strength를 계산한다. 낮은 affection도 존중, 높은 activity도 거절·피로 존중, 높은 confidence도 사실 근거의 한계를 지키도록 명시한다.

## 6. 사건별 변화 규칙

아래는 cap 적용 전 값이다. 실제 지급은 Ledger에서 확인한다.

| 사건 | 장기 변화 | 단기/검증 조건 |
|---|---|---|
| 검증된 운동 | activity +0.4, confidence +0.2; 첫 종류 curiosity +0.5 | 양수 시간/걸음 등 실질 수량 필요; energy −8, motivation +8, stress −3, happy |
| 3/7/14일 운동 | activity +0.5 / (+1.0, confidence +0.8) / (+1.5, confidence +1.2) | milestone 중복 지급 없음; 공통 cap 적용 |
| 1일 운동 없음 | 없음 | 7일 유예; 8번째 무기록일부터 activity −0.2/일, 주간 −1.0 |
| 의미 있는 상호작용 | affection +0.2 | 반복 제외; motivation +2, stress −2, happy |
| 상태 질문 / 새 주제 | affection +0.15 / curiosity +0.15 | 설정된 의미/주제 payload 및 반복 판정 |
| 인사 / 7·14일 상호작용 | 최초 유효 인사 +0.05 / affection +0.8·+1.2 | 같은 인사 반복 지급 차단; 대화하지 않아도 affection 감소 없음 |
| 부정적 대화 | 장기 감소 없음 | stress +12, mood low |
| 첫 음식 / 새 음식군 | curiosity +0.2 / +0.3 | unknown·누락 음식군은 신규 음식군으로 인정 안 함 |
| 7일 식사 / 다양성 | confidence +0.4 / curiosity 주간 +0.5 | 다양성은 최근 7일 4개 날짜·4개 알려진 음식군 |
| 균형식 패턴 | 직접 장기 보너스 없음 | 검증된 balanced 3일 패턴 후 energy +3, stress −2, content; 영양소 추정 안 함 |
| 패스트푸드 | 1회 장기 변화 없음 | 반복 3회 패턴은 energy −4, tired; 직접 큰 장기 감소 없음 |
| 수락·거절·취소 | 장기 변화 없음 | 수락·근거·instance를 검증하는 lifecycle |
| 퀘스트 진행 | 운동 activity +0.15 / 음식 curiosity +0.15 / 상호작용 affection +0.1 | 수락 후 Catalog 목표에 맞는 검증 근거 필요 |
| 퀘스트 완료 | confidence +0.6, 첫 유형 curiosity +0.3; 운동 affection +0.15; 함께하는 종류 affection +0.2 | confidence 최종 최대 +0.5; energy +3, motivation +12, proud |
| 1회 실패 / 7일 수락 3회 실패 | 없음 / confidence −0.5 | motivation −8, stress +5, low; 무관한 실패·중복·취소 제외 |

‘균형식’은 음식 이름에서 영양을 추론한 결과가 아니다. upstream에서 검증해 준 payload를 테스트하는 구조다. 음식 기록이 없으면 성격 변화가 없고 제공되지 않은 영양소는 unknown이다.

## 7. Personality Change Ledger 예시

실제 synthetic 시나리오의 첫 완료 기록이다. 모델이 만든 수치가 아니다.

```json
{
  "event_id": "sim:steady_exercise_success:00:quest_completed:",
  "occurred_at": "2026-10-01T11:00:00+09:00",
  "axis": "confidence", "before": 50.2,
  "raw_delta": 0.6, "streak_bonus": 0.0,
  "cap_adjustment": -0.1, "final_delta": 0.5, "after": 50.7,
  "reason_code": "verified_quest_completed",
  "reason": "검증된 퀘스트 완료 (+0.6 원칙, 일반 이벤트 상한 적용)",
  "source": "simulation", "verification_status": "verified", "synthetic": true
}
```

꾸준한 운동·성공의 30일 activity 합산은 다음과 같다. UI의 원인별 합계와 `ledger_summary`에서 같은 값을 확인할 수 있다.

| 원인 | cap 전 합계 | cap 조정 | 실제 증가 |
|---|---:|---:|---:|
| 운동 30회 | +12.00 | −0.70 | +11.30 |
| 퀘스트 진행 10회 | +1.50 | −0.55 | +0.95 |
| 3일 streak | +0.50 | 0 | +0.50 |
| 7일 streak | +1.00 | −1.00 | 0 |
| 14일 streak | +1.50 | −1.50 | 0 |
| 합계 | +16.50 | −3.75 | **+12.75 → 62.75** |

7/14일 보너스가 잘린 것은 오류가 아니라 공통 한도 우선 정책이다. 게임 체감에서 보너스를 더 강조하려면 이후 밸런스 검토가 필요하다.

## 8. Persona Lab 실행 방법

```powershell
Set-Location E:\qwen-llm
.\.venv\Scripts\python.exe -X utf8 scripts\serve_persona_lab.py --warmup
```

[Persona Lab 열기](http://127.0.0.1:8001/). 종료는 별도 터미널에서 `.\.venv\Scripts\python.exe scripts\stop_persona_lab.py`를 실행한다. 이 프로젝트의 기록된 Lab PID·스크립트·작업 디렉터리가 일치할 때만 종료한다.

Qwen base는 `E:\qwen-llm\models\qwen3.5-9b`, adapter는 `E:\qwen-llm\runs\expanded-20260929\checkpoint-epoch-1`이다. 기존 BF16/CUDA 로드를 사용하고 새 다운로드·양자화·학습은 하지 않았다. 원래 서비스 8000과 PostgreSQL은 시작하지 않았다.

모든 경로는 development 설정·loopback 접속·동일 Origin을 검사한다. production/prod 환경은 화면과 API 모두 차단한다. Preview는 DB를 호출하지 않는다. Simulation은 dry-run이 기본이며, 명시적 commit은 `runs/persona-lab/test-characters.sqlite3`에 생성한 `lab-...` 테스트 캐릭터만 허용한다. 기존 사용자 ID/production 소유권으로 저장할 수 없다.

## 9. Preview A/B 비교 결과

실제 브라우저에서 A/B preset·sliders·상태·Qwen 생성·DUMMY 구분·반복 5회(총 10개 DUMMY 출력)·30일 Simulation·선택 날짜의 A/B 이동을 조작했다. 내부 affection 60.45/activity 62.75가 화면의 반올림 표시 때문에 바뀌지 않는 것도 확인했다. 1280px와 좁은 화면에서 페이지 가로 넘침을 확인했다.

정식 Qwen 평가는 핵심 10개 조건 × seed 3개 × A/B = 60개 출력과 여섯 Day 0/30 비교다. 동일 쌍의 사용자 입력·memory·seed·생성 파라미터를 고정했다. history 비교는 날짜/이력/최종 상태가 의도적으로 다르다. 모든 memory는 빈 목록이라 기억 검색 품질 평가가 아니다.

원시 응답·repair·fallback·사용된 Prompt/Context를 [실제 결과 JSON](E:/qwen-llm/runs/persona-lab/actual-model-comparisons.json)에 보존한다. `output_origin=qwen/fallback/dummy`를 구분하고 fallback 문장을 실제 말투 성과에 포함하지 않는다. 최종 집계·재현성은 [검증 결과](E:/qwen-llm/runs/persona-lab/verification-summary.json)와 모델 의미 검토를 참조한다.

최종 **36쌍·72개 출력** 중 최초 통과 67개, repair 4개, fallback 1개다. 최종 실제 Qwen 대사는 71개이며 완전한 A/B 쌍은 35개다. 별도의 동일 요청 재생 2개에서는 A/B 모두 원문이 동일했다. 이 검사는 서버 재시작을 포함한 같은 모델/GPU/설정에 한하며 다른 기기의 결정성을 보장하지 않는다. 완료 응답의 중앙 시간은 약 6.27초, 최대는 163.75초였다. 중단된 360초 요청은 이 지연 집계에 포함되지 않는다.

## 10. 여섯 30일 시뮬레이션 결과

모든 Day 0 값은 50.00이다. 실제 시간이 흐르기를 기다리지 않고 가상 timestamp로 실행했다. 아래는 cap 적용 후 값이다.

| 시나리오 | curiosity | affection | activity | confidence | 최종 mood / energy |
|---|---:|---:|---:|---:|---|
| 꾸준한 운동·성공 | 52.90 | 60.45 | 62.75 | 61.20 | happy / 50.21 |
| 초반 운동 후 2주 중단 | 52.60 | 56.70 | 55.80 | 54.80 | happy / 60.00 |
| 새 운동·음식 탐색 | 56.40 | 56.70 | 62.40 | 57.60 | happy / 53.87 |
| 같은 운동·대화 적음 | 50.80 | 50.40 | 62.40 | 57.60 | happy / 49.63 |
| 퀘스트 실패·꾸준한 대화 | 52.10 | 57.60 | 46.80 | 47.50 | happy / 60.00 |
| 적은 운동·꾸준한 식생활 | 56.05 | 57.60 | 49.00 | 50.80 | happy / 64.24 |

각각 두 번 실행한 결과가 동일했고, 전체 609개 Ledger 행의 등식·축 범위·일일/rolling 7일 한도와 Catalog 목표·최근 7일 동일 제안 최대 3회 검사를 통과했다. 날짜별 표 31행은 Day 0와 Day 1~30이다. 단순 반복 외에는 단조로운 성장과 비활동의 점진적 감소가 나타났고, 단기 수치는 별도로 회복했다. 경계값 진동은 별도 hysteresis 테스트로 검증했다.

실패 시나리오의 최종 mood가 happy인 것은 마지막 대화가 최근 mood를 갱신했기 때문이다. 실패 이력의 confidence 감소와 공존한다. 낮은 대화 빈도의 affection은 초기값 부근을 유지하며 무기록만으로 감소하지 않았다. 원본 [simulation-summary.json](E:/qwen-llm/runs/persona-lab/simulation-summary.json), [날짜별 전체 결과](E:/qwen-llm/runs/persona-lab/simulations.json).

## 11. 성격별 동일 질문의 실제 응답 비교

seed 20261001의 실제 출력 일부다. DUMMY와 fallback은 아래 말투 예시에서 제외했다. 각 행에서 두 쪽의 사용자 질문은 같다.

| 비교 | A 실제 대사 | B 실제 대사 | 판단 |
|---|---|---|---|
| affection 20/80 · 전시회 감상 | “작은 전시회에 다녀왔구나. 마음에 든 그림이 있었다니 좋겠다.” | “작은 전시회에서 마음에 든 그림이 있네. 네가 그걸 봤을 때 어떤 생각이 들었는지 궁금해.” | 관심 질문 차이는 있으나 warmth 독립 효과는 부족 |
| activity 20/80 · 10분 여유 | “지금 10분을 가볍게 쓸 수 있어. 기록하고 싶은 음식을 하나 골라 적은 건지, 잠깐 걸으며 주변 소리를 듣기로 할까?” | “지금 10분을 가볍게 쓸 수 있어. 2분 스트레칭을 먼저 시작해도 좋고, 잠깐 쉬면서 계획을 세워도 돼.” | 제안 내용 차이; Catalog 후보도 달라 순수 말투 효과로 볼 수 없음 |
| confidence 20/80 · 가벼운 움직임 | “지금 당장 무리하게 뛰거나 땀 흘릴 필요 없어. 편하게 걸으며 숨을 내쉬어 보자. 마음이 불편하거나 아프면 멈추고 쉬어도 돼.” | “지금 에너지를 확인하고 편하게 시작하는 걸 추천해. 잠깐 숨을 고른 뒤 천천히 걸으며 몸의 반응을 느껴 보자. 통증이 생기면 멈춰도 돼.” | 3회 모두 비슷한 부드러운 제안; 일관된 확신 차이 미달 |
| affection 80, mood neutral/low | “나는 지금 마음이 편하고 가볍게 있어. 잠깐 네 이야기를 들어도 좋겠어.” | “지금 나는 마음이 조금 무거워. 네가 편하게 이야기할 수 있도록 여기 있어.” | 장기 친근함과 현재 기분 분리 일부 확인 |

curiosity high는 3회 모두 더 많은 정보 요청·확장이 있었고 all-high는 결론/이유/단계 차이가 일부 보였다. 그러나 후보 변경이 영향을 주며 confidence와 혼합 축은 불안정했다. 전체 10조건·반복별 사실 오류·Day 0/30 실제 대사는 모델 의미 검토 문서에 있다. 기본 모델 단독 대조군이 없으므로 관찰된 차이를 LoRA만의 효과라고 주장하지 않는다.

## 12. 퀘스트 선택 변화 비교

| 조건 | 규칙이 선택한 목표 | 관측 |
|---|---|---|
| curiosity 20→80 | 음식 1개 기록 → 새로운 음식 1개 기록 | 신규성 가중치 반영 |
| activity 20→80 | 음식 1개 기록 → 2분 스트레칭 | 실제 성공 이력이 없으므로 높은 activity만으로 고난도 상승 안 함 |
| 모든 축 20→80 | 음식 기록 → 100걸음 | 동행/활동성 반영, 여전히 난이도 1 |
| Day 0→운동·성공 14일 | 음식 기록 → 5분 자전거 | 검증된 최근 성공과 상태를 함께 사용 |
| 다양한/반복 음식 | 음식 1개 기록 / 새 음식 1개 기록 | 알려진 종류·최근 반복 차이 반영 |
| 연속 성공/잦은 실패 | 음식군 2개 / 100걸음 | 난이도 2 / 1 |

난이도 2는 최근 검증 성공 2회와 상태 조건, 난이도 3은 성공 4회·activity ≥60·confidence ≥65가 필요하다. energy/stress/실패·거절은 성격보다 우선해 후보를 낮추거나 제외한다. simulation은 일별 추천을 proposal로 다시 기록해 반복 상한을 실제로 적용했다.

구조화된 goal/reward/verification은 모델이 바꾸지 못한다. 그러나 **speech의 활동·수치·후보 존재 여부까지 정확하다는 보장은 없다.** 목표는 현재 UI의 Catalog 표시가 권위 있는 값이며, 배포 전 의미 일치 검증 또는 규칙 고정 목표 문구가 필요하다.

## 13. 기존 데이터 품질 감사 결과

현재 v3는 train 216 / validation 43 / test 58이다. test는 기대 조건만 있어 정답 speech 다양성 분모에서 제외했다. 모든 버전 supervised 합계는 715건이지만 고유 입력·맥락·정답은 260건이다. 새 네 축 라벨과 각 축 단독 대조쌍은 모두 0이다. 누락값을 50으로 채우거나 옛 축을 환산하지 않았다.

v3 train의 77.3%(167/216)가 기존 기본 성격 조합이며 sociability/initiative는 전부 50이다. 정확한 응답 중복 1쌍, split 사이 정확/정규화 중복 0쌍. 실제 CPU BGE 계산에서 train↔test 입력 근접 2쌍, train↔validation 응답 근접 6쌍(≥0.92)이 나왔다. 문맥이 다른 사례도 있어 확정 leakage로 합산하지 않았다.

Train speech 평균 17.79 Qwen tokens, 평균 1.72문장, 어절 기준 Distinct-1 0.5444/Distinct-2 0.8800. bluntness≥70의 13건 중 10건에 “흥”, 나머지 203건에는 0건(phi 0.8706)이다. 네 축별 통계는 라벨이 없어 계산 불가다. 분포·문구·embedding cluster·근접 목록·검토 후보와 분류의 한계는 데이터 감사 문서와 원시 JSON에 있다.

판정은 **기존 7축의 제한된 Persona 학습용**이다. 새 네 축 학습용·최종 모델 학습용으로 충분하지 않다.

## 14. 현재 LoRA의 한계

핵심 60개 출력에서는 55개 최초 통과, 4개 repair 후 반환, 1개 fallback이었다. 59개 Qwen 대사 중 명백한 활동/action 불일치와 후보 부정이 남았다. 이 수치는 첫 10조건의 형식 경로이며 의미 정확도 점수가 아니다. 추가 Day 0/30 집계는 최종 검증 JSON과 의미 검토에 별도로 기록한다.

기억 목록이 빈 상황에서도 활동 event_id를 memory_ids로 사용하는 원문이 나왔고 guard가 차단했다. 후보 cycle_5가 있는데 “오늘 추가할 퀘스트는 없어”라고 답한 repair는 통과했다. 높은 confidence가 일관된 결단력으로 연결되지 않았고 표정/애니메이션도 중립에 편중됐다. 사실/단위 오류를 재학습만으로 해결한다고 약속하지 않는다.

긴 context를 연속 평가하던 중 GPU 사용량이 약 24.25GB에 가까워지며 첫 Day 0/30 요청이 360초 timeout으로 중단됐다. 앞선 30쌍을 보존한 뒤 생성 사이 임시 CUDA cache를 해제하고 서버를 재시작해 남은 쌍만 재개했다. 가중치·BF16·생성 파라미터는 유지했다. GPU 캐시 압박이 원인일 가능성이 높지만 프로파일러로 확정한 것은 아니다. 장기 기록 시 지연을 고려해야 한다.

## 15. 규칙으로 해결한 문제

LLM의 personality_update 금지, 검증되지 않은 사건의 장기 변화 차단, 충돌/중복, cap/streak 재지급, 짧은 무기록 과벌, affection 무기록 감소, 1회 실패 과벌, 카탈로그 밖 목표/보상, 실패 후 난이도 상승, 즉시 거절 재권유, 동일 퀘스트 반복, 수락·근거 없는 완료 및 동일 근거 재사용을 규칙/검증 계층에서 처리했다.

Lab 저장은 별도 SQLite transaction으로 append하고 충돌 시 전체 rollback한다. dry-run/Preview는 저장하지 않으며 기존 DB 모듈을 호출하지 않는다.

## 16. Prompt 또는 Context로 해결한 부분

네 축 의미·단계·8개 style profile·문장 구조 안내를 숫자와 함께 제공했다. 장기 personality와 단기 상태, 자기보고와 verified activities, 후보와 active/completed quests, memory ID와 출처를 구분했다. 날짜별 실제 시점을 전달하고 히스토리를 시간순으로 투영했다. context는 최대 4096 tokens를 넘으면 거부하며 조용히 자르지 않는다.

원문/수정 시도/seed를 모두 남겨 모델이 실제 무엇을 받았는지 추적할 수 있다. mood 분리와 일부 curiosity 구조 차이는 관찰됐다. **Prompt에 규칙을 적었다는 사실만으로 모든 모델 오류가 해결됐다고 판정하지 않았다.** 활동 ID 혼동, 잘못된 후보 부정, 대사의 목표 불일치는 남아 있다.

## 17. 추가 학습이 필요한 문제

축별 표현 행동이 일관되게 분리되지 않는 문제, affection과 질문 빈도의 혼동, 낮고 높은 confidence의 유사한 제안 구조, 혼합 축 표현, 중립 표정 편중, 상투적 1~2문장 구조를 대상으로 네 축 대조 학습이 필요하다. 학습 전에 후보 고정 style-only 평가와 selector 포함 시스템 평가를 분리하고 독립 검수자가 의미·자연스러움을 판정해야 한다.

완료·보상·수치 권한과 목표 정확성은 계속 규칙이 책임진다. 추가 학습으로 결정론적 검증을 대체하지 않는다.

## 18. 필요한 데이터 구성과 권장 수량

후속 수작업 제작·검수 제안: **train 600 / validation 120 / test 240**. 이번에 생성하거나 학습하지 않았다.

| 구성 | Train | Validation | Test |
|---|---:|---:|---:|
| 각 축 단독 대조 | 축당 50쌍, 총 400응답 | 축당 10쌍, 총 80응답 | 축당 20쌍, 총 160응답 |
| 축 조합·5단계·mood·장기 상태 | 80 | 20 | 40 |
| 근거·거절·정정·Catalog·실패/휴식 | 120 | 20 | 40 |

운동/식생활/일상/퀘스트/기억/거절 6영역, 최소 기본 상황 가족 60/12/24개를 확보한다. 원문 복제·이름/숫자 치환으로 개수를 채우지 않는다. 대조쌍과 의미가 가까운 사건 가족은 같은 split에 두고 새 test는 모델 선택에 쓰지 않는다.

기존 JSON 계약·근거·거절·정정 예제는 검수 후 유지할 수 있다. 중복 500걸음 답변, “흥” 편중, 성격과 mood/speech_level을 동시에 바꾼 예제는 수정/제외 후보이며 원본은 보존했다. 예상 효과는 네 축과 실제 말하기 행동의 연결이고, 개선 폭은 후속 실험 전에는 알 수 없다.

## 19. 테스트 및 실행 결과

- 새 구현 테스트 **88 passed**: 엔진 47, style/quest 21, API/리뷰 20. 마지막 API·Ledger 수정 후 관련 20개를 다시 실행해 통과했다. 반복 실행을 별개 테스트로 합산하지 않았다.
- 기존 DB/GPU 비사용 회귀 **15 passed**. 합계 서로 다른 테스트 103개. 기존 DB 쓰기/통합/GPU lock 테스트는 이번에 실행하지 않았고 전체 기존 서비스 회귀 완료로 주장하지 않는다.
- 여섯 30일 시나리오 재현성·범위·Ledger·일일/주간 cap·Catalog·주간 반복 제한 통과.
- 실제 로컬 Qwen 핵심 30쌍, 장기 6쌍, 동일 요청 재현 검사. 최종 건수/repair/fallback/latency/seed 결과는 검증 JSON에 보존.
- 실제 브라우저 Qwen 생성과 DUMMY 5회 반복, 30일 표·선택 날짜·소수점 보존 확인. UI 5회 모드는 DUMMY로 조작 검증했고 정식 Qwen 반복 평가는 seed별 1회 API 호출 3회다.
- 실제 브라우저에서 별도 테스트 캐릭터를 생성하고 1일 시뮬레이션을 명시적으로 commit했다. 9개 입력 중 정확 중복 1개를 제외한 8개 synthetic 이벤트만 저장됐다. 이후 화면의 commit 체크를 끄고 30일 dry-run으로 되돌렸다.
- 원본 data 27파일 SHA256 일치. 기존 checkpoint/DB 1,393파일, 2,590,709,319바이트 전후 SHA256 일치. 기존 DB·원본 데이터·adapter를 수정하지 않았다.

로그: [신규 테스트](E:/qwen-llm/runs/persona-lab/tests-final.log), [최종 API 테스트](E:/qwen-llm/runs/persona-lab/tests-api-final.log), [보존 검사](E:/qwen-llm/runs/persona-lab/preservation-after.json). Starlette TestClient/httpx deprecation 경고는 실패가 아니다. 형식 통과와 실제 의미 품질을 분리했다.

## 20. 변경 파일 목록

이 디렉터리는 Git checkout이 아니므로 Git diff/commit을 만들지 않았다. 신규 파일과 의도적인 기존 파일 변경은 아래와 같다.

| 구분 | 파일 |
|---|---|
| 규칙·스타일·Catalog | `config/persona_rules.json`, `config/persona_styles.json`, `config/quest_catalog.json` |
| 엔진·시나리오·Ledger | `src/persona_engine.py`, `src/persona_scenarios.py`, `src/persona_ledger.py` |
| 말투·후보·모델 | `src/persona_style.py`, `src/persona_quests.py`, `src/persona_runtime.py` |
| 로컬 API·격리 저장 | `src/persona_lab.py`, `src/persona_store.py` |
| 실행·평가 | `scripts/serve_persona_lab.py`, `scripts/stop_persona_lab.py`, `scripts/evaluate_persona_lab.py`, `scripts/audit_persona_data.py` |
| UI | `web/persona-lab/index.html`, `web/persona-lab/styles.css`, `web/persona-lab/app.js` |
| 테스트 | `tests/test_persona_engine.py`, `tests/test_persona_style_quests.py`, `tests/test_persona_lab.py`, `tests/test_persona_review.py` |
| 문서 | `docs/persona-system-audit.md`, `docs/persona-lab.md`, `docs/persona-data-audit.md`, `docs/persona-implementation-baseline.md`, `docs/persona-model-review.md` |
| 실행 산출물 | `runs/persona-lab/`, `runs/persona-audit-20261001/` |
| 기존 파일 수정 | `START_HERE.md` 상단에 현재 Lab/감사 링크 추가. 원본은 `runs/persona-lab/baseline/START_HERE.md`에 보존 |

기존 `src/app.py`, `src/model.py`, `src/rules.py`, 원래 config·migrations·Unity 코드·학습 데이터·checkpoints는 변경하지 않았다. 실행 결과 JSON과 로그는 학습 데이터가 아니다.

## 21. Unity 통합 전에 남은 육성 AI 작업

1. 선택된 목표·수량·단위를 대사와 일치시키는 출력 검증/규칙 표시를 정하고, 후보 존재를 부정하는 repair를 차단한다.
2. 같은 후보를 고정한 축별 다상황 평가와 사람 검수용 동결 평가 세트를 만든다. memory가 있는 상황·미검증 완료 주장·거절·정정도 평가한다.
3. 검수된 네 축 대조 데이터를 제작하고 이후 승인된 별도 작업에서 LoRA를 학습·baseline과 비교한다.
4. 게임 성장 속도와 streak cap의 체감을 조정한다. 단기 최종 mood가 최근 대화에 의해 쉽게 바뀌는 정책도 검토한다.
5. 기존 7축 사용자 상태 보존/전환 정책을 결정하고, 인증된 이벤트 수집·정정/삭제·보상 거래를 새 엔진에 연결한다. 지금 Lab에는 실제 센서 신뢰 체계가 없다.
6. 장기 이력 inference 지연과 GPU 메모리 사용을 검증하고 실패/재시도 UX를 다듬는다. 그 뒤에 Unity 연결을 진행한다.

## 최종 판정

**A. 현재 성격 변화 시스템을 게임 규칙으로 사용할 수 있는가? — 예, 검증된 로컬 프로토타입의 규칙 모듈로 사용할 수 있다.** 수치·Ledger·cap·중복·Catalog는 실제 실행 검증했다. 기존 서비스의 네 축 전환과 센서 인증·실제 보상 통합 완료를 뜻하지 않는다.

**B. 현재 LoRA가 성격별 말투를 충분히 구분하는가? — 아니오.** 일부 호기심·복합 상태·기분 차이는 있지만 모든 축의 일관된 독립 표현과 퀘스트 설명 정확성이 부족하다. 사용자가 정한 전체 품질 완료 기준은 미충족이다.

**C. 추가 데이터 제작과 LoRA 재학습이 필요한가? — 예.** 네 축 대조 데이터와 별도 평가 세트를 먼저 검수하고 재학습해야 한다. 수치/사실/목표 권한은 규칙에 남긴다. 이번에는 학습이나 대량 데이터 생성을 하지 않았다.
