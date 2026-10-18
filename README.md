# HEALTHMON

팀 기본 Unity 화면에서 대화·음식 분석·3D 진화를 연결합니다. 작업 브랜치는 `ai/3d`이며 기존 팀 폴더 구조를 유지합니다.

| 경로 | 역할 |
| --- | --- |
| `Ai/LLM` | 기존 대화·음식 기록 API, 앱 실행기 |
| `Ai/Vision` | 팀 음식 인식 모델과 CPU 워커 |
| `Ai/Generation3D` | Qwen 이미지 생성, TRELLIS.2, RigAnything, 비동기 진화 API |
| `Client/HealthMonUnity` | 팀 `MainARScene`, 대화·촬영 UI, 기존 AR 큐브의 모델 교체 |
| `Server`, `Wearable` | 기존 팀 영역 |
| `Docs` | 실행과 연동 계약 |

[로컬 실행](Docs/LOCAL_DEVELOPMENT.md) · [3D 진화 연동](Docs/3D_UNITY_INTEGRATION.md) · [폴더 구조](Docs/BRANCH_LAYOUT.md)

모델 가중치·생성 결과·로컬 인증·Unity 빌드 캐시는 소스와 분리합니다. 기존 Vision 가중치는 팀의 Git LFS 포인터를 유지합니다. 3D 가중치와 의존성 복원은 [3D 패키지 안내](Ai/Generation3D/README.md)를 따릅니다.
