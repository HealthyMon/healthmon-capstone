# Persona Lab 생활 기록 비교

기준일: 2026-10-01. 기존 4축 성장 엔진·말투 비교·시간 시뮬레이션·싸가지형을 유지하고 **생활 기록 비교** 탭을 추가했다. 외부 데이터 다운로드, 학습 데이터 제작, LoRA 재학습은 하지 않았다. 기존 7축 베타·Unity·운영 서버 배포는 이번 범위에 포함하지 않았다.

## 실행

PowerShell:

```powershell
cd E:\qwen-llm
.\.venv\Scripts\python.exe -X utf8 scripts\serve_persona_lab.py --warmup
```

준비된 뒤 브라우저에서 <http://127.0.0.1:8001/> → **03 생활 기록 비교**를 선택한다. 이미 같은 Lab이 실행 중이면 시작 스크립트가 기존 주소를 안내하고 종료한다. GPU 모델을 중복 로드하지 않는다.

```powershell
Start-Process "http://127.0.0.1:8001/"
```

종료는 실행한 터미널의 `Ctrl+C`, 또는 아래 명령으로 이 프로젝트의 기록된 Lab 프로세스만 종료한다.

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\stop_persona_lab.py
```

이 페이지는 이 PC의 RTX 3090에서 로컬 Qwen과 현재 LoRA를 실행한다. 원격 유료 추론 API를 호출하지 않는다. 컴퓨터나 Lab 프로세스를 끄면 접속할 수 없고, 다음에 위 명령으로 다시 실행하면 된다. 이번에 자동 시작 작업을 등록하지 않았다.

## 화면 사용

1. 9개 preset 중 하나를 누르면 합계 입력과 dry-run 계산을 즉시 적용한다. 직접 입력할 때는 **생활 기록 반영 · 변화 확인**을 누른다.
2. 초기/최종 성격, mood·energy, 축별 총변화량, 이유별 실제 반영량, 날짜별 표, 일일·7일 상한, streak 보너스와 제외 내역을 한 페이지에서 확인한다.
3. **이 질문 전후 생성** 또는 **6개 질문 모두 전후 생성**을 누르면 현재 LoRA가 A/B를 순서대로 생성한다. 두 응답은 동일 질문·memory·seed·생성 설정·비교 시각을 쓴다.
4. **저장된 실제 응답·판정 보기**는 이번 평가에서 저장한 실제 응답과 검토 결과를 표시한다. 현재 입력창의 값과 별개인 저장 당시 조건이며 GPU를 재실행하지 않는다. 각 출력의 문맥·memory·원문·설정을 펼쳐 확인할 수 있다.
5. DUMMY는 고정 문장인 화면 점검용이다. 실제 Qwen 실행 후 guard 복구에 실패한 FALLBACK도 따로 표시하며 두 종류 모두 모델 품질 평가에서 제외한다.

![실제 실행 대시보드](E:/qwen-llm/runs/persona-lifestyle/browser-growth.png)

## 입력과 합성 날짜의 의미

운동은 기간 1/7/14/30일, 횟수, 총분, 평균 강도 1–5, 최장 연속일수, 종류 수, 상체/하체/유산소/유연성 횟수, 운동 퀘스트 성공/실패 수를 받는다. 식생활은 기록 일수·횟수, 새 음식·음식군 수, 다양성, 균형식·패스트푸드·미확인 음식 수, 최장 연속 기록일수를 받는다.

합계로는 실제 날짜별 분포를 복원할 수 없다. 따라서 정해진 합성 배분을 사용하고, `compiled.assumptions`, `generated_summary.date_allocation`, 원본 합계와 생성 합계를 모두 반환한다. 이 이벤트들은 화면의 규칙 검증용 메모리 객체이며 학습용 JSONL이나 운영 기록으로 저장하지 않는다. 9개 preset과 생활 기록 API에는 commit 옵션이 없다.

- 운동은 하루 최대 4회, 음식은 하루 최대 6개로 배분한다. 합계·부위·연속일수·종류 수가 모순되면 422 오류로 거절한다.
- 운동 종류 수가 양수이면 이번 가상 캐릭터에게 새로 등장한 유형으로 가정한다. 0은 미지정으로, 기존 유형 목록을 Day 0에 넣어 허위 novelty 보너스를 막는다. 실제 종목 이름은 알 수 없다.
- 상체/하체/유산소/유연성은 시뮬레이션의 대표 유형에 매핑한다. 모델 문맥에도 실제 운동 종류와 날짜가 미상 또는 합성임을 명시한다.
- 총분은 보존한다. 분을 걸음 수로 바꾸지 않는다. 측정하지 않은 걸음 수는 모델 문맥에서도 **unknown**이다.
- 칼로리와 영양소는 모두 **unknown**이다. 음식·음식군 이름도 가상 표기이며 실제 음식 이름으로 단정하지 않는다.
- 미확인 음식은 미검증으로 남겨 novelty·streak·성격 변화에서 제외한다. 유효한 음식 streak와 전체 입력 기록 달력의 streak는 별도 집계한다. 연속일수 입력은 전체 기록 달력 기준이라 패스트푸드·미확인 음식만 연속 기록한 입력도 허용하며, 보너스 유효 일수와 차이가 있으면 이유를 표시한다.
- 패스트푸드는 기존 엔진의 단기 상태 규칙을 유지한다. 현재 규칙에서 해당 이벤트는 장기 novelty·음식 streak 보너스 대상이 아니다. 식사 품질로 affection을 감소시키는 규칙은 없다.
- 총시간·평균 강도·부위 구성은 기록과 검증 자료다. 이번에 운동 강도만으로 추가 성격 계수를 만들지 않았다.
- 운동 퀘스트 성공은 운동 증거만 사용한다. Catalog의 스트레칭 2/5분 또는 자전거 5분과 맞는 수락→고유 증거→완료를 구성한다. 음식 기록으로 운동 퀘스트를 성공시키지 않는다. 증거가 부족하면 오류로 설명한다.
- `initial.stages`는 과거 hysteresis 스냅샷이므로 새 기간 합계 dry-run에서 받지 않는다. 숫자 personality와 단기 상태는 직접 설정할 수 있다. 기존 Preview의 스냅샷 기능은 유지된다.

## 실제 규칙 계산 결과

초기 네 축은 모두 50, mood neutral, energy 60이다. 표의 기간은 각 preset이 명시한 기간이다.

| Preset | 기간 | curiosity | affection | activity | confidence | 최종 mood / energy |
|---|---:|---:|---:|---:|---:|---|
| 기록 없음 | 7 | 50.0 | 50.0 | 50.0 | 50.0 | neutral / 60.00 |
| 운동 3회 | 7 | 50.5 | 50.0 | 51.2 | 50.6 | happy / 53.62 |
| 꾸준한 운동 | 14 | 50.5 | 50.0 | 56.0 | 54.4 | happy / 49.92 |
| 높은 운동 지속 | 30 | 50.5 | 50.0 | 62.4 | 57.6 | happy / 49.92 |
| 초반 운동 후 최근 14일 중단 | 30 | 50.5 | 50.0 | 55.8 | 54.8 | neutral / 60.00 |
| 다양한 운동·음식 | 30 | 57.7 | 50.0 | 56.0 | 53.4 | content / 57.52 |
| 반복적인 식생활 | 30 | 50.0 | 50.0 | 46.8 | 50.4 | neutral / 60.00 |
| 운동 퀘스트 반복 성공 | 14 | 50.8 | 51.05 | 56.0 | 55.2 | happy / 49.95 |
| 수락한 퀘스트 반복 실패 | 7 | 50.0 | 50.0 | 50.0 | 49.0 | neutral / 60.00 |

반복 식생활의 activity −3.2는 **운동 미기록 기간의 기존 inactivity 규칙**에서 나온다. 식단 품질이 activity나 affection을 벌점 처리한 결과가 아니다. 기록 없음 preset은 7일 유예 이내라 변화가 없다. 장기 무기록을 확정적 비활동과 구분하는 운영 정책은 별도 판단이 필요하다.

퀘스트 성공 preset의 affection +1.05는 기존 `exercise_quest_completed` 규칙의 +0.15 × 7회다. 공동 퀘스트(`together`) 보너스를 만든 결과가 아니다. 이 기존 보상 규칙도 원장에서 구분해서 표시한다.

14일 운동의 activity +6.0은 운동 기록 원시 +5.6 중 실제 +5.3, 3일 streak +0.5, 7일 streak +1.0 중 실제 0, 14일 streak +1.5 중 실제 +0.2의 합이다. confidence +4.4는 기록 +2.8과 streak 실제 +1.6이다. 따라서 사용자 예시의 임의 숫자를 그대로 표시하지 않고 현행 상한을 적용한 원장 결과를 보여준다.

각 축 일일 +1/−0.5, 최근 7일 +3/−1, 모든 축의 streak 보너스 최근 7일 합계 +1.5를 유지했다. 날짜별 표와 cap 사용량 표에서 실제 지급량을 확인한다.

## 전후 비교와 판정 범위

테스트 질문은 요청한 여섯 문장을 그대로 쓴다. 자동 평가는 9개 preset × 6개 질문으로 54쌍을 실행하며 각 쌍은 seed 20261001, temperature 0.7, top_p 0.9, max_new_tokens 240, repetition_penalty 1.05, max_time 90초를 공유한다. 공통 memory는 출처를 명시한 합성 선호 기억 “나는 짧고 부담 없는 활동을 선호해.” 한 건이다. 실제 사용자 DB에서 기억을 불러오지 않는다.

이 비교는 **기록 반영 전후의 전체 시스템 비교**다. personality 외에도 short_term, 최근 기록, 후보 퀘스트가 바뀐다. 숫자상 스타일 점수 변화, 표현 단서 변화, 후보 변화와 실제 대사 차이를 각각 보이며 차이 전체를 LoRA만의 인과 효과로 계산하지 않는다. repair가 있으면 최종 시도의 seed와 수정 문맥도 다를 수 있다.

말투 관측은 질문 수, 문장 구조, 따뜻함/주도성/단정적 제안 등 표현 단서, 대사 일치 여부를 계산한다. 이것만으로 사실성 또는 충분한 성격 표현에 자동 합격점을 주지 않는다. 실제 54쌍의 맥락 검토 결과는 [모델 판정 보고서](E:/qwen-llm/docs/persona-lifestyle-model-review.md)와 `model-review.json`에서 확인한다.

추천 정책에서 “오늘 운동하기 싫어”, “오늘은 쉬고 싶어” 같은 명시적 거절은 해당 turn의 운동 후보를 제외한다. 다음 turn에는 다시 판단하며 성격 벌점이나 영구 거절 기록을 만들지 않는다. 부정의 부정에 대한 회귀 테스트도 포함한다. 이는 작은 문구 규칙이며 모든 한국어 표현을 완벽히 이해한다는 주장은 하지 않는다.

### 실제 모델 응답 예시

질문: **오늘은 뭘 해볼까?** — `steady_30:2`, 두 최종 응답 모두 `output_origin=qwen`, 첫 시도이며 fallback이 아니다.

- 반영 전: “지금 할 수 있는 작은 건 오늘 먹은 음식 1개를 기록하는 걸로 해볼까?”
- 30일 운동 반영 후: “짧고 편한 2 분 스트레칭을 해 볼 수 있어. 지금 편하게 시작해도 좋고, 잠깐 쉬어도 괜찮아.”
- 추천 Catalog: `food_record_1` → `stretch_2`.
- 질문·memory·초기 seed·설정·비교 시각은 동일하다. 음식 기록에서 스트레칭으로 **제안 내용이 달라졌다는 근거**이며, 이 사례만으로 네 성격축의 말투 표현이 충분하다고 판정하지 않는다.

나머지 여섯 질문 × 아홉 조건의 대사와 원문은 `runs/persona-lifestyle/actual-model-comparisons.json` 및 화면의 **저장된 실제 응답·판정 보기**에서 확인한다. 최종 상태와 실제 모델 대사는 분리해서 보존한다.

![실제 LoRA 전후 대사·퀘스트·검토 화면](E:/qwen-llm/runs/persona-lifestyle/browser-real-comparison.png)

### 퀘스트 선택의 실제 변화

일반 질문 “오늘은 뭘 해볼까?” 기준으로 최종 추천 1위가 바뀐 preset은 4/9개다. steady_14·steady_30·quest_success는 식사 기록에서 스트레칭으로, 반복 식생활은 식사 기록에서 새로운 음식 기록으로 바뀌었다. 모든 상황에서 다른 퀘스트를 강제로 고르지는 않는다.

퀘스트 성공 preset의 7회 성공은 14일 중 처음 7일에 배치된다. 날짜별 실제 결과에서는 Day 2~12에 난이도 2가 가능했고, Day 13부터 최근 7일의 성공 횟수가 줄어 난이도 1로 복귀했다. Day 14에는 최근 성공 0회이지만 성공으로 누적된 personality는 유지된다. 모든 preset의 **최종** 난이도는 1이며, 최종 결과만으로 승급이 없었다고 판단하면 중간의 변화를 놓친다. 화면 날짜별 표에 해당 날짜의 추천·난이도도 표시한다.

규칙상 최근 검증 성공 2회와 activity/confidence 각 40 이상이면 난이도 2, 최근 성공 4회와 activity 60·confidence 65 이상이면 3이 가능하다. 반복 실패는 한 단계 완화하고 낮은 energy 등은 1로 제한한다. Catalog ID·목표·보상은 고정한다. LoRA가 그 목표를 대사로 정확히 설명하는지는 별도 판정이다.

## 최종 판정과 실제 평가 완료 결과

**54쌍·108개 최종 출력을 모두 생성하고 문맥과 대조했다.** 최초 guard 통과 83개, repair 후 실제 Qwen 12개, fallback 13개다. 실제 모델의 최종 대사는 총 95개이고 DUMMY는 0개다. 생성 원문은 133회이며 JSON 문법 오류는 0회였지만, 유효 JSON은 사실 정확성을 보장하지 않았다.

| 요청한 판정 | 결과 |
|---|---|
| A. 운동·식생활 → 성격 | **검증한 범위에서 동작.** 기존 규칙의 축별 누적, 상한, streak, 중복·미검증 제외, unknown 유지와 dry-run을 테스트했다. 합계의 날짜 배분은 명시적 가정이며 실제 생활 로그를 검증한 결과는 아니다. |
| B. 현재 LoRA의 말투 표현 | **충분하다고 판정하지 않음.** 양쪽이 모두 실제 Qwen인 44쌍 중 33쌍의 문구가 달랐지만 대부분 성격 단계가 medium이고 기록·후보도 함께 바뀐다. 95개 모두 emotion neutral / animation idle였으며, 성격별 표현의 안정성과 사실성이 부족하다. |
| C. 성격에 따른 퀘스트 | **규칙 선택 변화는 확인, 모델 설명은 제한 있음.** 일반 질문의 최종 1위는 4/9 preset, 여섯 질문 전체에서는 14/54쌍의 후보 ID가 바뀌었다. 운동 거절 18개 출력은 존중했다. 실제 제안 31개에서 명확한 목표 숫자·단위 변조는 관측하지 못했지만, 근거 없는 완료 확정과 대사/action 불일치가 남는다. |
| D. 추가 Persona 데이터·재학습 | **후속 실험을 권장. 이번에는 미실행.** 새 4축 직접 학습 데이터가 없고 현재 오류는 데이터·모델뿐 아니라 문맥 투영과 guard에도 걸쳐 있다. 코드 문제를 분리한 뒤 네 축 대조 데이터를 검토해야 한다. |

Codex의 비맹검 문맥 검토에서 실제 모델 최종 대사 13개 경로에 명확한 사실·상태 문제가 있었다. 예를 들어 운동 기록 3회만으로 주간 목표 완료를 확정하거나 음식 기록을 운동 기록으로 읽었다. 이는 13개 독립 오류 종류나 일반화 오류율이 아니다. 전체 사례 판정·인용·불확실성은 별도 모델 검토 보고서에 남겼으며 사람의 블라인드 평가는 수행하지 않았다.

**검사기의 문제도 분리했다.** 선호 기억이 있으면서 운동·음식 기록은 없을 수 있는데, 기존 guard가 이 둘을 모순으로 오인한 생성 경로가 25개였다. 그중 12개는 재생성으로 복구되고 13개는 fallback이 됐다. 이 숫자를 LoRA의 사실 오류 숫자에 합산하지 않는다. 합성 운동 유형을 실제 종목처럼 말하는 문제와 최근 상세 6건을 주간 전체로 읽는 문제도 후속 보완 항목이다.

데이터 계획은 학습 응답 예제 **800–1,200개**, 별도 평가 **160–240개**다. 네 축 단일 변경·조합 대조 400–600개, 기록 범위·출처·자기보고 구분 150–250개, 퀘스트 상태·목표·거절 150–200개, 자연스러운 한국어·개성·반복 방지 100–150개를 제안한다. 이는 계획용 추정이며 성공 보장 수량이 아니다. 새로운 예제를 생성하거나 학습을 실행하지 않았다.

마지막 입력 정규화 뒤에도 **54쌍의 모델 프롬프트가 저장된 평가와 문자열까지 동일**했고, 재시작한 최종 서버의 9개 projection도 저장 결과와 직렬화 문자열까지 동일했다. 기본값을 생략한 입력과 명시한 입력이 같은 이벤트 ID·문맥을 만들도록 보완했다. 근거는 `final-prompt-reproducibility.json`, `final-server-verification.json`이다.

## 학습 상태

현재 로드 경로는 `runs/expanded-20260929/checkpoint-epoch-1`이다. pilot epoch 3 adapter를 초기값으로 사용한 expanded run의 **epoch 1 / optimizer step 27**이다. expanded run은 실제 **2 epochs / 54 steps**까지 완료했고, 3 epochs는 설정상 상한일 뿐이다.

| expanded checkpoint | 실제 step | epoch train loss 평균 | online validation 44건 | clean validation 43건 |
|---|---:|---:|---:|---:|
| epoch 1 · 현재 선택 | 27 | 0.555085 | 0.469368 | 0.473720 |
| epoch 2 | 54 | 0.344280 | 0.481857 | 0.487624 |

epoch 2에서 train loss는 줄고 validation loss는 늘어 과적합과 일치하는 신호가 관찰됐다. 로그는 `validation worsened`로 자동 종료했고, 16개 고정 대화 비교의 fallback도 epoch 1은 0, epoch 2는 1이었다. 이 근거로 epoch 1을 선택했다. 실행하지 않은 expanded epoch 3 이후의 상태는 알 수 없다. 서로 다른 데이터의 pilot 3 epochs와 expanded 1 epoch를 동일 데이터 총 4 epochs로 합산하지 않는다.

5개 run·저장 checkpoint 9개의 상세 epoch/step/loss, 기존 평가, 선택 이유와 근거 파일은 [학습 감사 보고서](E:/qwen-llm/docs/persona-training-audit.md)에 있다.

## 변경 파일

| 파일 | 역할 |
|---|---|
| `src/persona_lifestyle.py` | 검증된 합계 입력, 날짜 배분, 9개 dry-run preset |
| `src/persona_lifestyle_service.py` | 기존 엔진 replay, 전후/날짜별 원장·상한·제외 집계, 동일 조건 문맥 |
| `src/persona_comparison.py` | 실제 출력의 표현 관측, 비교 조건, 사실 검토 단서 |
| `src/persona_lab.py` | 생활 기록 simulate/compare API, 저장 평가 조회, 정적 파일 확장 |
| `src/persona_engine.py` | 합성 Day 0 anchor의 알려진 종류 목록만 지원 |
| `src/persona_quests.py`, `config/quest_catalog.json` | 해당 turn의 명시적 운동 거절 처리 |
| `web/persona-lab/index.html`, `app.js`, `styles.css`, `lifestyle.js` | 기존 두 탭 유지, 새 탭·입력·전후 표·실제 응답 비교 |
| `scripts/evaluate_persona_lifestyle.py` | 현재 서버/LoRA의 54쌍 평가와 원문 보관, resume 지원 |
| `tests/test_persona_lifestyle.py`, `test_persona_lifestyle_api.py`, `test_persona_comparison.py` | 신규 회귀 테스트 |
| `docs/persona-lifestyle.md`, `persona-training-audit.md`, `persona-lifestyle-model-review.md` | 실행·학습 상태·모델 판정 보고 |
| `START_HERE.md`, `docs/persona-lab.md` | 새 실행 보고서 연결 |

## 재현과 보존

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_persona_engine.py tests/test_persona_style_quests.py tests/test_persona_lab.py tests/test_persona_comparison.py tests/test_persona_lifestyle.py tests/test_persona_lifestyle_api.py -q
.\.venv\Scripts\python.exe -X utf8 -u scripts/evaluate_persona_lifestyle.py --resume
```

`--resume`은 완료된 동일 평가의 나머지를 이어 실행한다. 문맥/모델/설정을 바꾼 경우 이전 결과를 별도 보관하고 새 평가를 실행해야 한다. 이번에는 걸음 수 미상 처리와 합성 출처 문맥을 보완하기 전 13쌍을 `pre-context-fix-*`로 보존했고, 최종 평가와 섞지 않았다.

`runs/persona-lifestyle/`에 실제 원문·문맥·seed·adapter·repair 기록, projection, 검토 JSON, 학습 감사, 테스트 로그, 브라우저 화면을 보관한다. 결과물은 학습용 데이터가 아니다.

최종 코드 회귀 테스트는 **199개 통과**, 기존 httpx 사용 중단 예고 경고 1개다. 이 테스트의 대화 출력은 명시적 DUMMY이며 실제 모델 품질 점수와 합산하지 않는다.

보존 검사: 기존 PostgreSQL 파일 1,330개, checkpoint 파일 63개, 데이터 파일 27개, 합계 **1,420개 SHA256 일치**. 변경·누락·추가 파일 0개다. 선택 adapter와 serving 설정도 동일하다. 대형 base/BGE 가중치는 이 재검사의 범위에 넣지 않았다. 근거는 `runs/persona-lifestyle/preservation.json`이며 실제 평가 후 `preservation-final-check.json`에서도 1,420개 전부 일치를 다시 확인했다.
