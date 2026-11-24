# HealthMon 설치와 AI 가중치 안내

HealthMon은 운동·식사 기록을 슬라임의 성장에 연결하는 **Android AR 캐릭터 육성 게임**입니다. Unity 앱에서 육성·탐험·전투를 진행하고, Windows PC의 백엔드가 게임 데이터를 저장합니다. 관절 인식·음식 분석·대화·진화 생성은 별도 AI 서비스에 요청합니다.

**팀원 기본 테스트는 `최초 5번 설치 → 2번 백엔드 → 3번 AI` 순서입니다.** Android 휴대폰을 USB로 연결하면 **4번**으로 연결을 설정합니다. 이 설치에는 음식·관절 모델이 포함되며, 대화·진화용 대형 모델과 별도 관리하는 LoRA는 포함되지 않습니다.

## 1. 먼저 설치할 프로그램

| 프로그램·환경 | 필요한 경우 | 준비 방법 |
| --- | --- | --- |
| Windows x64 | 현재 CMD 실행기 사용 | 아래 절차는 Windows PC 기준입니다. Mac용 실행 절차가 아닙니다. |
| Docker Desktop와 WSL2 | 백엔드·음식·관절 실행 | [공식 Windows 설치 안내](https://docs.docker.com/desktop/setup/install/windows-install/)를 따라 설치하고 Linux 컨테이너 엔진을 실행합니다. 설치 과정에서 재부팅을 요구하면 먼저 완료합니다. |
| Unity Hub와 Unity **6000.4.6f1** | PC에서 게임 화면 실행 또는 APK 빌드 | [프로젝트 버전 파일](../Client/HealthMonUnity/ProjectSettings/ProjectVersion.txt)에 맞춰 설치합니다. 사용할 APK를 이미 받았다면 서버 PC에 Unity를 설치할 필요는 없습니다. |
| Unity Android Build Support, Android SDK & NDK Tools, OpenJDK | Unity에서 Android APK 빌드 | 해당 Unity 버전의 Hub 모듈로 설치합니다. [Unity Android 환경 설치 안내](https://docs.unity.com/en-us/engine/6000.0/manual/platform-specific/android/getting-started/sdksetup)를 참고합니다. |
| Android SDK Platform-Tools의 `adb` | 휴대폰 USB 연결·APK 설치 | Unity의 Android SDK에 포함된 도구를 사용하거나 [공식 Platform-Tools](https://developer.android.com/tools/releases/platform-tools)를 받습니다. |
| Git | Git 명령으로 저장소 받기·갱신 | [Git for Windows](https://git-scm.com/downloads/win)를 사용합니다. GitHub에서 받은 소스를 사용하는 경우 Git 자체는 실행 필수가 아닙니다. |
| Android Studio와 워치 프로젝트의 SDK/JDK | Wear OS 앱 또는 Android 플러그인을 직접 빌드 | [워치·Unity 연동 문서](../Wearable/Android/HealthMonWatch/docs/unity-plugin-integration.md)의 빌드 환경을 따릅니다. 서버 실행만 할 때는 필요하지 않습니다. |

기본 5번 설치에서는 Python·PyTorch·ONNX Runtime·PostgreSQL을 Windows에 각각 설치하지 않습니다. 설치 스크립트가 Docker 이미지 안에 실행 환경을 준비합니다. 음식·관절 기본 구성은 CPU를 사용하므로 이 두 기능을 위해 CUDA나 NVIDIA GPU를 별도로 준비할 필요는 없습니다.

최초 설치에는 인터넷 연결이 필요합니다. 모델 외에도 Docker 이미지, Python 패키지, Unity 에셋 등을 내려받으므로 모델 파일 크기만큼의 디스크 공간으로는 부족합니다. 대화·진화까지 실행하려면 별도의 GPU 실행 환경과 모델 저장 공간이 필요합니다.

## 2. 처음 받은 PC에서 실행하기

### 소스와 환경 준비

1. GitHub의 **`develop` 브랜치**를 받습니다. `Start-HealthMon.cmd`, `Server`, `Client`, `Ai` 폴더가 같은 저장소 루트 아래에 있어야 합니다. CMD 파일 하나만 따로 옮기지 않습니다.
2. Docker Desktop을 실행하고 Linux 컨테이너 엔진이 준비될 때까지 기다립니다.
3. 저장소 루트의 **`Start-HealthMon.cmd`를 열어 5번**을 선택합니다.
4. `Setup complete`가 표시되면 설치가 끝난 것입니다. 설치 중 `Building`, `Downloading`, `exporting layers`가 보이는 것은 Docker 환경을 만드는 과정입니다.

5번이 준비하는 내용은 다음과 같습니다.

- 백엔드 API와 PostgreSQL 이미지, 로컬 테스트 연결 설정
- 음식 분석용 CPU 실행 환경과 가중치 3개, 합계 약 **565MB**
- 관절 인식용 CPU 실행 환경과 RTMPose-L·YOLOX-tiny 모델, 합계 약 **131MB**
- Git LFS 포인터로만 받은 필수 Unity 에셋 복원, 모델 SHA-256 확인

**5번은 설치만 하며 서버나 Unity 화면을 실행하지 않습니다.** Hugging Face 로그인, 대화·진화용 기본 모델 다운로드, 비공개 LoRA 다운로드도 수행하지 않습니다.

### 서버와 게임 실행

각 단계가 끝나 창이 닫히면 `Start-HealthMon.cmd`를 다시 열어 다음 번호를 선택합니다.

| 번호 | 하는 일 | 실행 후 상태 |
| --- | --- | --- |
| **1** | 백엔드와 설치된 AI를 함께 시작 | 2번과 3번을 함께 실행하는 선택지입니다. 최초 설치를 대신하지 않습니다. |
| **2** | 게임 백엔드·DB 시작 | 계정·펫·기록·성장·상점 등 게임 API를 사용할 수 있습니다. AI는 별도로 시작합니다. |
| **3** | 설치된 AI 시작 | 음식·관절을 실행하고, 대화·진화는 필요한 모델과 실행 환경이 준비된 경우에 실행합니다. 없는 기능은 `SKIP`으로 표시합니다. |
| **4** | Android USB 연결 설정 | 휴대폰으로 접속 정보와 USB 통신 경로를 전달합니다. 서버 시작·환경 설치·APK 설치를 대신하지 않습니다. |
| **5** | 최초 환경 설치 | 위의 백엔드·음식·관절 환경을 준비합니다. |
| **0** | 메뉴 닫기 | 실행 중인 서버를 종료하는 번호가 아닙니다. |

- **PC Unity 테스트:** 최초 5번 → 2번 → 필요하면 3번 → Unity Hub에서 `Client/HealthMonUnity` 열기 → `Assets/HealthMon/Scenes/BootScene.unity`에서 Play.
- **Android 테스트:** 최초 5번 → 2번 → 3번 → 개발용 APK 설치 및 USB 디버깅 승인 → 4번 → 휴대폰 앱 실행.
- **종료:** `Stop-HealthMon.cmd`에서 1번 전체 / 2번 백엔드 / 3번 AI / 4번 USB 연결 해제를 선택합니다. 서버 종료는 모델이나 저장된 게임 기록을 삭제하지 않습니다.

명령줄에서 같은 동작을 수행할 수도 있습니다. 아래 명령은 저장소 루트의 PowerShell에서 실행합니다.

```powershell
.\Start-HealthMon.cmd -Target Setup
.\Start-HealthMon.cmd -Target Backend
.\Start-HealthMon.cmd -Target AI
.\Start-HealthMon.cmd -Target Android
# 사용을 마친 뒤 서버 전체 종료
.\Stop-HealthMon.cmd -Target All
```

### 휴대폰과 워치 연결

PC의 Unity Editor와 USB로 연결한 개발용 Android 앱에는 실행기가 접속 정보를 자동으로 전달합니다. 기본 백엔드 주소는 `http://127.0.0.1:18092`이며, 이 경로에서는 주소·토큰을 매번 직접 입력하지 않습니다. 서버 시작 때 이미 연결된 휴대폰에 자동 설정을 시도하며, 나중에 연결했거나 재연결했다면 4번을 실행합니다.

휴대폰에서 개발자 옵션의 **USB 디버깅**을 켜고, PC 연결 허용 팝업을 직접 승인해야 합니다. 앱에서 카메라 권한도 허용합니다. 같은 Wi-Fi에 연결하는 것만으로 이 USB 개발 연결이 설정되지는 않습니다. 일반 배포 APK나 원격 서버의 접속 설정은 별도입니다.

APK 빌드와 관절 촬영은 [Android 안내](../Ai/Pose/README-ANDROID.md)를 따릅니다. `HealthMon → Pose → Build Android preview APK`는 별도 패키지 `com.healthmon.capstone.posepreview`를 만드는 개발용 메뉴입니다. **워치 연동은 휴대폰 앱과 워치 앱의 application ID와 서명 인증서가 일치해야 하므로**, 이 관절용 미리보기 APK를 기본 워치 앱과 그대로 조합하면 안 됩니다. 워치 테스트에는 [워치·Unity 연동 문서](../Wearable/Android/HealthMonWatch/docs/unity-plugin-integration.md)의 패키지·서명 조건을 맞춘 앱을 사용합니다.

## 3. AI 가중치가 포함된 범위

**소스코드, 기본 모델, 추가 학습 가중치(LoRA)는 서로 다른 파일입니다.** LoRA는 기본 모델에 적용하는 추가 학습 결과이므로 LoRA 파일만으로 대화나 진화 생성을 실행할 수 없습니다.

| 기능 | 필요한 모델·파일 | 현재 저장소와 설치 방식 |
| --- | --- | --- |
| 음식 분석 | `food_regions.pth`, `classifier.pkl`, `portion.pt` | **음식 영역 검출·Food2K 분류·FPB 중량 추정 모델 3개(약 565MB)**입니다. 5번이 팀 비전 소스의 고정 Git LFS revision에서 내려받아 SHA-256을 확인합니다. 파일은 `Ai/Vision/multifood/models/`에 설치하며 일반 Git 커밋에 포함하지 않습니다. 기존 단일 음식 모델은 호환 경로로 유지합니다. |
| 관절 인식 | `rtmpose-l.onnx`, `yolox-tiny.onnx` | 소스와 다운로드 명세가 저장소에 있고, **5번이 OpenMMLab 배포처에서 모델을 받습니다.** 현재 Windows·Android 경로는 CPU ONNX 추론을 사용합니다. |
| 대화 | `Qwen/Qwen3.5-9B`, `BAAI/bge-m3`, LoRA 모드에서 사용할 대화 어댑터 | 코드와 버전·해시 명세는 저장소에 있습니다. **기본 5번 설치는 이 모델과 대화 LoRA를 받지 않습니다.** 별도 준비한 로컬 모델·실행 환경을 설정해야 합니다. |
| 진화 이미지 생성 | `Qwen/Qwen-Image-Edit-2511` 등 기본 구성 파일, `healthmon_epoch10.safetensors` | 설정과 해시 명세는 저장소에 있습니다. **새 진화 LoRA 본체와 대형 기본 모델은 기본 설치에 포함되지 않습니다.** LoRA 크기는 943,905,448바이트이며 전체 진화 모델 크기가 아닙니다. |
| 진화 3D 변환·리깅 | 3D 재구성·리깅 모델과 해당 실행 환경 | 이미지 생성과 별도 단계입니다. 진화 LoRA뿐 아니라 이 단계의 모델·의존성도 준비되어야 최종 3D 캐릭터를 만들 수 있습니다. |

따라서 **GitHub 소스만 받은 상태와 모든 AI 기능을 실행할 수 있는 상태는 다릅니다.** 기본 설치를 마친 팀원은 백엔드·음식·관절 중심으로 테스트할 수 있고, 대화·진화는 선택 기능으로 별도 준비합니다. 대화·진화가 없다고 이미 준비된 다른 기능을 함께 중지시키지는 않습니다. 다만 음식·관절 모델 다운로드 자체가 실패하면 해당 기능의 설치는 완료되지 않은 것이므로 원인을 해결하고 5번을 다시 실행해야 합니다.

### 모델 확인에 사용하는 파일

| 명세 | 확인할 내용 |
| --- | --- |
| [음식 가중치 명세](../Ai/Vision/multifood/models/manifest.json) | 3개 파일의 크기와 SHA-256 |
| [관절 모델 명세](../Ai/Pose/mac-exercise-counter/models/manifest.json) | OpenMMLab 다운로드 주소, ONNX 파일명, SHA-256 |
| [대화 모델 잠금 파일](../Server/portable/model-lock.json) | 대화·임베딩의 모델 ID와 고정 revision, 어댑터 해시 |
| [진화 LoRA 명세](../Ai/Generation3D/configs/evolution_2511/model.json) | epoch-10 LoRA, 기본 모델 revision, 해시, 추론 설정 |
| [진화 기본 모델 명세](../Ai/Generation3D/configs/evolution_2511/base_models.json) | 이미지 생성에 필요한 기본 모델 구성과 파일 해시 |

명세 파일은 모델을 식별·검사하기 위한 자료이며 가중치 본체를 대신하지 않습니다. 다른 파일을 같은 이름으로 바꾸거나 버전이 다른 기본 모델에 LoRA를 임의로 연결하면 재현되지 않을 수 있습니다.

### 대화와 진화를 추가로 사용할 경우

모델 담당자가 지정된 버전의 기본 모델·추가 학습 가중치와 실행 환경을 준비한 뒤 [로컬 AI 설정](../Server/local_probe/README.md) 및 [3D 진화 구성](../Ai/Generation3D/README.md)을 적용합니다. 현재 기본 5번에 이 작업을 자동으로 수행하는 단계는 없습니다. 비공개 저장소에서 받는 파일은 해당 저장소의 읽기 권한이 필요하며, 웹사이트에 로그인한 상태가 터미널 다운로드 인증까지 자동으로 설정해 주지는 않습니다.

대화는 시작 후 GPU에 상주합니다. 진화 요청 처리 중에는 대화 GPU 프로세스를 내리고, 진화 종료 후 대화를 복구하는 구조입니다. CPU 음식·관절 서비스는 계속 사용할 수 있습니다. GPU·RAM·디스크 용량은 선택한 모델 전체와 실행 중인 다른 프로그램을 함께 고려해야 합니다.

## 4. SW 등록 자료에 사용할 프로그램 구성 설명

아래 내용은 소스코드와 모델 가중치의 관계를 설명할 때 사용할 수 있습니다.

> 헬스몬(HealthMon)은 실제 운동·식사 정보를 캐릭터 성장과 연계하는 AR 기반 육성 게임이다. 프로그램은 Unity 기반 게임 화면과 육성·탐험·전투 처리, 서버의 계정·펫 상태·운동 및 식사 기록·상점 처리, 웨어러블 데이터 연동, AI 요청 및 결과 반영 코드로 구성된다. AI 기능은 관절 인식, 음식 분석, 캐릭터 대화, 진화 이미지 및 3D 모델 생성을 포함한다.
>
> 프로그램 소스코드와 AI 모델 가중치는 분리하여 관리한다. 저장소에는 AI 호출·전처리·후처리·게임 연동 코드, 실행 환경 정의, 모델의 식별 정보 및 무결성 확인용 명세가 포함되어 있다. 음식 분석 가중치는 Git LFS로 관리하고, 관절 모델은 설치 과정에서 지정된 배포처에서 받는다. 대화·진화용 대형 기본 모델과 별도 관리하는 추가 학습 가중치는 기본 설치에 포함하지 않는다. 이들 파일을 제외한 소스 제출물은 프로그램의 구현 내용을 설명하는 자료이며, 모든 AI 기능을 즉시 실행할 수 있는 배포본을 의미하지 않는다.
>
> 대화·진화를 재현하려면 명세에 맞는 기본 모델·추가 학습 가중치·실행 환경이 별도로 필요하다. 외부 모델·라이브러리·에셋은 각 배포자의 라이선스에 따라 사용하며, 프로그램 소스에 대한 설명과 외부 구성요소의 권리 범위를 구분한다.

가중치와 에셋을 제외해 소스 사본을 제출하는 경우에는 **실제로 제출한 파일 목록과 제외한 범위**를 함께 표시합니다. 이 README 설명이나 GitHub 링크가 제출 기관에서 요구하는 신청서·소스 사본·첨부자료를 대신하지는 않으며, 추가 자료 요구 여부는 제출 기관의 안내를 따릅니다.

| 소스 경로 | 설명할 구현 내용 |
| --- | --- |
| [`Client/HealthMonUnity`](../Client/HealthMonUnity) | 게임 UI, 캐릭터 육성, AR, 탐험·전투, AI 결과 표시 |
| [`Server/healthmon`](../Server/healthmon) | 계정·게임 상태·운동 및 식사 기록·성장 규칙·상점 API |
| [`Wearable/Android`](../Wearable/Android) | 워치 운동 데이터 수집과 휴대폰·서버 연동 |
| [`Ai/Pose`](../Ai/Pose), [`Ai/Vision`](../Ai/Vision) | 관절·음식 추론 및 요청 처리 |
| [`Ai/LLM`](../Ai/LLM), [`Ai/Generation3D`](../Ai/Generation3D) | 대화·진화 모델 활용 코드와 설정 |
| [`Server/local_probe`](../Server/local_probe), [`Server/team`](../Server/team) | AI 서비스 연결·실행 관리와 팀원 PC 환경 설치 |

## 5. 설치나 연결이 안 될 때

| 증상 | 확인할 내용 |
| --- | --- |
| CMD를 켰는데 게임 창이 안 뜸 | CMD는 서버 실행기입니다. Unity Editor 또는 휴대폰 앱은 별도로 엽니다. `Building`·`exporting layers`는 최초 환경 설치 진행 표시입니다. |
| CMD가 바로 닫히거나 실행이 안 됨 | 저장소 전체를 받았는지 확인하고, 해당 폴더의 PowerShell에서 `.\Start-HealthMon.cmd`를 실행해 오류를 확인합니다. 관리자 권한만으로 해결된다고 판단하지 않습니다. |
| Docker를 찾을 수 없거나 엔진 준비 실패 | Docker Desktop 설치·첫 실행·WSL2 설정을 완료하고 Linux 컨테이너 모드인지 확인합니다. |
| `SKIP dialogue / evolution` 표시 | 기본 설치에서 예상되는 상태입니다. 이 기능을 사용하려면 별도 모델과 실행 환경을 준비해야 합니다. |
| 음식·관절도 `SKIP` 또는 해시 오류 | 모델이 없거나 불완전할 수 있습니다. 5번 설치의 다운로드·검증 결과를 확인하고 재시도합니다. |
| 카메라는 나오지만 음식 분석이 안 됨 | 카메라 영상과 서버 추론은 별개입니다. 2번 백엔드, 3번의 `food ready`, 휴대폰 연결 상태를 확인합니다. |
| 휴대폰이 서버에 연결되지 않음 | 2번·3번 실행 후 USB 디버깅 승인과 개발용 APK 설치를 확인하고 4번을 다시 실행합니다. 4번만으로 서버가 켜지지 않습니다. |
| 그림·모델·폰트가 없거나 에셋 오류 | Git LFS 포인터만 받은 상태인지 확인하고 5번의 에셋 복원 결과를 확인합니다. |
| 워치 데이터가 전달되지 않음 | 휴대폰·워치 앱 설치, 페어링, application ID와 서명 인증서 일치 여부를 확인합니다. 같은 Wi-Fi만으로 앱 연동 조건이 충족되지는 않습니다. |

`.env`, `.runtime`의 접속 토큰·계정 정보, 데이터베이스, 서명 키는 공유하거나 Git에 올리지 않습니다. 오류를 전달할 때는 실패한 기능과 오류 문구를 남기되 해당 비밀정보는 제외합니다.
