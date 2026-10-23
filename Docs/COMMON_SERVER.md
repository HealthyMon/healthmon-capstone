# 공용 서버

CPU FastAPI와 PostgreSQL pgvector가 운동·식사·대화 사건, v2.2 성장 상태,
퀘스트·보상과 AI 작업을 관리합니다. Unity와 Android는 이 서버의 상태를 조회합니다.

## 시작

### Windows에서 더블클릭 실행

각자 자기 PC에 서버를 실행하는 테스트는 [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/)
설치 후 저장소 루트의 **`Start-HealthMon.cmd`**를 더블클릭합니다.
Docker가 없으면 설치 안내를 열며, WSL 설정과 설치를 마친 뒤 다시 실행합니다.
Docker Desktop이 꺼져 있으면 실행하고 Linux 엔진 준비를 기다립니다.
호스트 Python 설치 없이 서버·DB 실행, 마이그레이션과 테스트 펫 준비까지 처리합니다.
첫 실행에는 이미지 다운로드와 빌드 시간이 필요하고 이후에는 캐시를 재사용합니다.

준비가 끝나면 `.runtime/local-server-connection.html`을 브라우저로 열어
Unity에 넣을 API 주소·계정별 토큰·펫 ID를 표시합니다. 인증 정보가 있는 로컬 파일이므로 공유하지 않습니다.
새 설정은 `APP_ENV=test`, `API_PORT=18092`, `AI_MODE=disabled`와 PC별 임의 토큰을 사용합니다.
기존 `.env`가 있으면 그대로 유지하고 실제 Compose 포트를 안내하므로 기존 `8020` 설정도 유지됩니다.
다른 사람이 실행할 때는 자기 PC에 생성된 설정을 사용하며 다른 PC의 `.env`를 복사하지 않습니다.

`http://127.0.0.1:18092/health/ready`에서 준비 상태를 확인합니다. 기존 설정의 포트가 다르면 해당 포트를 사용합니다.
`127.0.0.1`은 Unity와 서버를 같은 PC에서 실행할 때의 주소입니다.
종료는 **`Stop-HealthMon.cmd`**로 하며 DB 볼륨·펫·기록·토큰을 삭제하지 않습니다.
이 실행기는 준비된 로컬 AI 설정이 있으면 대화·음식 분석·3D Gateway와 자동 생성 worker도 함께 실행합니다.
로컬 설정이나 공유 AI 서버가 없으면 AI 준비 방법을 표시하고 중단합니다.
PC별 최초 준비는 [AI 통합 실행](../Server/local_probe/README.md)을 따릅니다.
기본 3D 캐릭터는 새 펫과 모델이 없던 기존 펫에 자동 연결합니다.

### 명령줄 실행

Git, Python 3.10 이상, Docker Compose v2를 준비합니다.
Windows Docker Desktop에서는 Linux 컨테이너를 사용합니다.

```sh
python Server/scripts/manage.py init
docker compose up -d --build
python Server/scripts/manage.py seed
```

`init`는 작업 폴더의 `.env`에 DB 비밀번호, 개발 사용자별 토큰과 서버 ID를 생성합니다.
기존 설정은 유지합니다. 토큰은 해당 로컬 `.env`의 `DEV_TOKENS`에서 확인합니다.
`seed` 출력의 소유자·펫 ID를 클라이언트 설정에 사용합니다.
API 기본 주소는 `http://127.0.0.1:8020`이며 `init --port PORT`로 바꿀 수 있습니다.

| 경로 | 용도 |
| --- | --- |
| `/health/live` | 프로세스 상태 |
| `/health/ready` | DB와 마이그레이션 준비 상태 |
| `/server-info` | 서버 인스턴스와 계약 |
| `/identity` | 인증한 사용자 |
| `/pets/{pet}/state` | 서버의 게임 상태 |

## 데이터 흐름

```text
Watch -> Phone Room -> WorkManager -> FastAPI -> PostgreSQL -> Unity
Unity chat/photo/evolution -> FastAPI -> AI Gateway -> AI service
```

`Server/healthmon`은 기존 SQL 001~003 이후 공용 마이그레이션 004~009를 적용합니다.
사건 저장, 점수, 보상과 스냅샷은 같은 펫의 트랜잭션으로 처리합니다.
`game_ledger`의 고유 키가 EXP와 Coin의 중복 지급을 방지합니다.
같은 ID와 내용은 재전송으로 처리하고, 변경 내용은 명시적인 다음 revision으로 기록합니다.
저장 시각은 UTC, 게임의 일·주 경계는 Asia/Seoul입니다.

운동은 시작 시점의 목표·단위·신체 부위를 사용합니다.
음식 사진의 분석과 실제 섭취 확인은 별도 요청이며, 사용자가 확인한 양을 점수에 반영합니다.
기록·기억 삭제는 원문과 종속 캐시를 정리하고 확정된 게임 집계 정책을 적용합니다.

## 인증과 설정

클라이언트는 API 주소, 사용자 bearer 토큰과 펫 ID를 사용합니다.
서버는 인증한 소유자와 펫 권한을 검사합니다.
개발 환경은 `DEV_TOKENS`, 운영 환경은 명시적으로 발급한 토큰의 `AUTH_TOKEN_HASHES`를 사용합니다.
Unity는 토큰을 런타임에 보관하고 Android는 Keystore 기반 암호화 저장소를 사용합니다.
DB 비밀번호와 AI 서비스 토큰은 서버에만 설정합니다.

| 설정 | 설명 |
| --- | --- |
| `APP_ENV` | `development`, `test`, `production` |
| `AI_MODE` | `disabled`, `mock`, `remote` |
| `AI_BASE_URL` | 원격 AI Gateway 주소 |
| `AI_SERVER_TOKEN` | 서버 간 인증 토큰 |
| `AI_TIMEOUT_SECONDS` | 원격 요청 제한 시간 |
| `PUBLIC_BASE_URL` | 외부 API 기준 주소 |
| `STARTER_MODEL_MANIFEST` | 초기종 manifest 경로 |

`mock`과 합성 기록은 전용 test DB와 허용한 test owner에서 사용합니다.
원격 AI는 기본 HTTPS를 사용하며, 개발 HTTP 연결은 `ALLOW_HTTP_AI=true`로 명시합니다.
휴대폰 연결에는 서버 PC의 LAN 주소, Android 에뮬레이터에는 `10.0.2.2`를 사용합니다.
운영 API는 리버스 프록시의 HTTPS 주소를 사용합니다.

## AI와 초기종

대화·음식·임베딩·진화 계약은 [AI Gateway 명세](api/ai-gateway.openapi.json)를 따릅니다.
CPU API 이미지는 GPU 라이브러리와 추론 가중치를 포함하지 않습니다.
[로컬 AI Gateway](../Server/local_probe/README.md)와
[3D Gateway](../Ai/Generation3D/runtime/common_gateway/README.md)는 별도로 실행합니다.

기본 초기종의 GLB·PNG·manifest는 `Server/assets/starter/lucan`에 있습니다.
첫 기동 시 기본 자산을 등록하고 새 펫에 연결합니다.
기존 기본 자산과 기존 펫의 연결은 유지합니다.
다른 초기종은 `Server/scripts/provision_starter.py --manifest PATH --set-default`로 등록합니다.
첫 진화는 부모 PNG·종 계약·파일 해시를 작업 입력에 동결하며, 이후 진화는 이전 단계의 결과를 계승합니다.
상세 흐름은 [3D 진화](3D_UNITY_INTEGRATION.md)를 참고합니다.

## 관리와 테스트

```sh
python Server/scripts/manage.py logs
python Server/scripts/manage.py stop
python Server/scripts/manage.py start
python Server/scripts/manage.py backup --file backups/healthmon.dump
python Server/scripts/manage.py restore --file backups/healthmon.dump
python Server/scripts/manage.py test
```

중단 시 DB 볼륨은 유지합니다. 복구는 새 `healthmon_restore_*` DB에 수행합니다.
복구 DB를 사용하려면 `.env`의 `POSTGRES_DB`를 해당 이름으로 설정하고 다시 기동합니다.
테스트 전용 작업 폴더는 `init --test`로 초기화합니다.
공용 API 명세는 [OpenAPI](api/common.openapi.json), Unity 설정은 [연결 안내](UNITY_COMMON_SERVER.md)를 따릅니다.
