# Unity 공용 서버 연결

Unity 프로젝트는 `Client/HealthMonUnity`이며 기본 씬은 `MainARScene`입니다.
서버 실행은 [공용 서버 안내](COMMON_SERVER.md)를 따릅니다.

## 연결

1. 지정된 Unity 버전으로 프로젝트를 열고 `MainARScene`에서 Play를 시작합니다.
2. 우상단 설정 버튼으로 **COMMON SERVER** 개발 패널을 엽니다.
3. API 주소와 사용자 토큰, 펫 ID를 입력하고 연결합니다. 펫 ID를 비우면 소유한 첫 펫을 선택합니다.
4. 서버 인스턴스·소유자·펫 검증 후 홈의 레벨·EXP·Coin·친밀도·활동성을 서버 값으로 표시합니다.

데스크톱 환경변수는 `API_BASE_URL`, `HEALTHMON_USER_TOKEN`, `HEALTHMON_PET_ID`입니다.
토큰은 비직렬화 런타임 필드에 보관합니다.
Android 에뮬레이터의 호스트 주소는 `10.0.2.2`, 실제 휴대폰은 서버 PC의 LAN/HTTPS 주소를 사용합니다.

## 화면 흐름

- **대화:** 서버의 현재 스탯·기억·성격 축을 전달하고 응답을 표시합니다. 긴 문구는 버블 안에서 스크롤합니다.
- **음식:** 사진 분석 후 반환 후보를 선택하고 실제 섭취량, 채소·과일 양, 식사 구분을 확인해 저장합니다.
- **운동:** WearableScene에서 기록·실시간 상태를 표시하고, 본인 기록으로 확인한 항목을 서버에 동기화합니다.
- **퀘스트:** 서버 목록과 보상을 사용합니다. 선택 제안은 표시 확인 후 수락·거절합니다.
- **진화:** 서버 작업 상태를 조회하고 인증된 GLB를 기존 AR 배치 루트에 로드합니다.

## 상태와 재시도

상태는 `healthmon.v2.2` 계약과 `state_version`을 검사합니다.
서버·계정·펫과 연결 세대가 다른 응답은 현재 화면에 적용하지 않습니다.
대기 중인 대화·진화는 같은 요청 ID로 재시도합니다.
동일 서버·계정·펫에서 토큰을 갱신할 때는 패널의 재인증 기능으로 요청 범위를 유지합니다.
운동 업로드는 Android WorkManager에서 대화 요청과 독립적으로 실행합니다.

## 모델과 Android 의존성

모델은 최신 서버 상태의 stage·revision·해시와 일치하는 자산을 표시합니다.
초기종과 진화 결과는 공용 서버의 인증된 같은 origin에서 다운로드하며 SHA-256을 확인합니다.
GPU 주소와 AI 서비스 토큰은 Unity에 전달하지 않습니다.

Android 빌드는 `Assets/Plugins/Android/mainTemplate.gradle`의 전이 의존성을 사용합니다.
AAR 빌드와 동기화 설정은 [Android 연동](../Wearable/Android/HealthMonWatch/docs/unity-plugin-integration.md)을 따릅니다.
Unity 테스트는 [Play 테스트 안내](../Client/HealthMonUnity/Tests/NATIVE_E2E.md)를 참고합니다.
