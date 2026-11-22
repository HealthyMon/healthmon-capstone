# HEALTHMON

운동·식사 기록과 캐릭터 성장, 대화, 3D 진화를 연결하는 프로젝트입니다.
공용 FastAPI와 PostgreSQL이 게임 상태를 관리하며 Unity와 Android가 같은 API를 사용합니다.

## 실행

루트 실행 파일은 **`Start-HealthMon.cmd`와 `Stop-HealthMon.cmd` 두 개**입니다.
더블클릭 후 **1번 전체 / 2번 백엔드 / 3번 AI / 4번 Android USB**를 선택합니다.
시작 메뉴의 **5번**은 AI 전체 최초 설치, **0번**은 실행 없이 닫기입니다.
명령줄에서는 아래의 `-Target` 옵션으로 메뉴를 건너뛸 수 있습니다.

**Unity 관절 AI 운동 화면:** Windows에서 `Start-HealthMon.cmd -Target Setup`(최초 1회) →
`Start-HealthMon.cmd -Target AI` → Unity 홈의 **운동** 버튼 순서로 실행합니다.
Android 휴대폰 촬영은 `Start-HealthMon.cmd -Target Android`로 USB 연결 후 앱의 **운동** 화면을 사용합니다. [Android 실행·APK 안내](Ai/Pose/README-ANDROID.md)
스쿼트·팔굽혀펴기·컬을 카메라로 세며 AI 전체 종료는 `Stop-HealthMon.cmd -Target AI`입니다.
게임 백엔드와 독립적으로 대화·음식·진화·관절 AI를 함께 관리합니다. [실행 및 검증 안내](Ai/Pose/README-WINDOWS.md)

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
AI 모델 파일은 Git에 넣지 않으며, 아래 최초 설치에서 다운로드하고 Python/CUDA 환경을 Docker 이미지에 설치합니다.
AI 준비가 빠지면 실행기가 원인을 표시하며, 이미 켜진 백엔드는 유지합니다.
[AI 최초 설정](Server/local_probe/README.md) · [1차 정리 내역과 남은 작업](Docs/LOCAL_RUNTIME_REFACTOR.md)을 참고하세요.
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

## 팀원 PC 최초 통합 설치

대상은 NVIDIA GPU를 사용하는 Windows x64 PC입니다. Git·Git LFS, WSL2 기반 Docker Desktop,
NVIDIA 드라이버를 먼저 준비합니다. 호스트 Python 설치는 필요 없습니다. Unity는 별도로 설치합니다.

1. 저장소를 클론하고 팀에서 전달받은 `healthmon-adapters.zip`을
   `.runtime/team-install/healthmon-adapters.zip`에 둡니다. 이 ZIP에는 새 진화 epoch-10 LoRA와
   기존 대화 LoRA만 들어 있습니다. 비공개 가중치이므로 팀 내부에서 전달하며 로그인 토큰은 공유하지 않습니다.
2. `Start-HealthMon.cmd`의 **5번**을 실행합니다. Git LFS 음식 가중치, 고정 버전의 기본 모델·관절 모델을 받고
   파일 해시를 확인한 다음 Docker 실행 환경과 연결 설정을 만듭니다. 이 단계에서는 서버나 GPU 모델을 실행하지 않습니다.
3. 설치가 끝난 뒤 **1번 전체 / 2번 백엔드 / 3번 AI**로 실행합니다. 종료도 `Stop-HealthMon.cmd`의 같은 번호를 사용합니다.

ZIP을 다른 폴더에 둔 경우에는 다음처럼 지정할 수 있습니다.

```powershell
.\Start-HealthMon.cmd -Target Setup -BundlePath 'D:\Downloads\healthmon-adapters.zip'
```

기본 모델은 최초에 수십 GB 이상을 다운로드합니다. 일부 gated 모델은 해당 Hugging Face 계정의 접근 승인이
필요할 수 있습니다. 다운로드가 인증 오류로 중단되면 읽기 권한이 있는 `HF_TOKEN`을 현재 PowerShell 환경변수로
설정하고 같은 설치 명령을 다시 실행합니다. 토큰은 저장소나 ZIP에 넣지 않습니다. 정상 다운로드 파일은 재사용합니다.

AI 환경은 `Server/portable/Dockerfile`, 최초 설치는 `Server/portable/setup.ps1`, AI 실행 구성은
`compose.ai.yaml`에 있습니다. 대화·음식·관절·진화는 서로 다른 Python 환경을 사용합니다.
진화 요청을 처리할 때 대화 GPU 프로세스를 종료하고, 진화 단계들을 순서대로 실행한 뒤 대화를 복구합니다.
음식·관절 인식은 CPU에서 계속 사용할 수 있습니다.

새 진화 이미지 단계는 **Qwen-Image-Edit-2511 + HealthMon epoch-10 LoRA**를 사용합니다.
DiffSynth와 Transformers 버전을 고정하고 새 가중치의 해시·적용 대상이 일치해야 실행합니다.
기존 이미지 모델은 진화 계획·검증 용도로 남아 있으며 3D 재구성·리깅 단계도 별도로 유지합니다.

기존 `.runtime/native-server.json` 또는 `.runtime/local-services.json`이 있는 PC에서는 설치를 실행해도
기존 실행기·DB·진화 기록을 자동으로 Docker 환경으로 전환하지 않습니다. 새 PC에서만 통합 실행을 자동 활성화합니다.
기존 PC의 전환은 저장 데이터와 생성 파일 경로를 확인한 뒤 진행합니다.

설치 완료 기록의 `inference_verified: false`는 **파일 준비 완료와 실제 추론 검증을 구분**하기 위한 값입니다.
설치만으로 추론 성공을 표시하지 않습니다. 진화는 실제 모델 생성·다운로드·홈 외형 교체·앱 재실행 후 유지까지
검증하고, 완료 화면의 슬라임 외형·정면·화면 잘림을 별도로 확인합니다. 화면 연출만 호출한 캡처는 실제 진화 결과가 아닙니다.
현재 초기종은 게임의 슬라임이며, 2511 생성기는 슬라임 부모 계약이 없는 이전 동물 입력을 거부합니다.

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
