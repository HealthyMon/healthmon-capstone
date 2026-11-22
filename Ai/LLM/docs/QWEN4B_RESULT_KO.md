# Qwen3.5-4B 학습 결과

## 완료한 작업

- 공식 Qwen3.5-4B에 새 NF4 QLoRA를 학습했습니다. 9B용 LoRA를 재사용하지 않았습니다.
- 1단계: 기존 헬스몬 216건 + AI Hub에서 선별한 대화 29건, 1 epoch, optimizer 31회.
- 2단계: 공통 서버용 43건 + 기존 예제 재학습 48건, 2 epochs, optimizer 24회.
- 최종 체크포인트: `runs/qwen4b-common-v1/checkpoint-epoch-2`.
- 성격 지침·최근 대화·관련 기억을 프롬프트로 전달하는 기존 함수와 서버 상태 계산·기억 검색 코드는 유지했습니다.
- 기존 LLM API와 Unity 공통 서버의 서로 다른 JSON 계약을 함께 학습했습니다.
- Ollama에 있던 GGUF는 그대로 두고, 학습용 공식 safetensors를 별도로 받았습니다.

## 마지막에 수행한 검증

완료된 검사는 다시 실행하지 않았습니다. 중단된 마지막 API 단계만 별도로 이어서 처리했습니다.

| 항목 | 결과 |
|---|---|
| 코드 검사 | 108개 통과 |
| 기존 LLM API 형식의 실제 생성 | 15/16 통과 (학습 전 4B: 13/16) |
| 공통 서버 형식의 실제 생성 | 12/12 통과 |
| 최종 학습 검증 손실 | 0.548932 (공통 6건 + 기존 43건) |
| 모델 저장 후 재로드 손실 | 0.548932 |
| 실제 API 요청 검사 | 실제 4B 모델 사용 3건 통과; 인증 거절·동일 요청 재사용·입력 충돌 처리 확인 |

위 수치는 응답 계약과 개발용 사례 결과입니다. 독립적인 의미 정확도나 9B 대비 동등 성능을 의미하지 않습니다.
학습 데이터는 AI Hub 전체가 아닌 선별한 일부이며, 새 공통 서버 예제는 AI가 작성·검토했습니다.

## 확인된 한계

- 성격 Activity/Affinity의 낮음·높음에 따른 말투 차이가 약합니다.
- 캐릭터 호감 발화를 `target=other`로 분류한 사례가 있습니다.
- 일상 대화의 질문 의도, 존댓말, 퀘스트 만료 설명에 일부 오류가 있습니다.
- 기억의 변경 시간대와 5분 산책 목표는 이번 실제 생성 사례에서 올바르게 답했습니다.
- 원래 운영 중이던 9B LoRA가 없어서 9B와 직접 비교하지 못했습니다.
- 실제 Unity APK, 기존 DB, BGE 검색을 연결한 실기기 검증은 하지 않았습니다.

## 로컬 서버에 선택하기

모델 선택 정보는 `config/serving.qwen4b.json`, 공통 서버 설정 예시는
`config/common-gateway.qwen4b.example.json`에 있습니다. 예시의 토큰과 BGE 경로는
기존 서버 값을 사용해야 합니다. 예시는 실행 중인 서버 설정을 자동으로 바꾸지 않습니다.

기존 공통 서버의 비공개 AI 설정에서 아래 모델 항목을 적용합니다.

- `model_path`: 이 폴더의 `models/qwen3.5-4b` 절대 경로
- `adapter_path`: 이 폴더의 `runs/qwen4b-common-v1/checkpoint-epoch-2` 절대 경로
- `expected_model_mode`: `lora`
- `expected_model_version`: `qwen4b-v1`
- `quantization`: `nf4`
- `full_personality_facts`: `true`

기존 토큰·BGE 경로·DB·Unity 접속 주소는 유지합니다. 공통 서버는 기존 실행 경로를 사용합니다.
이 복사본에는 `.env`나 비공개 운영 설정이 없어 실제 APK 접속 서버를 교체하지 않았습니다.

학습·실행 명령의 상세 안내는 `QWEN4B_MIGRATION.md`를 참고하세요.
검증 원본은 `runs/qwen4b-final-validation-v1`에 있습니다.
