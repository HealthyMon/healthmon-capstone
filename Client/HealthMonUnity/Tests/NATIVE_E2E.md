# Unity Play 통합 테스트

프로젝트에 지정된 Unity Editor에서 기존 `MainARScene`과 공용 서버의 연결을 검사합니다.
테스트 컴포넌트는 `#if UNITY_EDITOR`로 빌드에서 제외되며 씬·프리팹에 저장하지 않습니다.

## 준비와 실행

1. 별도 PostgreSQL DB와 `APP_ENV=test`, 전용 owner·토큰·펫을 준비합니다.
2. `native-e2e.example.json`을 ignored `.runtime/unity-native-e2e.json`으로 복사합니다.
3. 서버 인스턴스·owner·펫 ID와 fixture의 전체 예상 상태를 입력합니다.
4. 토큰은 `HEALTHMON_NATIVE_E2E_TOKEN` 또는 ignored 설정 파일에 전달합니다.
5. `MainARScene`에서 **HealthMon → Verification → Run isolated native E2E**를 실행합니다.

다른 설정 파일은 `HEALTHMON_NATIVE_E2E_CONFIG`로 지정합니다.
출력은 프로젝트의 ignored `Temp/NativeE2E/<run-id>`에 저장합니다.

fixture 준비 도구는 저장소 루트에서 실행합니다.

```sh
python Client/HealthMonUnity/Tests/prepare_native_e2e.py --ai-key-config .runtime/local-gpu-probe/private.json
```

도구는 `.runtime/test-connection.json`의 로컬 admin 설정으로 새 test DB를 생성하고
API 환경 map과 fixture 파일을 `.runtime`에 작성합니다.
해당 환경을 로드한 별도 프로세스에서 공용 API를 실행합니다.

```sh
python -m uvicorn Server.healthmon.app:create_app --factory --host 127.0.0.1 --port 18092
```

## 검사 옵션

| 설정 | 내용 |
| --- | --- |
| `run_chat` | 생산 대화 요청·응답·UI와 전달 상태 |
| `run_workout_smoke` | 운동 저장·상태 갱신·동일 ID 재전송 |
| `run_auth_recovery_smoke` | 동일 서버·계정·펫의 재인증 |
| `run_dialogue_layout_smoke` | 긴 문구와 버블 스크롤 |
| `run_food_smoke` | 분석 후보·명시 섭취 확인·중복 방지 |
| `require_model_display` | 게시 자산·revision·해시·스킨 로드 |
| `simulate_ar_placement` | Editor 카메라 앞의 모델 배치 |

실제 모델 추론 검사는 real 응답을 사용합니다. UI 전용 합성 테스트는 별도 케이스로 실행합니다.
모델 케이스는 `expected_model_revision`, `expected_model_sha256`과
`expected_evolution_profile`을 fixture에 고정할 수 있습니다.
단계 경계는 9/10·19/20·29/30이며 체형·성격 축을 서로 다른 fixture로 준비합니다.
모델과 화면 캡처는 Editor Game view에서 함께 확인합니다.
