# 3D 진화와 Unity 연결

기존 AR 배치 함수가 만드는 큐브를 배치 루트로 유지합니다. 완료된 GLB를 그 자식으로 로드하고 다운로드·SHA256·재질·스킨 로딩이 성공한 뒤 이전 시각 모델을 교체합니다. 루트의 위치·회전과 콜라이더는 보존합니다. 팀 씬·프리팹 구조를 새로 만들지 않습니다.

## 처리 순서

1. `EvolutionClient.SetGrowthStats(stats, source)`로 점수 8개와 출처를 전달합니다.
2. 기존 레벨 이벤트의 15·30·50 조건 또는 `RequestEvolution(level, stats, source)` 신호를 받습니다.
3. 서버는 202로 작업 ID를 반환하고 실제 현재 부모 이미지와 개체의 종 계약을 확인합니다.
4. 부모 이미지의 시각 특징을 읽고 점수 기반 설계를 생성한 뒤 Qwen-Image-2.1로 새 이미지를 만듭니다. 현재 방식은 부모를 분석한 새 text-to-image 생성이며 동일 픽셀을 보존하는 직접 편집을 보장하지 않습니다.
5. 모라·누비 2차 정책은 몸통·지지 팔다리를 포함한 최소 세 부위의 큰 구조 변화와 계승 상징을 검사합니다. 관찰을 검사표로 구조화해 해시와 엄격한 판정 기준을 재확인합니다. 자동 시각 판단은 오류 가능성이 있어 직접 품질 검토도 필요합니다.
6. TRELLIS.2 → RigAnything → 기술·포즈 검사 후 원본 GLB를 불변 버전 폴더에 저장합니다.
7. `current.json`을 원자적으로 교체하고 Unity가 같은 AR 자리의 모델 자식을 갱신합니다.

점수 필드: `UpperBody`, `LowerBody`, `Nutrition`, `Activity`, `Affinity`, `Initiative`, `Mood`는 0~100, `EnergyBalance`는 -1~1입니다. 기분은 영구 몸 조형 계산에서 제외합니다. 실측되지 않은 점수를 임의로 만들지 않으며, 전체 점수가 없으면 `waiting_for_growth_stats`로 기다립니다. 시연은 `score_source=synthetic_demo`처럼 출처를 명시합니다.

단계와 조형 규칙을 함께 바꾸면 그 차이를 작은 점수 변화만의 효과로 해석할 수 없습니다. 실제 생활 기록을 이 8개 점수로 변환하는 생산자는 아직 연결되지 않았습니다.

## 소스와 API

- `Scripts/API/EvolutionClient.cs`: 요청·재개·조회·해시 확인
- `Scripts/Growth/EvolutionContracts.cs`: 점수·요청·완료 버전 계약
- `Scripts/AR/ArEvolutionModel.cs`: glTFast로 GLB를 같은 배치 루트에 로드
- `Ai/Generation3D/runtime/unity`: 비동기 API, 저장, GPU 워커, 검사
- `configs/evolution/second-stage-v2.json`: 큰 2차 변화 정책

| API | 용도 |
| --- | --- |
| `GET /health` | 준비 상태 |
| `GET /v1/pets/{pet}/current` | 현재 완료 버전 |
| `POST /v1/pets/{pet}/evolutions` | 레벨·점수·출처·요청 ID로 진화 신호 |
| `GET /v1/jobs/{job_id}` | 진행·실패·완료 조회 |
| `GET /v1/pets/{pet}/versions/{revision}/model.glb` | 불변 모델 다운로드 |

요청은 ID로 중복을 방지하고, 레벨을 크게 올려도 한 번에 한 단계씩 진화합니다. 실패하거나 파일 검증이 깨지면 이전 현재 모델을 유지합니다. 기존 대화 모델과 GPU 잠금을 공유합니다. CPU 음식 인식은 별도 워커를 사용합니다.

## 검증과 범위

3D 회귀 검사는 중복·충돌·순차 단계·인증·다운로드·원자 게시·실패 보존·재시작·부모 계승·종별 설계·큰 변화 판정을 확인합니다. 실제 모라 2차는 이미지·원본 3D·34개 뼈·Unity Editor 교체를 확인했고, 누비 2차는 이미지 비교까지 확인했습니다. Qwen 가중치를 추가 학습하지 않았습니다.

기술 리깅 통과는 완성된 애니메이션 품질을 보장하지 않습니다. 현재 검증 GLB에는 애니메이션 클립이 없으며, 몸통·겨드랑이 스킨 정리와 꼬리·잎의 독립 움직임 검토가 필요합니다. 실기기 AR 추적과 고밀도 원본 모델의 모바일 성능은 별도로 검증해야 합니다. 로컬 검증 원본·실패 기록·빌드 백업은 소스 저장소 밖에 보관합니다.
