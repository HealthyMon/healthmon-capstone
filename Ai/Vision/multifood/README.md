# Multi-food CPU runtime

이 코드는 `HealthyMon/healthmon-capstone`의 `feature/vision` revision `8be8e8afd9e4d93f28329076243c36bf85f3a1a6`에서 필요한 음식 분석 부분만 선별했습니다.

- 원본: `Ai/Vision/Vision/aihub/*.py`, `Ai/Vision/Vision/food_ai.py`
- 음식 영역: DishSeg로 학습한 FasterRCNN MobileNet
- 음식명: NoisyViT Food2K, 2,000개 클래스. CSV 행 순서가 모델 클래스 순서이므로 임의 정렬하지 않습니다.
- 중량: FPB YOLOv12XL의 음식별 crop 회귀
- `vendor/fpb/ultralytics`: 원본 `음식 탐지/Multitask-Food-Portion-Estimation/ultralytics`의 필요한 Python/YAML 소스. 원본 라이선스는 `vendor/fpb/LICENSE`에 보존합니다.

`worker.py`는 기존 인증 게이트웨이에서만 호출하는 CPU 추론 진입점입니다. 표준 입력 JSON 한 건을 받고 JSON 한 건을 반환합니다. 추론 시 다운로드하지 않으며 모델을 요청 종료 후 해제합니다. 전체 사진은 최대 1,024px, 음식 crop은 최대 192px로 전송합니다. 실제 음식이 없으면 결과를 만들지 않고 오류로 반환합니다.

## 설치와 실행

저장소 루트 `Start-HealthMon.cmd`의 5번이 모델 3개와 `healthmon-multifood:local` 이미지를 준비합니다. 가중치 합계는 564,822,953바이트이며 `models/manifest.json`의 크기·SHA-256·source revision을 확인합니다. Windows의 기존 대화용 Python 환경에 Torch나 Vision 의존성을 설치하지 않습니다.

일반 팀 설치는 음식 Docker 서비스 안에서 실행합니다. 기존 네이티브 AI 설치는 동일한 CPU 이미지를 요청마다 `--network none`으로 실행합니다. 백엔드 인증, 기존 요청 ID, 식사 확인 API를 그대로 사용하며 별도 8001 포트나 게임 내 서버 주소 입력은 추가하지 않습니다.

## 결과의 의미

음식명과 중량은 사진 기반 추정값입니다. 이름은 등록된 음식 목록에서 수정하고 중량은 실제 먹은 양으로 확인해야 합니다. 신뢰도가 낮은 음식명을 확정 사실로 표시하지 않습니다. 영양 정보의 결측과 실제 0을 구분합니다. UI의 열량을 서버로 그대로 보내지 않고 서버의 동일한 음식 카탈로그로 다시 계산합니다.

같은 분석을 재전송해도 식사·보상을 중복 생성하지 않습니다. 이 브랜치의 다중 음식 기록은 분석된 모든 영역을 한 번씩 확정하도록 요구합니다. 오검출 영역을 삭제하는 기능은 포함하지 않았습니다.

## 확인한 테스트

`python -m pytest Ai/Vision/multifood/aihub -q`는 영역 중복 제거, 클래스 순서, 결측 영양, 중량 매칭을 검사합니다. 실제 추론 및 Unity 결과는 `Docs/VISION_INTEGRATION_REVIEW.md`에 기록합니다. 단일 사진의 성공은 분류 정확도 평가나 Android 실기기 검증을 의미하지 않습니다.
