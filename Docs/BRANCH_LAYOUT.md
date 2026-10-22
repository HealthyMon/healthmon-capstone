# 저장소 구조

`feature/dev`에서 공용 서버와 클라이언트 통합을 개발하며, 팀 검토 후 `develop`에 반영합니다.

```text
Ai/
  LLM/
  Vision/
  Generation3D/
Client/HealthMonUnity/
Server/
  healthmon/
  migrations/
  assets/
  scripts/
  tests/
Wearable/Android/
Docs/api/
compose.yaml
```

공용 서버는 루트 Compose로 실행합니다. [로컬 실행](LOCAL_DEVELOPMENT.md)을 참고합니다.
Unity 에셋과 스크립트는 `.meta`를 함께 관리해 씬·프리팹의 GUID 연결을 유지합니다.
GPU 가중치·vendor 의존성·생성 결과·실행 설정은 소스와 분리해 관리합니다.
