# HEALTHMON

운동·식사 기록을 슬라임의 성장에 연결하는 Android AR 캐릭터 육성 게임입니다.
육성·탐험·전투와 AI 대화·음식 분석·관절 인식·3D 진화를 연결합니다.
공용 FastAPI와 PostgreSQL이 게임 상태를 관리하며 Unity와 Android가 같은 API를 사용합니다.

**처음 받았다면 [설치·실행·AI 가중치 안내](Docs/SETUP_AND_MODEL_GUIDE.md)를 먼저 확인하세요.**
필수 프로그램, `5 → 2 → 3 → 4` 실행 순서, 포함된 가중치와 별도 모델,
SW 등록 자료에 사용할 프로그램 구성 설명을 정리했습니다.

## 실행

루트 실행 파일은 **`Start-HealthMon.cmd`와 `Stop-HealthMon.cmd` 두 개**입니다.
더블클릭 후 **1번 전체 / 2번 백엔드 / 3번 AI / 4번 Android USB**를 선택합니다.
시작 메뉴의 **5번**은 최초 환경 설치, **0번**은 실행 없이 닫기입니다.
**처음에는 5번 → 이후 2번 백엔드 / 3번 AI**입니다. 3번은 설치된 AI를 모두 켜되 모델이 없는 기능만 건너뜁니다.
명령줄에서는 아래의 `-Target` 옵션으로 메뉴를 건너뛸 수 있습니다.

**Unity 관절 AI 운동 화면:** Windows에서 `Start-HealthMon.cmd -Target Setup`(최초 1회) →
`Start-HealthMon.cmd -Target Backend` → `Start-HealthMon.cmd -Target AI` → Unity 홈의 **운동** 버튼 순서로 실행합니다.
Android 휴대폰 촬영은 `Start-HealthMon.cmd -Target Android`로 USB 연결 후 앱의 **운동** 화면을 사용합니다. [Android 실행·APK 안내](Ai/Pose/README-ANDROID.md)
스쿼트·팔굽혀펴기·컬을 카메라로 세며 AI 전체 종료는 `Stop-HealthMon.cmd -Target AI`입니다.
게임 백엔드와 독립적으로 대화·음식·진화·관절 AI를 관리하며, 설치되지 않은 모델은 건너뜁니다. [실행 및 검증 안내](Ai/Pose/README-WINDOWS.md)

**로컬 기본 실행은 `Start-HealthMon.cmd -Target Backend`입니다.** API·PostgreSQL만 켜며 AI 모델이 없어도
계정·펫·운동·식사 기록과 서버 규칙을 사용할 수 있습니다. 종료는 `Stop-HealthMon.cmd -Target Backend`입니다.
상점의 상품 54개 조회·구매·코인 차감·보유 목록·캐릭터 선택 저장도 AI 없이 동작합니다.
지갑과 보유 목록은 펫별로 저장되며, 중복 요청은 추가 차감하지 않습니다. 캐릭터 선택은
서버에 저장하고 현재 슬라임 외형은 유지합니다. 재학습 모델의 실제 교체는 후속 작업입니다.
Unity는 `Client/HealthMonUnity`를 열고 Play를 누르면 실행기가 준비한 계정으로 자동 접속합니다.
새 설치의 기본 모드는 서버 모드이며, 로컬 서버 기본 주소는 `http://127.0.0.1:18092`입니다.

AI 최초 설정을 마친 뒤에는 `Start-HealthMon.cmd -Target AI` / `Stop-HealthMon.cmd -Target AI`로 대화·음식 분석·3D 생성·관절 인식을
별도로 켜고 끕니다. 초기 연결 설정을 적용할 때만 `Start-HealthMon.cmd -Target Backend`를 한 번 다시 실행하며,
이후 AI를 껐다 켜는 동안 API·DB를 재시작할 필요가 없습니다.
Unity 개발 설정에는 AI 전체·대화·음식·진화의 관측 상태가 표시됩니다.
관절 AI의 준비 상태는 통합 실행기에서도 확인합니다. 종료 시 한 그룹에 문제가 있어도 다른 그룹 종료를 시도합니다.
GPU 대화 모델은 현재 상주 방식이며 매 응답 후 해제하지 않습니다. 3D 생성 시 대화 모델을 내리고 생성 종료 후 복구합니다.
음식·관절 인식과 임베딩은 CPU를 사용합니다. 메모리 부족 시 실행을 거부하며 다른 프로그램을 종료하거나 모델을 임의 양자화하지 않습니다.

기존 `18092` 테스트 환경은 `.runtime/native-server.json` 설정이 있으면
**`Start-HealthMon.cmd` 하나로 원래 PostgreSQL·AI·API를 시작**합니다.
기존 DB·인증·펫·모델과 진화 저널을 그대로 사용하며, 다른 Docker DB로 전환하지 않습니다.
연결 정보는 `.runtime/client-connection.json`에 자동 저장합니다. 종료는 `Stop-HealthMon.cmd`입니다.

Windows에서는 Docker Desktop을 준비합니다. AI까지 함께 실행하려면 AI 환경을 설정한 뒤
**`Start-HealthMon.cmd`를 더블클릭하고 1번 전체를 선택**합니다. 로컬 AI를 설정한 PC에서는 대화 모델,
음식 분석, 3D Gateway·자동 생성 worker, 관절 AI, 서버·DB를 함께 실행하고 준비 상태를 확인합니다.
테스트 펫 준비가 끝나면 Unity 연결 설정도 자동 생성합니다. 주소·토큰·펫 ID를 복사할 필요가 없습니다.
공유 AI 서버를 사용하는 경우 대화·음식·진화용 로컬 GPU는 필요 없습니다.
새 통합 설치에서는 관절 AI도 Docker 내부 CPU 환경을 사용합니다. 기존 PC의 네이티브 실행 환경은 유지합니다.
끌 때는 **`Stop-HealthMon.cmd`**를 실행합니다.
기존 설정·펫·기록은 유지하며 첫 설정의 기본 포트는 `18092`입니다.
음식 가중치는 Git LFS로 관리하며, 기본 5번은 음식·관절 모델과 CPU 실행 환경을 준비합니다.
대화·진화용 대형 기본 모델과 별도 LoRA는 5번에서 받지 않습니다. [모델별 포함 범위](Docs/SETUP_AND_MODEL_GUIDE.md#3-ai-가중치가-포함된-범위)를 참고하세요.
AI 준비가 빠지면 실행기가 원인을 표시하며, 이미 켜진 백엔드는 유지합니다.
[기본 설치 안내](Docs/SETUP_AND_MODEL_GUIDE.md) · [기존 전체 AI 수동 설정](Server/local_probe/README.md) · [1차 정리 내역과 남은 작업](Docs/LOCAL_RUNTIME_REFACTOR.md)을 참고하세요.
모델 연결이 없던 기존 펫에도 기본 3D 캐릭터를 자동 연결하며 레벨과 기록은 유지합니다.

### 주소·토큰 입력 없이 접속

- PC: `Start-HealthMon.cmd`의 **1번**(전체) 또는 **2번**(백엔드) → Unity **Play**.
  Unity를 먼저 실행해도 5초 간격으로 서버 준비를 확인합니다. AI만 필요할 때는 **3번**으로 추가 실행합니다.
- Android 개발 APK: USB 디버깅이 승인된 휴대폰을 연결한 뒤 PC 실행기를 켭니다.
  설치된 HealthMon 개발 앱에 연결 정보를 전달하고 게임 API·관절 AI의 USB 경로를 함께 설정합니다.
  휴대폰을 나중에 연결했다면 **4번**으로 다시 설정합니다. 최초 USB 디버깅 승인은 휴대폰에서 직접 해야 합니다.
  이 기능이 포함된 새 개발 APK가 필요하며, 기존 APK 파일은 이번 코드 수정만으로 갱신되지 않습니다.
- 다른 서버·계정을 직접 지정하려면 게임 설정의 **수동 연결 설정**을 펼칩니다.
  수동 연결을 선택하면 자동 계정 변경을 중지하며, **서버 자동 연결** 버튼으로 다시 활성화합니다.

연결 파일에는 해당 로컬 테스트 계정의 토큰이 있으므로 공유하지 않습니다. Git·씬·APK에는 포함하지 않으며,
Android에서는 ADB `run-as`로 앱 내부 저장소에만 전달합니다. 일반 배포 APK의 계정 로그인이나 Wi-Fi 연결 설정을
대체하는 기능은 아닙니다. 자동 접속 전 서버 식별자를 확인하고 기존 계정의 펫 선택을 유지합니다.
실행기는 브라우저 입력 안내를 자동으로 열지 않습니다. 필요하면 `.runtime/local-server-connection.html`에서
접힌 수동 연결 정보를 확인할 수 있습니다.

## 팀원 PC 최초 설치

Windows x64에서 Docker Desktop의 Linux 컨테이너와 WSL2를 준비하고 Unity는 별도로 설치합니다.
호스트에 Python을 따로 설치하거나 주소·토큰을 입력할 필요는 없습니다.
Unity 버전·Android 빌드 모듈·ADB·워치 앱 조건은 [필수 프로그램과 연결 안내](Docs/SETUP_AND_MODEL_GUIDE.md)를 확인하세요.

1. 저장소를 받은 뒤 `Start-HealthMon.cmd`의 **5번**: 백엔드·DB와 음식 분석·관절 인식 실행 환경을 준비합니다.
2. **2번**: 백엔드 실행. 워치 데이터·게임 기록·성장·상점·전투를 테스트합니다.
3. **3번**: 설치된 AI를 모두 실행합니다. 대화·음식·진화·관절 중 모델이 없는 기능은 `SKIP`으로 표시하고 나머지를 계속 실행합니다.
   **1번**은 2번과 3번을 함께 실행합니다. 종료는 `Stop-HealthMon.cmd`의 같은 번호입니다.

5번은 음식 모델 약 565MB(GitHub LFS)와 관절 모델 약 131MB(OpenMMLab)를 준비하며,
Docker 이미지와 실행 패키지는 별도로 내려받습니다. 파일은 해시를 검사하고 정상 파일을 재사용합니다.
GitHub ZIP에 실제 Unity 에셋 대신 LFS 포인터가 들어 있으면 필요한 에셋도 복원합니다.
Hugging Face 접속·로그인, 비공개 LoRA, 100GB급 대화·진화 기본 모델 다운로드는 이 설치에 포함하지 않습니다.
설치는 서버를 켜지 않으며, 3번에서 빠진 모델을 자동 다운로드하지도 않습니다.

대화·진화가 이미 설치된 기존 PC는 설정과 모델을 그대로 사용합니다. 진화 요청을 처리할 때만
대화 GPU 프로세스를 내려 메모리를 확보하고, 진화가 끝나면 대화를 복구합니다. 음식·관절은 CPU로 동작합니다.
새 팀원 PC에서 대화·진화가 빠져 있어도 음식 분석·관절·백엔드 게임 테스트는 독립적으로 동작합니다.
실행 중 오류는 누락과 구분해서 표시하고, 준비된 다른 기능은 유지합니다.

최초 설치 코드는 `Server/team/setup.ps1`, CPU AI 환경은 `compose.team.yaml`입니다.
기존 전체 AI 환경의 수동 설치 코드는 `Server/portable`에 보존되어 있으며 기본 5번에서는 호출하지 않습니다.
기존 DB·계정·펫·인증 정보와 모델 파일은 삭제하거나 새로 만들지 않습니다.

### 개발자용 수동 실행

아래는 CMD의 5번 설치와 별개인 수동 개발 경로입니다. 이 경로에서는
Git, Python 3.10 이상, Docker Compose v2를 준비하고 저장소 루트에서 실행합니다.

```sh
python Server/scripts/manage.py init
docker compose up -d --build
python Server/scripts/manage.py seed
```

이 수동 경로의 기본 API는 `http://127.0.0.1:8020`, 준비 상태는 `/health/ready`입니다.
위 CMD 팀원 설치 경로는 `18092`를 사용합니다.
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

### 비전 선별 통합 검증 브랜치

현재 작업 브랜치는 `integration/vision-review-20261124`입니다. `develop` 기준 게임에 음식별 영역 분석, 이름·중량 수정, 합산 식사 기록을 연결했습니다. `feature/vision`의 관절·상점 삭제, 별도 대화 모델 설정, 가상환경 파일은 가져오지 않았습니다. [통합 범위와 검증 결과](Docs/VISION_INTEGRATION_REVIEW.md)를 확인한 뒤 `develop` 반영을 결정합니다.

기존 설치에서도 이 브랜치의 새 음식 모델과 CPU 이미지를 준비하려면 **5번을 한 번 실행한 후 2번 → 3번**으로 시작합니다. 대화·진화 모델은 추가 다운로드하지 않습니다. 기존 네이티브 설치에서는 음식 서비스 설정만 백업 후 새 Docker worker로 전환합니다.
