# HEALTHMON

운동·식사 기록과 캐릭터 성장, 대화, 3D 진화를 연결하는 프로젝트입니다.
공용 FastAPI와 PostgreSQL이 게임 상태를 관리하며 Unity와 Android가 같은 API를 사용합니다.

## 실행

**Unity 관절 AI 운동 화면:** Windows에서 `Setup-PoseAI.cmd`(최초 1회) →
`Start-AI.cmd` → Unity 홈의 **운동** 버튼 순서로 실행합니다. 기존 AI 최초 설정도 필요합니다.
Android 휴대폰 촬영은 `Connect-PoseAndroid.cmd`로 USB 연결 후 앱의 **운동** 화면을 사용합니다. [Android 실행·APK 안내](Ai/Pose/README-ANDROID.md)
스쿼트·팔굽혀펴기·컬을 카메라로 세며 AI 전체 종료는 `Stop-AI.cmd`입니다.
게임 백엔드와 독립적으로 대화·음식·진화·관절 AI를 함께 관리합니다. [실행 및 검증 안내](Ai/Pose/README-WINDOWS.md)

**로컬 기본 실행은 `Start-Backend.cmd`입니다.** API·PostgreSQL만 켜며 AI 모델이 없어도
계정·펫·운동·식사 기록과 서버 규칙을 사용할 수 있습니다. 종료는 `Stop-Backend.cmd`입니다.
상점의 상품 54개 조회·구매·코인 차감·보유 목록·캐릭터 선택 저장도 AI 없이 동작합니다.
지갑과 보유 목록은 펫별로 저장되며, 중복 요청은 추가 차감하지 않습니다. 캐릭터 선택은
서버에 저장하고 현재 슬라임 외형은 유지합니다. 재학습 모델의 실제 교체는 후속 작업입니다.
Unity는 `Client/HealthMonUnity`를 열고 실행 후 표시되는 연결 정보로 접속합니다.
새 설치의 기본 모드는 서버 모드이며, 로컬 서버 기본 주소는 `http://127.0.0.1:18092`입니다.

AI 최초 설정을 마친 뒤에는 `Start-AI.cmd` / `Stop-AI.cmd`로 대화·음식 분석·3D 생성·관절 인식을
별도로 켜고 끕니다. 초기 연결 설정을 적용할 때만 `Start-Backend.cmd`를 한 번 다시 실행하며,
이후 AI를 껐다 켜는 동안 API·DB를 재시작할 필요가 없습니다.
Unity 개발 설정에는 AI 전체·대화·음식·진화의 관측 상태가 표시됩니다.
관절 AI의 준비 상태는 통합 실행기에서도 확인합니다. 종료 시 한 그룹에 문제가 있어도 다른 그룹 종료를 시도합니다.
GPU 대화 모델은 현재 상주 방식이며 매 응답 후 해제하지 않습니다. 3D 생성 시 대화 모델을 내리고 생성 종료 후 복구합니다.
음식·관절 인식과 임베딩은 CPU를 사용합니다. 메모리 부족 시 실행을 거부하며 다른 프로그램을 종료하거나 모델을 임의 양자화하지 않습니다.

기존 `18092` 테스트 환경은 `.runtime/native-server.json` 설정이 있으면
**`Start-HealthMon.cmd` 하나로 원래 PostgreSQL·AI·API를 시작**합니다.
기존 DB·인증·펫·모델과 진화 저널을 그대로 사용하며, 다른 Docker DB로 전환하지 않습니다.
연결 정보는 실행 후 브라우저에 표시합니다. 종료는 `Stop-HealthMon.cmd`입니다.

Windows에서는 Docker Desktop을 준비합니다. AI까지 함께 실행하려면 AI 환경을 설정한 뒤
**`Start-HealthMon.cmd`를 더블클릭**합니다. 로컬 AI를 설정한 PC에서는 대화 모델,
음식 분석, 3D Gateway·자동 생성 worker, 관절 AI, 서버·DB를 함께 실행하고 준비 상태를 확인합니다.
테스트 펫 준비가 끝나면 Unity에 넣을 주소·토큰·펫 ID를 브라우저에 표시합니다.
공유 AI 서버를 사용하는 경우 대화·음식·진화용 로컬 GPU는 필요 없습니다.
통합 실행에 포함된 관절 AI는 이 PC의 Python CPU 환경을 사용하며 `Setup-PoseAI.cmd`로 준비합니다.
끌 때는 **`Stop-HealthMon.cmd`**를 실행합니다.
기존 설정·펫·기록은 유지하며 첫 설정의 기본 포트는 `18092`입니다.
AI 모델·Python/CUDA 환경은 코드에 포함되지 않으며 PC별로 준비하거나 공유 AI 서버를 지정합니다.
AI 준비가 빠지면 실행기가 원인을 표시하며, 이미 켜진 백엔드는 유지합니다.
[AI 최초 설정](Server/local_probe/README.md) · [1차 정리 내역과 남은 작업](Docs/LOCAL_RUNTIME_REFACTOR.md)을 참고하세요.
모델 연결이 없던 기존 펫에도 기본 3D 캐릭터를 자동 연결하며 레벨과 기록은 유지합니다.

명령줄로 직접 실행하려면:

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
