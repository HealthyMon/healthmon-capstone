# HEALTHMON

운동·식사 기록과 캐릭터 성장, 대화, 3D 진화를 연결하는 프로젝트입니다.
공용 FastAPI와 PostgreSQL이 게임 상태를 관리하며 Unity와 Android가 같은 API를 사용합니다.

## 실행

Git, Python 3.10 이상, Docker Compose v2를 준비하고 저장소 루트에서 실행합니다.

```sh
python Server/scripts/manage.py init
docker compose up -d --build
python Server/scripts/manage.py seed
```

기본 API는 `http://127.0.0.1:8020`, 준비 상태는 `/health/ready`입니다.
Unity 버전은 `Client/HealthMonUnity/ProjectSettings/ProjectVersion.txt`를 따릅니다.

| 경로 | 역할 |
| --- | --- |
| `Server/healthmon` | 공용 API, v2.2 규칙, PostgreSQL, AI Gateway |
| `Client/HealthMonUnity` | 캐릭터, 대화, 음식 분석, AR, 운동 화면 |
| `Wearable/Android` | 워치 운동 수집, 휴대폰 저장, 서버 동기화 |
| `Ai/LLM` | 대화 모델과 기억 처리 |
| `Ai/Vision` | 음식 인식 모델 |
| `Ai/Generation3D` | 이미지 생성, 3D 재구성, 리깅, 진화 작업 |
| `Docs/api` | 공용 API와 AI Gateway 명세 |

[서버 실행](Docs/COMMON_SERVER.md) · [Unity 연결](Docs/UNITY_COMMON_SERVER.md) ·
[3D 진화](Docs/3D_UNITY_INTEGRATION.md) · [Android 연동](Wearable/Android/HealthMonWatch/docs/unity-plugin-integration.md)

환경 설정, 인증 정보, 데이터베이스, 모델 가중치와 생성 캐시는 로컬 런타임에 보관합니다.
기존 Vision 가중치는 Git LFS로 관리합니다. 3D 환경 준비는 [3D 안내](Ai/Generation3D/README.md)를 따릅니다.
