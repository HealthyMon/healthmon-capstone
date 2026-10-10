# 학습 상태와 체크포인트 감사

감사일: 2026-10-01. 작업 경로: `E:\qwen-llm`.

**현재 기본 선택은 `runs/expanded-20260929/checkpoint-epoch-1`이 맞다.** 이 체크포인트는 expanded run의 **epoch 1 / optimizer step 27**이며, 기존 pilot epoch 3 adapter에서 새 optimizer로 추가 학습한 결과다. expanded run 자체는 계획 상한 3 epochs 중 **2 epochs / 54 updates**를 실제 완료한 뒤 검증 loss 악화로 종료됐다. 가장 나중에 저장한 epoch 2 대신 epoch 1을 선택했다.

이는 “base에서 학습을 딱 1 epoch만 했다”, “전체 프로젝트가 같은 데이터로 9 epochs 학습됐다”, “expanded를 3 epochs 완료했다”는 뜻이 아니다. 데이터·초기화·optimizer가 다른 run들을 합산한 총 epoch 숫자를 사용하지 않는다.

## 이번에 실제 확인한 것

- 5개 run의 `config.json`, `metrics.jsonl`, `selection.json`, trainable parameter 메타데이터와 저장 checkpoint 9개를 직접 조사했다.
- `optimizer.pt` ZIP의 `data.pkl` 항목에서 `pickletools`로 **epoch/steps 정수 opcode만** 확인했다. pickle을 실행하거나 torch.load를 호출하지 않았고, tensor storage나 safetensors 가중치 수치를 로드하지 않았다.
- 저장된 epoch/steps, 로그의 update 수, validation 시점, checkpoint 디렉터리 이름이 **9개 모두 일치**했다.
- clean validation, checkpoint 대화 비교, 최종 58건 비교의 원시 결과와 기존 판정을 구분해 읽었다. 새로운 모델 추론을 실행하지 않았다.
- 학습·데이터 생성·다운로드·GPU·DB 작업을 하지 않았다. 기존 파일을 수정하지 않고 이 문서와 `runs/persona-lifestyle/training-audit.json`만 새로 작성했다.

기계 판독 결과에는 56개 근거 파일의 SHA256, 로그 줄 번호, optimizer metadata의 byte offset, 전체 정밀도의 loss가 있다: [training-audit.json](E:/qwen-llm/runs/persona-lifestyle/training-audit.json).

## Run별 실제 수행량

여기서 epoch는 **각 run의 데이터 한 바퀴**, step은 **그 run에서 optimizer.step이 실행된 횟수**다. batch=1, gradient accumulation=8이며, 마지막 불완전 묶음도 1 update로 처리한다.

| Run | 사용 데이터/실제 train·validation | 시작 adapter | 설정상 epoch 상한 | 실제 완료 epoch | sample 방문 | optimizer updates | 종료 기록 |
|---|---|---|---:|---:|---:|---:|---|
| smoke-20260929 | pilot_v2 부분집합 8/2 | config에 init 기록 없음 | 1 | 1 | 8 | 1 | complete |
| pilot-20260929 | pilot_v2 34/8 | 새 LoRA; pipeline 명령에 resume 없음 | 3 | 3 | 102 | 15 | complete |
| improved-smoke-20260929 | improvement_v1 부분집합 8/2 | pilot epoch 3 | 1 | 1 | 8 | 1 | complete |
| improved-20260929 | improvement_v1 96/16 | pilot epoch 3 | 3 | 2 | 192 | 24 | **stop_requested**, epoch 2 저장 뒤 complete |
| expanded-20260929 | improvement_v2 216/44 | pilot epoch 3 | 3 | 2 | 432 | 54 | **early_stop**, validation worsened, complete |

pilot와 첫 smoke의 config에는 `data` 필드가 없지만, 보존된 data_manifest의 train/validation SHA256이 실제 pilot_v2 파일과 일치한다. 첫 smoke의 정확한 초기화 인자는 config에 저장되지 않았으므로 추정값을 확정 메타데이터처럼 채우지 않았다. 보존된 당시 스크립트는 기본값에서 새 LoRA를 만들며 smoke는 처음 8개 예제를 사용한다. 이후 스크립트의 smoke는 길이가 긴 8개를 선택하므로 현재 코드만 보고 두 smoke의 subset을 같다고 가정하지 않았다.

`improved-20260929`와 `expanded-20260929`는 서로 이어 붙인 run이 아니다. 둘 모두 **pilot epoch 3**에서 따로 출발했다. `improved-smoke` 결과도 expanded의 초기 adapter로 사용되지 않았다.

근거:

- [pilot 완료 로그](E:/qwen-llm/runs/pilot-20260929/metrics.jsonl:123)
- [improved stop_requested 로그](E:/qwen-llm/runs/improved-20260929/metrics.jsonl:221)
- [expanded early_stop 로그](E:/qwen-llm/runs/expanded-20260929/metrics.jsonl:491)
- [expanded 초기 adapter 설정](E:/qwen-llm/runs/expanded-20260929/config.json:73)
- [pilot 실행 명령](E:/qwen-llm/scripts/pilot_pipeline.py)

## 저장 checkpoint별 epoch·step·loss

Train loss는 해당 epoch에 기록된 `backward.loss`의 산술평균이다. 학습 도중 가중치가 바뀌는 모델의 예제별 loss이며, 고정 checkpoint로 전체 train을 다시 평가한 값이나 토큰 가중 평균은 아니다. Validation은 당시 run에서 실제 사용한 검증 예제의 평균이다.

| Run / checkpoint | metadata epoch | metadata step | epoch train loss 평균 | 당시 validation loss | 검증 수 |
|---|---:|---:|---:|---:|---:|
| smoke / epoch 1 | 1 | 1 | 0.890405 | 0.931764 | 2 |
| pilot / epoch 1 | 1 | 5 | 0.957774 | 0.741445 | 8 |
| pilot / epoch 2 | 2 | 10 | 0.639960 | 0.647154 | 8 |
| pilot / epoch 3 | 3 | 15 | 0.398419 | 0.592772 | 8 |
| improved-smoke / epoch 1 | 1 | 1 | 0.548815 | 0.690211 | 2 |
| improved / epoch 1 | 1 | 12 | 0.514798 | 0.458359 | 16 |
| improved / epoch 2 | 2 | 24 | 0.259799 | 0.480418 | 16 |
| **expanded / epoch 1 — 현재 선택** | **1** | **27** | **0.555085** | **0.469368** | **44** |
| expanded / epoch 2 | 2 | 54 | 0.344280 | 0.481857 | 44 |

각 run의 `complete.reload_validation_loss`는 그 run이 선택한 best checkpoint의 당시 validation loss와 정확히 일치한다. 이는 **과거 저장·재로드 확인 기록**이며 이번 감사에서 가중치를 다시 로드했다는 뜻은 아니다. 마지막 complete에 step 54와 loss 0.469368이 함께 있다고 해서 epoch 2의 validation이 0.469368인 것도 아니다. 전체 학습은 step 54까지 수행한 뒤 **선택된 epoch 1을 재로드**해 평가했다.

expanded의 직접 근거는 [epoch 1 validation](E:/qwen-llm/runs/expanded-20260929/metrics.jsonl:246), [epoch 2 validation](E:/qwen-llm/runs/expanded-20260929/metrics.jsonl:490), [best 재로드 완료](E:/qwen-llm/runs/expanded-20260929/metrics.jsonl:492)다. 저장 metadata는 `optimizer.pt`의 `epoch`/`steps` 항목을 별도로 대조했다.

LoRA 설정은 모든 확인된 run에서 BF16, 비양자화, rank 8, alpha 32, trainable 21,639,168개다. expanded의 learning rate는 **5e-5**, 다른 4개 run은 **1e-4**다. `adapter_config.json`의 `inference_mode`나 `init_lora_weights`는 학습 완료 epoch를 나타내는 필드가 아니다. epoch/step 판정에는 optimizer metadata와 실제 학습 로그를 사용했다.

## 현재 선택이 epoch 1인 이유

선택 경로는 [config/serving.json:2](E:/qwen-llm/config/serving.json:2), expanded `selection.json`, `checkpoint-selection-review.json`에서 일치한다. 파일과 adapter metadata도 실제 존재한다.

검증 loss에는 두 가지 버전이 있다.

| 평가 | Epoch 1 | Epoch 2 | 의미 |
|---|---:|---:|---|
| 학습 당시 online validation **44건** | 0.4693680399690162 | 0.4818571414798498 | expanded metrics/selection.json의 값 |
| 정리한 validation **43건** 재평가 | 0.4737201534904713 | 0.4876236292685187 | clean-validation-loss.json의 값 |
| 같은 고정 16개 검증 대화의 fallback | 0 | 1 | checkpoint-dialogue 원시 metrics에서 다시 집계 |
| 같은 16개에서 repair 후 모델 응답 반환 | 1 | 0 | raw/final을 구분 |
| 같은 16개 첫 시도 guard 부적합 | 1 | 1 | JSON 문법 오류 수와 다름 |

43건 파일의 실제 SHA256은 clean-validation-loss.json에 기록된 `f60f5a6171b45fd0b89800d737c661be975770fcb7342fddb3234f6dfbd9241a`와 일치한다. v2와 v3의 train 파일은 동일하지만 validation에서 1건을 분리했으므로 44건 loss와 43건 loss는 같은 숫자가 아니다.

16개 비교의 원시 결과에서 `improvement-v1-106`은 두 checkpoint 모두 첫 거절 답변에 요구된 존댓말을 지키지 않았다. epoch 1은 재생성 후 “대신 작성할 수는 없습니다”로 복구했고, epoch 2는 두 번째에도 같은 부적합 대사를 반복해 fallback으로 바뀌었다. 따라서 epoch 1 선택은 낮은 clean validation loss와 낮은 fallback이라는 근거가 있다.

기존 선택 검수에는 두 후보 모두 제공된 기억/걸음값 및 Quest ID를 바꾸는 오류가 해당 16건에서 없었다고 기록돼 있다. 일부 장난 표현은 epoch 2가 더 낫고 epoch 1에도 어색한 말투와 근거 없는 “첫 발표” 가정이 남는다고 명시돼 있다. 이를 “epoch 1의 모든 대화 품질이 더 좋다”로 확대하지 않는다.

근거: [clean loss epoch 1](E:/qwen-llm/runs/improvement-20260929/clean-validation-loss.json:7), [clean loss epoch 2](E:/qwen-llm/runs/improvement-20260929/clean-validation-loss.json:13), [선택 이유](E:/qwen-llm/runs/improvement-20260929/checkpoint-selection-review.json:36), [16건씩의 원시 대화](E:/qwen-llm/runs/improvement-20260929/checkpoint-dialogue.json).

선택 정책과 검수 파일은 최종 58건 시험을 checkpoint 선택에 사용하지 않았다고 기록한다. 이번 감사는 그 역사적 정책·원시 결과·현재 설정의 일치를 확인했으며 당시 의사결정을 새로 재연하지 않았다. 서비스 config의 기본 선택을 확인한 것이므로, 별도 프로세스가 환경변수나 명시 인자로 다른 adapter를 로드했는지까지 증명하는 결과는 아니다.

## 과적합 신호와 판단 한계

**expanded epoch 2에는 과적합과 일치하는 신호가 있다.** 같은 run에서 train loss 평균은 0.555085→0.344280으로 **약 38.0% 감소**했으나, online validation은 **2.66% 악화**, 정리한 clean validation도 **2.93% 악화**했다. 로그의 종료 이유도 `validation worsened`다. 같은 16개 대화에서도 fallback이 0→1로 늘었다.

96건 improved 실험에서도 train loss는 0.514798→0.259799로 약 49.5% 감소하는 동안 validation은 0.458359→0.480418로 약 4.81% 악화했다. 다만 이 run의 실제 종료 이벤트는 `stop_requested`다. `stop.request`에는 다음 checkpoint 저장 뒤 중단하고 확장 데이터를 pilot adapter에서 새 run으로 학습한다는 내용이 남아 있다. 검증 악화가 관찰됐다는 사실과 자동 early stopping으로 종료됐다는 주장을 혼동하면 안 된다.

반면 pilot에서는 epoch 1→3 동안 validation이 0.741445→0.647154→0.592772로 계속 감소했다. **관찰된 세 epoch에서는 validation 악화가 없다.** pilot epoch 4 이후나 expanded epoch 3 이후는 실행·저장된 결과가 없으므로 추정하지 않는다. smoke 2건 validation으로는 과적합이나 성격 품질을 판단할 수 없다.

이 신호만으로 모든 대화 오류의 원인을 과적합으로 확정하지 않는다.

- 실행별 seed는 하나이고 독립 반복 학습·신뢰구간 검증이 없다.
- 검증 수가 8/16/43/44건으로 작다. 기존 데이터 감사에서 의미상 가까운 train/validation 사례도 발견했다.
- Train 평균은 학습 중 값이며 validation은 epoch 말의 eval 값이라 절대 차이를 엄밀한 일반화 오차로 계산하지 않는다.
- run 사이에는 데이터, 초기 adapter, 프롬프트 코드, 학습률이 달라진다. pilot loss와 expanded loss를 직접 빼서 품질 개선율로 쓰지 않는다.
- 네 성격축의 라벨이 기존 학습 데이터에 없으므로 “네 축을 학습했으나 과적합해서 실패했다”고 결론낼 근거가 없다.
- 출력 형식 개선, 말투 구분, 기억 정확성, Quest 숫자 보존은 서로 다른 평가 대상이다.

## 선택 뒤의 실제 평가가 보여 준 한계

보존된 최종 58건 원시 비교에는 base, pilot epoch 3, expanded epoch 1 각각 58건과 생성 attempt가 모두 있다. 아래 fallback은 원시 metrics에서 다시 집계했고, 의미 오류 범주는 당시 동일 Codex 검수자의 라벨이다. 이번에 새 블라인드 검수를 수행한 값이 아니다.

| 58건당 관찰 지표 | Base | Pilot epoch 3 | Expanded epoch 1 |
|---|---:|---:|---:|
| 최초 JSON 문법 오류 | 1 | 0 | 0 |
| 최초 schema/enum 오류 | 8 | 1 | 0 |
| 최초 말투·언어 오류 라벨 | 8 | 12 | 6 |
| 최초 기억·사실 오류 라벨 | 7 | 3 | 4 |
| 최초 퀘스트·진행 오류 라벨 | 6 | 0 | 2 |
| 최초 불필요한 반복 라벨 | 0 | 0 | 1 |
| 서버 fallback | 6 | 2 | 1 |

범주가 중복될 수 있으므로 합산한 실패율이나 `58−라벨합계` 성공률을 만들지 않는다. 형식과 일부 말투는 개선됐지만 pilot보다 기억·퀘스트 오류가 늘었으므로 **선택 adapter의 전체 품질 우위나 운영 승인까지 입증되지는 않았다.** 현재 config도 `production_quality_approved=false`다.

예를 들어 expanded epoch 1은 target 500/progress 120을 “120걸음 중 500걸음을 채웠어”로 뒤집었고, “아침보다 늦은 오후를 선호”하는 기억을 “저녁이나 밤”으로 바꾼 원시 결과가 있다. 이것은 낮은 validation loss나 유효 JSON이 사실 정확성을 보장하지 않는 사례다. 최종 58건에는 expanded epoch 2를 넣지 않았으므로 이 표로 epoch 1과 2의 최종 시험 우열을 계산할 수도 없다.

근거: [최종 원시 비교](E:/qwen-llm/runs/improvement-20260929/final-comparison.json), [기계 검사](E:/qwen-llm/runs/improvement-20260929/final-mechanical.json), [기존 의미 검수](E:/qwen-llm/runs/improvement-20260929/final-semantic-review.json). 이미 읽고 평가한 이 시험은 향후 새 개선의 미노출 holdout으로 재사용할 수 없다.

## 기존 보고와 원시 근거의 차이

1. **`epochs:3`과 실제 2 epochs:** expanded/improved config는 계획 상한이다. 완료량은 로그·checkpoint metadata로 판정했다. 기존 파일을 수정하지 않았다.
2. **0.469368과 0.473720:** 전자는 44건 online, 후자는 43건 clean 재평가다. 현재 선택은 같은 expanded epoch 1로 일치한다.
3. **“NLL uses all 44”라는 보존 문구:** [checkpoint-selection-cases.json:777](E:/qwen-llm/data/improvement_v2/checkpoint-selection-cases.json:777)에 남아 있지만 실제 clean loss 기록은 43건이다. [작성 코드](E:/qwen-llm/scripts/after_expanded_training.py:22)의 오래된 설명 문자열이 보존된 것으로 보이며, 이 문구로 clean 평가 분모를 44라고 보고하면 틀린다. 실제 16개 dialogue cases는 v1 validation cases의 동일한 복사본임을 비교했다.
4. **과거 epoch 3 선택:** [FINAL_STATUS.json:21](E:/qwen-llm/FINAL_STATUS.json:21)과 [docs/RESULTS.md:13](E:/qwen-llm/docs/RESULTS.md:13)은 앞선 pilot 단계의 기록이다. 현재 기본 설정과 더 나중의 IMPROVEMENT_STATUS는 expanded epoch 1을 가리킨다. 과거 파일을 현재 상태로 덮어쓰지 않았다.
5. **현재 선택의 학습 이력:** `--init-adapter`는 adapter 가중치를 가져오지만 optimizer/epoch/step을 재개하지 않는다. [train_lora.py:64](E:/qwen-llm/scripts/train_lora.py:64)에서 새 optimizer와 step 0으로 시작하며 `--resume` 경로만 저장 optimizer를 복원한다. 선택 모델은 “pilot 3회 학습 상태를 출발점으로 expanded 데이터 1회 추가 학습”이라고 설명하는 것이 정확하다.

현재 증거로 유지할 판단은 **“expanded epoch 1을 개발 baseline으로 선택한 근거는 있으며, 두 번째 expanded epoch에서 일반화 악화 신호가 관찰됐다. 그러나 성격별 말투·기억·퀘스트 품질이 충분히 완성됐다는 근거는 없다”**이다. 이번 작업에서 새 학습이나 데이터 대량 제작을 실행하지 않았다.
