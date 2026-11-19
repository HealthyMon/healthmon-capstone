# HealthMon Unity 관절 AI — Windows

`feature/poseai`의 RTMPose-L / YOLOX-tiny / 운동 카운터를 HealthMon Unity 화면에 연결했습니다. Windows Python 3.12와 ONNX Runtime CPU를 사용합니다. Mac, CoreML, PySide6, Mac 앱 실행기는 필요하지 않습니다. 기존 `mac-exercise-counter` 폴더 이름은 원본 알고리즘 경로이며, 그 안의 Qt 화면이나 Mac 실행 스크립트를 실행하지 않습니다.

## 실행

1. 처음 설치할 때 저장소 루트의 `Setup-PoseAI.cmd`를 실행합니다. 프로젝트 전용 `.runtime/pose-venv`에 고정 버전 패키지를 설치하고 공식 모델을 내려받아 SHA-256을 확인합니다. 기존 LLM/진화 AI 환경은 변경하지 않습니다.
2. 기존 AI 최초 설정 후 `Start-AI.cmd`를 실행합니다. 대화·음식·진화·관절 AI가 함께 시작됩니다. 관절 AI 주소는 `http://127.0.0.1:18095`입니다.
3. Unity Hub에서 `Client/HealthMonUnity`를 열고 `Assets/HealthMon/Scenes/MainARScene.unity`를 실행합니다. 저장된 씬에 UI와 진입 버튼이 포함되어 있어 별도 설치 메뉴는 필요 없습니다.
4. 하단 **운동** → 종목 선택 → **훈련 준비** → **훈련 시작**을 누릅니다. 카메라 장치가 필요합니다. 연결 주소는 내부에서 자동 적용됩니다.
5. 끝나면 **훈련 종료**, AI 전체를 끌 때는 `Stop-AI.cmd`를 실행합니다.

일반 실행·종료는 백엔드(`Start/Stop-Backend.cmd`)와 AI 전체(`Start/Stop-AI.cmd`) 두 묶음입니다. 관절 AI는 CPU에서 실행되므로 대화·3D 모델의 GPU 메모리를 추가 점유하지 않습니다. 관절 기능만 격리 검증할 때는 내부 도구 `Ai/Pose/pose-runtime.ps1 -Action start/stop`을 사용할 수 있습니다.

## 화면과 기록

- 기존 HealthMon의 파란 패널, 한글 폰트, 민트/금색 버튼을 재사용합니다. 홈의 기존 기능을 유지하고 위쪽 메뉴에 여덟 번째 **운동** 버튼을 추가했습니다.
- 스쿼트, 팔굽혀펴기, 컬 선택과 촬영 안내, 카메라 전환, 실제 관절 표시, 횟수/각도/진행 상태, 일시정지/재개, 대상 재선택, 결과 화면을 제공합니다.
- 준비 → 굽힘 → 복귀의 완전한 반복만 셉니다. 컬은 신체 기준 좌우를 구분합니다. 가림·입력 단절·대상 변경은 진행 중인 반복을 취소하며 이미 완료한 횟수는 유지합니다.
- 카메라 권한/장치 없음과 서버 연결 실패를 안내합니다. 연결이 끊기면 횟수를 임의로 늘리지 않고 마지막 확인값을 유지합니다. 재연결은 일시정지 상태로 돌아온 뒤 사용자가 재개합니다.
- 사용자 영상은 디스크에 저장하지 않습니다. 결과만 Unity `Application.persistentDataPath/pose-workouts.json`에 최근 100개까지 저장합니다. Editor 검증 영상의 기록은 `Temp/PoseVerification`에 분리합니다. 이 기록으로 게임 재화·경험치를 임의 지급하지 않습니다.

## 연결 구조

`HealthMonPoseView`는 화면, `HealthMonPoseScreen`은 카메라/상태/기록, `HealthMonPoseClient`는 HTTP 연결을 담당합니다. `Ai/Pose/unity_service.py`는 기존 카운터를 재사용합니다. Unity는 동시에 한 프레임만 전송하고 지난 프레임을 쌓지 않습니다. 표시 영상과 관절은 같은 추론 결과입니다. 카메라 회전과 수직 반전을 보정한 JPEG를 보냅니다.

- `GET /health`: 준비/실행 상태
- `POST /sessions`: 운동 세션 생성 (`exercise`, 선택적 `squat_view`)
- `POST /sessions/{id}/frames?sequence=N&timestamp=T`: JPEG 프레임 → 실제 관절·횟수·표시 영상
- `POST /sessions/{id}/control`: `pause` 또는 `retarget`
- `DELETE /sessions/{id}`: 종료와 최종 횟수

세션별 카운터가 분리되고, 동일 프레임 재전송은 다시 세지 않으며 이전 프레임/시간 역행은 거부합니다. 세션은 최대 4개, 비활성 만료는 30분입니다. 기본 서비스는 이 PC의 loopback에만 바인딩하며 브라우저 Origin 요청을 거부합니다. Android 휴대폰 촬영은 [Android 실행 안내](README-ANDROID.md)의 `Connect-PoseAndroid.cmd` USB 연결을 사용합니다. Android C# 컴파일 검증과 실제 단말 실행 검증은 구분합니다.

## 검증

2026-11-17 Windows에서 기존 알고리즘 + 새 API 테스트 86개와 Unity Editor/Android 코드 컴파일을 통과했습니다. Unity에서 공개 실제 운동 영상 402프레임을 HTTP로 추론해 스쿼트 3회, 팔굽혀펴기 5회, 컬 좌우 각 1회를 표시·저장했고, 일시정지/재개/종료를 포함해 431개 확인 항목, 런타임 예외 0개를 확인했습니다. 검증 미디어 출처는 원본 `mac-exercise-counter/assets/SOURCES.md`에 있습니다. 모델과 카운팅 기준을 이번 UI 작업에서 임의로 완화하지 않았으며, 원본 README에 기록된 정면 스쿼트 4회 중 1회 누락 한계는 남아 있습니다.

추가로 연결 실패·중간 단절·재연결·빈 화면의 0회 유지·대상 재선택·중복 종료·기록 중복 방지 등 19개 항목을 검증했습니다. 이 PC에는 물리 웹캠 없이 `OBS Virtual Camera`만 등록돼 있었습니다. [pyvirtualcam](https://github.com/letmaik/pyvirtualcam)으로 공개 검증 영상을 기존 가상 카메라에 공급하고, 별도의 Editor 프레임 주입 없이 실제 `WebCamTexture` → JPEG → HTTP → RTMPose → 화면/기록 경로도 25프레임과 스쿼트 1회로 확인했습니다(7개 항목, 예외 0개). 가상 카메라 공급기는 검증 전용이며 제품 실행에는 필요 없습니다. Android 후속 작업에서는 실제 APK 빌드 및 카메라 앱 복귀 14개 항목도 통과했습니다. 물리 웹캠·Android 실기기 촬영은 아직 미검증입니다.

```powershell
$env:PYTHONPATH = "$PWD/Ai/Pose/mac-exercise-counter/src"
.runtime/pose-venv/Scripts/python.exe -m pytest Ai/Pose/mac-exercise-counter/tests Ai/Pose/test_unity_service.py -q
```

씬 UI를 다시 설치해야 할 때만 `HealthMon > Pose > Rebuild exercise screen`을 사용하세요. 기존 씬을 여는 작업이므로 편집 중인 씬은 먼저 저장하세요. 네이티브 검증 메뉴는 명시적인 `.runtime/pose-verification.json`의 `isolated_fixture: true` 설정이 있을 때만 실행됩니다.
