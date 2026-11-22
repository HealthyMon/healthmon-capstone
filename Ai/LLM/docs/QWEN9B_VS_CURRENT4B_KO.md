# 기존 9B와 현재 4B 비교

2026-11-11. 기존 폴더의 기록과 현재 모델의 실측을 대조했다. **동일 조건의 두 모델 실행 비교는 미완료**다.

## 실행 자료 확인

기존 폴더: `C:\Users\user\Desktop\기존  LLM\healthmon-capstone-main\healthmon-capstone-main\Ai\LLM`.
이 폴더에는 코드·데이터·보고서가 있으나 `models`와 `runs`가 없다. 설정의 원본 경로 `E:\qwen-llm\models\qwen3.5-9b`도 이 PC에 존재하지 않는다. Desktop의 어댑터 설정 파일 검색에서 기존 9B 체크포인트를 찾지 못했다. 현재 확인한 Hugging Face 캐시에도 9B가 없다. 따라서 과거 보고서의 모델을 다시 실행했다고 주장하지 않는다.

현재 모델: `qwen4b-axis-priority-v1/checkpoint-epoch-2`. 서버가 로드한 어댑터 checksum과 교체 기록이 일치한다. 아래 현재 수치는 직전 최종 비교의 합성 요청 24건을 재집계한 것으로, 이번에 다시 측정한 값은 아니다.

## 측정치와 구성

| 항목 | 기존 Qwen3.5-9B | 현재 Qwen3.5-4B |
|---|---|---|
| 선택 LoRA | expanded-20260929 / epoch 1 | axis-priority-v1 / epoch 2 |
| 기록 GPU | RTX 3090 24GB | RTX 4070 Ti 12GB |
| 학습 방식 | BF16 LoRA, rank 8 | NF4 QLoRA, BF16 compute, rank 8 |
| 현재 추론 방식 | 과거 BF16 기록 | NF4 로드 후 BF16 복원·LoRA 병합, vision 제거, FLA |
| 응답 시간 중앙값 | 5.813초 | 3.508초 |
| 응답 시간 최댓값 | 8.844초 | 4.125초 |
| 응답 시간 평균 | 해당 요약에 없음 | 3.509초 |
| 응답 시간 최솟값 | 해당 요약에 없음 | 2.985초 |
| 시간 측정 대상 | 과거 HTTP 흐름 중 모델 요청 9턴의 model latency | 현재 GPU gateway HTTP 요청 24건의 왕복 시간 |
| 형식 오류 | 과거 확장 모델 시험 58건 중 JSON 0, schema 0 | 현재 시험 24건 중 요청/계약 오류 0 |
| 한국어·말투 | 과거 원문 tone 오류 6/58 | 어색한 어휘·존대 혼합·영어/한자 혼입 관찰 |
| 기억·사실 | 과거 원문 memory_fact 오류 4/58 | 차 변경 사실 회상 성공 1건, 다른 문장에서 근거 없는 추측 관찰 |
| 활동성·주도성 | 동일한 현재 3축 시험 결과 없음 | 활동성 3/3쌍, 주도성 3/3쌍 구분 관찰 |
| 마지막 추가 학습 데이터 | 216건, 실제 2 epochs, 54 updates; epoch 1 선택 | 352건, 2 epochs, 88 updates; epoch 2 선택 |
| 마지막 학습 실행 시간 | 기록상 1,395.66초, 약 23.3분 | loading~complete 4,168.15초, 약 69.5분 |

응답 시간의 측정 경계, GPU, 문장, 출력 길이, 프롬프트, 후처리와 생성 설정이 다르다. 따라서 표의 숫자로 ‘4B가 몇 % 빠르다’거나 ‘9B보다 정확하다’는 결론을 내릴 수 없다. 학습 시간도 데이터량·토큰 길이·양자화·GPU가 달라 효율 비교가 아니다. 두 형식 시험의 100%도 동일 시험에서의 동률을 의미하지 않는다.

기존 평가의 의미 오류 범주는 겹칠 수 있다. 오류 수를 합산해 정확도를 산출하지 않는다. 현재는 전체 품질 정확도 라벨을 매기지 않았다. 현재 8,411,502,592 bytes는 로드 모델 파라미터 용량이며 실제 전체 VRAM peak가 아니다. 과거 21.38 GiB는 학습 peak이므로 두 수치를 메모리 절감률로 비교하지 않는다.

## 판단

현재 4B는 실제 서버에서 약 3~4초 응답하며 제한된 시험에서 활동성·주도성 제어를 확인했다. 문장 자연스러움과 사실 보존은 아직 부족하다. 기존 9B에도 말투·기억·퀘스트 오류가 기록돼 있어 크기만으로 품질 우위를 단정할 수 없다. 현재 자료만으로 품질 동등성이나 속도 향상률은 판정할 수 없다.

공정한 직접 비교에는 기존 `models/qwen3.5-9b` 전체와 `runs/expanded-20260929/checkpoint-epoch-1`의 학습된 LoRA가 필요하다. 기본 9B만 다운로드하면 사용자가 쓰던 학습 모델의 비교가 아니다. 원본 9B BF16 전체 가중치는 약 19.3GB로 기록돼 있으므로 현재 12GB GPU에서는 그대로 GPU에 올리는 조건이 맞지 않는다. 동일 GPU에서 둘 다 같은 양자화로 비교하는 모델 비교와 실제 배포 방식 비교를 분리해야 한다. 9B에만 CPU offload를 적용해 얻은 시간을 모델 크기만의 차이라고 해석해서는 안 된다.

## 근거 파일

- 기존: `config/serving.json`, `config/qwen3.5-9b.json`, `IMPROVEMENT_STATUS.json`, `FINAL_STATUS.json`, `docs/IMPROVEMENT_RESULTS.md`.
- 현재: `runs/qwen4b-axis-priority-v1/config.json`, `metrics.jsonl`, `parameter-comparison.json`, `promotion.json`.
- 현재 실응답 검토: `docs/QWEN4B_AXIS_PRIORITY_RESULT_KO.md`.

기존 파일 및 현재 서버 설정은 변경하지 않았다.
