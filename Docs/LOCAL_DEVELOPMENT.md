# 로컬 개발

## 서버

저장소 루트에서 실행합니다.

```sh
python Server/scripts/manage.py init
docker compose up -d --build
python Server/scripts/manage.py seed
```

`init`가 생성한 `.env`는 해당 작업 폴더의 설정입니다. 각 작업 폴더를 별도로 초기화합니다.
API 기본 포트는 8020이며 `init --port PORT`로 선택할 수 있습니다.
실행·인증·백업 설정은 [공용 서버 안내](COMMON_SERVER.md)를 참고합니다.

## Unity

`Client/HealthMonUnity`를 프로젝트에 지정된 Unity 버전으로 열고 `MainARScene`을 실행합니다.
개발 연결 패널에 API 주소, 사용자 토큰과 펫 ID를 입력합니다.
환경변수는 `API_BASE_URL`, `HEALTHMON_USER_TOKEN`, `HEALTHMON_PET_ID`를 사용합니다.
자세한 화면 흐름은 [Unity 연결](UNITY_COMMON_SERVER.md)을 참고합니다.

## AI 서비스

공용 서버는 `AI_MODE=remote`와 `AI_BASE_URL`, `AI_SERVER_TOKEN`으로 AI 서비스를 연결합니다.
서버 간 요청은 [AI Gateway 명세](api/ai-gateway.openapi.json)를 따릅니다.
로컬 구성은 [AI Gateway](../Server/local_probe/README.md),
진화 실행은 [3D Gateway](../Ai/Generation3D/runtime/common_gateway/README.md)를 참고합니다.

## 테스트

```sh
python Server/scripts/manage.py test
python Client/HealthMonUnity/Tests/run_contract_checks.py
```

Unity Play 테스트는 [실행 안내](../Client/HealthMonUnity/Tests/NATIVE_E2E.md)를 따릅니다.
테스트 데이터는 별도 `APP_ENV=test` 환경과 전용 사용자·펫으로 준비합니다.
