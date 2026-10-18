# 저장소 구조

`ai/3d`에서 Unity·LLM·Vision·3D를 함께 수정합니다. 별도 통합 브랜치나 다른 작업본의 서버를 실행하는 구조가 아닙니다.

```text
Ai/
  LLM/
  Vision/
  Generation3D/
Client/HealthMonUnity/
  Assets/HealthMon/
    Scenes/
    Scripts/API/
    Scripts/Dialogue/
    Scripts/Food/
    Scripts/Growth/
    Scripts/AR/
    Scripts/State/
    Scripts/UI/
    Scripts/Editor/
    Resources/
Server/
Wearable/
Docs/
```

Unity의 팀 씬·프리팹과 기존 기능별 폴더를 보존합니다. 에셋이나 스크립트를 옮길 때 `.meta`를 함께 옮겨 GUID와 Inspector 연결을 유지합니다. `Scripts/Editor`에는 팀 편집 도구와 실행에 필요한 씬 열기만 남깁니다.

3D 소스는 `Ai/Generation3D`가 기준입니다. Docker는 이 폴더의 `src`, `scripts`, `runtime` 및 진화 정책을 사용하고, 가중치·vendor·생성 결과는 별도 런타임 경로에 둡니다. `Ai/LLM/runtime/gpu.lock`을 공유해 큰 GPU 모델은 순서대로 실행합니다.
