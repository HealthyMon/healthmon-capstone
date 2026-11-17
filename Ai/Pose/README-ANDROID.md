# HealthMon 관절 AI — Android 촬영

Android 휴대폰의 HealthMon Unity 앱에서 촬영하고, USB로 연결된 Windows PC에서 RTMPose를 실행합니다. Mac 앱은 사용하지 않습니다. 현재 개발용 연결은 USB이며 휴대폰 단독 추론이나 일반 Wi-Fi 연결은 제공하지 않습니다.

## 실행

1. PC에서 최초 한 번 `Setup-PoseAI.cmd`를 실행합니다.
2. Android 휴대폰의 개발자 옵션에서 USB 디버깅을 켜고 PC에 연결합니다. 휴대폰에 나타나는 이 PC의 연결 허용은 사용자가 직접 승인합니다.
3. 기존 AI 최초 설정 후 프로젝트 루트의 `Start-AI.cmd`로 AI 전체를 시작하고, `Connect-PoseAndroid.cmd`로 `adb reverse tcp:18095 tcp:18095`를 설정합니다. USB 연결 도구는 모델을 시작하지 않습니다. 게임 백엔드는 별도로 제어합니다.
4. 휴대폰에 개발용 APK를 설치하고 **운동 → 훈련 준비**에서 카메라 권한을 허용합니다. 연결 설정은 앱 내부에서 자동 적용됩니다.
5. 필요한 관절이 모두 보이게 휴대폰을 고정하고 **훈련 시작**을 누릅니다. 전면 카메라가 기본이며 시작 전에 카메라를 전환할 수 있습니다.
6. 종료 후 `Disconnect-PoseAndroid.cmd`, `Stop-AI.cmd`를 실행합니다. USB를 뽑거나 휴대폰을 재부팅하면 연결 명령을 다시 실행합니다.

여러 장치가 연결되면 `Connect-PoseAndroid.cmd -Serial 장치ID`로 선택합니다. adb가 자동 검색되지 않으면 `-AdbPath "Android SDK의 platform-tools\adb.exe"`를 지정합니다. 연결 스크립트는 다른 포트 매핑을 지우거나 덮어쓰지 않습니다. AI 서비스는 계속 PC의 loopback에서만 동작합니다.

운동 화면에는 서버 주소 입력이나 USB 연결 표시가 없습니다. 기본 주소는 내부 설정 `http://127.0.0.1:18095`입니다. 개발 중 주소 변경이 필요하면 **설정 · 관리 → 연결·설정 → 관절 AI · 개발 설정**을 사용합니다. 이 항목과 저장된 주소 재정의는 Unity Editor 또는 Development Build에서만 사용되며, 다음 운동부터 적용됩니다. 잘못 저장된 주소는 기본 설정으로 대체됩니다.

## APK

프로젝트 버전과 동일한 Unity **6000.4.6f1**, Android Build Support, JDK 17, NDK r27c, SDK가 필요합니다. Unity 메뉴 **HealthMon → Pose → Build Android preview APK** 또는 배치 모드의 `-buildTarget Android -executeMethod HealthMonAndroidBuild.BuildPreview`로 빌드합니다.

기본 출력: `.runtime/apk/HealthMon-Pose-Android.apk`. 이번 검증 APK는 찾기 쉽게 프로젝트 루트의 `HealthMon-Pose-Android.apk`에도 복사했습니다. ARM64 개발용 패키지 ID는 `com.healthmon.capstone.posepreview`이며 기존 `com.healthmon.capstone` 앱과 저장 데이터를 덮어쓰지 않습니다. 앱 표시 이름은 `HealthMonUnity`입니다. 기존 부트/홈/운동 화면을 포함하며 첫 실행에서 닉네임 설정 후 홈으로 진입합니다.

이 APK는 Android 10(API 29) 이상 ARM64용입니다. 전체 게임의 기존 ARCore/Depth 필수 설정을 유지하므로 해당 기기 지원 여부도 실기기에서 확인해야 합니다. 로컬 HTTP는 개발 빌드의 loopback 주소에 허용하며 배포용 HTTPS 서버 설정은 별도로 필요합니다. 빌드 메서드는 일시 변경한 앱 ID/인터넷/HTTP/스크립팅/아키텍처/미리 로드할 에셋 설정을 복원합니다.

## 휴대폰 동작

- Android Camera 권한을 확인하고 사용자의 응답 후 카메라를 엽니다. 거절하면 설정 안내를 표시하며 운동을 시작하지 않습니다.
- 운동 화면은 세로 방향으로 고정하고 닫으면 기존 방향 설정으로 돌아갑니다. AR 세션이 별도 오브젝트에서 카메라를 점유하는 경우 운동 동안 정지하고 닫으면 기존 상태를 복원합니다.
- 카메라 회전/수직 반전을 보정합니다. 요청 해상도를 무시하는 기기는 전송 영상을 최대 변 960픽셀로 제한합니다. 추론 요청은 동시에 한 개만 보냅니다.
- 촬영 중 화면 꺼짐을 막고 종료 시 원래 설정으로 복원합니다. 앱이 백그라운드로 가면 카메라를 해제합니다. 복귀하면 서버의 일시정지를 확인하고 카메라를 다시 연 뒤 **훈련 재개**를 기다립니다.
- 사용자 영상은 저장하지 않으며 횟수/운동 종류/시간만 휴대폰의 앱 저장소에 기록합니다. USB 연결 단절 시 확인된 횟수를 유지합니다.

## 검증 범위

2026-11-17 검증: 회전 4방향 × 수직 반전 및 크기 제한 11개 검사, 기존 운동 카운터/API 테스트 86개 통과. Unity의 실제 Android IL2CPP 빌드와 APK v2 서명, ARM64, 카메라/인터넷 권한, loopback 네트워크 리소스를 확인했습니다. 실제 플레이어 빌드에서 발견한 기존 `EvolutionOrbGraphic.OnValidate`의 에디터 전용 코드 누락도 수정했습니다.

PC의 OBS 가상 카메라에 공개 운동 영상을 공급해 실제 WebCamTexture → JPEG → RTMPose를 실행했습니다. 카메라 재연결, 서버 일시정지 확인, 명시적 재개, 횟수 보존을 포함한 14개 검사 통과, 런타임 예외 0개입니다. 이는 Android 기기의 권한/드라이버 테스트를 대신하지 않습니다.

Android 휴대폰은 이번 작업 중 연결할 수 없으므로 **실기기 촬영 완료로 간주하지 않습니다**. 이후 기기에서 권한 허용/거절/설정 복귀, 전면·후면 방향, 세로 관절 표시, 백그라운드 복귀, USB 단절/재연결, 세 운동의 반복 횟수와 저장을 확인해야 합니다.

구현 근거: [Unity Android 권한](https://docs.unity.com/en-us/engine/6000.0/manual/platform-specific/android/developing/device-features-and-permissions/requesting-permissions), [Android adb 역방향 연결](https://developer.android.com/develop/ui/views/layout/webapps/access-local-server).
