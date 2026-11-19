# 로컬 AI Gateway

공용 서버의 `healthmon.ai.v1` 요청을 기존 LLM·임베딩·음식 모델에 연결합니다.
CPU 공용 API와 별도 프로세스로 실행하며 모델은 지정한 로컬 경로에서 읽습니다.

| 서비스 | 기본 주소 | 기능 |
| --- | --- | --- |
| `router` | `127.0.0.1:18090` | 기능별 요청 라우팅 |
| `gpu_gateway` | `127.0.0.1:18091` | 대화·임베딩 |
| 3D Gateway | `127.0.0.1:18093` | 진화·GLB |
| `vision_gateway` | `127.0.0.1:18094` | 음식 분석 |
| 관절 AI | `127.0.0.1:18095` | CPU 자세 인식·운동 횟수 |

## 백엔드와 AI 별도 실행

| 목적 | 시작 | 종료 |
| --- | --- | --- |
| API·PostgreSQL | `Start-HealthMon.cmd -Target Backend` | `Stop-HealthMon.cmd -Target Backend` |
| 대화·음식·3D·관절 AI 그룹 | `Start-HealthMon.cmd -Target AI` | `Stop-HealthMon.cmd -Target AI` |
| 전체 | `Start-HealthMon.cmd` | `Stop-HealthMon.cmd` |

먼저 백엔드만 실행할 수 있습니다. 새 PC의 AI 기본 설정은 `disabled`이며 가짜 응답으로
AI 성공을 대신하지 않습니다. API의 `/health/ready`는 DB 준비 상태만 검사합니다.
아래 최초 설정 후 `Start-HealthMon.cmd -Target Backend`를 한 번 실행하면 연결 주소·토큰이 API에 적용됩니다.
그 뒤 AI 온·오프는 API·DB 재시작이나 `.env` 변경 없이 가능합니다.
기존 native 설치도 같은 CMD의 `Backend` / `AI` 구분을 따릅니다.
관절 환경은 최초 한 번 `Start-HealthMon.cmd -Target Setup`로 준비합니다. 일반 AI 실행/종료에는 관절 AI도 포함되며,
`Start/Stop-HealthMon.cmd`의 전체 실행/종료에도 포함됩니다. 백엔드만 켜거나 끄는 명령은 관절 AI를 건드리지 않습니다.
관절 시작 실패는 전체 AI 준비 완료로 표시하지 않고, 종료 시 한 그룹 실패가 다른 그룹 종료를 막지 않습니다.

## AI 최초 설정

로컬 AI 환경을 준비한 후 `local-services.example.json`을
`.runtime/local-services.json`으로 복사해 이 PC의 Python과 비공개 설정 경로를 지정합니다.
경로는 저장소 루트 기준 상대 경로나 절대 경로를 사용할 수 있습니다.
실행 Python에는 `fastapi`, `uvicorn`, `httpx`, `python-dotenv`, `psutil`, `filelock`, `Pillow`가 필요하고,
대화 Python에는 기존 Qwen 추론 환경이 필요합니다. 음식 모델의 Python은 Vision 설정에서 지정합니다.
GPU 모델 가중치·학습 환경·인증 정보는 Git에 넣지 않습니다.

`evolution_config`는 다음 형태의 비공개 JSON입니다. `work_root`는 이 설치만의 작업 저널이며
`model_root`, `vendor_root`는 준비한 기존 3D 모델·소스 경로입니다.

```json
{
  "work_root": ".runtime/local-evolution",
  "model_root": "PATH_TO_GENERATION3D_MODELS",
  "vendor_root": "PATH_TO_GENERATION3D_VENDOR"
}
```

3D 실행에는 준비된 `healthmon-3d:3090` Docker 이미지와 NVIDIA GPU도 필요합니다.
기존 테스트 설치의 base-only·Vision·3D 설정이 있으면 실행기가 PC별 통합 설정을 자동 작성합니다.
과거 실험 작업을 다시 생성하지 않도록 새 통합 3D 저널을 사용합니다.

설정 파일을 준비한 뒤 `Start-HealthMon.cmd -Target Backend`를 실행하면 Docker API의 AI 주소와 서버 전용 인증을
연결합니다. 이 단계에서는 모델을 불러오거나 GPU를 사용하지 않습니다.
`Start-HealthMon.cmd -Target AI`가 모델·Python·3D 이미지의 준비 상태를 검사하고 AI 프로세스를 시작합니다.
AI를 먼저 켠 경우에도 백엔드 시작 시 같은 연결 설정을 적용합니다.
`Start-HealthMon.cmd`는 백엔드와 AI를 순서대로 켜는 편의 명령입니다.
이미 실행 중인 같은 설정의 서비스는 재사용합니다. 단일 GPU에서는 요청된 3D 생성 동안 대화 모델을
잠시 내리고 완료·실패 후 다시 올립니다. 음식 분석은 CPU에서 계속 실행합니다.
대화 모델은 기본 `warmup=true`로 시작 시 GPU에 로드하고 상주합니다. 응답 후 임시 생성 캐시만 해제하며 모델은 유지합니다.
3D는 큐에 작업이 있을 때 실행하고, 대화 프로세스 종료를 기다린 뒤 GPU를 사용합니다.
임베딩·음식·관절 모델은 CPU를 사용합니다. 관절 모델은 첫 훈련 요청에서 로드한 뒤 프로세스가 종료될 때까지 유지합니다.
따라서 통합 AI 실행은 GPU 모델 네 개를 동시에 올리는 동작이 아닙니다. 대화 모델의 가중치 외에도
문맥·출력·CUDA 작업 공간과 Unity 등 다른 앱이 VRAM을 사용하므로 실제 여유 메모리를 확인해야 합니다.
기본 캐릭터를 보여주는 데에는 새 3D 생성이 필요하지 않습니다.

`Stop-HealthMon.cmd -Target AI`는 백엔드를 유지하며 로컬 AI 종료만 요청합니다. 이미 생성 중인 3D 작업은 끝난 후 종료합니다.
종료 대기 중 재시작은 거부하며 `stopped`가 된 후 다시 켭니다. 종료 중에는 대화 모델을 다시 로드하지 않습니다.
`Stop-HealthMon.cmd`는 이 종료 요청과 백엔드 종료를 함께 수행합니다.
오류는 `.runtime/local-services.stderr.log`, 서비스별 `local-*.stderr.log`,
상태는 `.runtime/local-services-status.json`에서 확인합니다.

로컬 모델을 설치하지 않는 PC는 `.env`에 공유 AI Gateway의 `AI_MODE=remote`, `AI_BASE_URL`,
`AI_SERVER_TOKEN`을 지정합니다. 개발 HTTP를 사용하는 경우에만 `ALLOW_HTTP_AI=true`를 지정합니다.
공유 AI의 실제 프로세스는 해당 서버에서 관리합니다. 이 PC의 CMD는 원격 서버를 종료하지 않습니다.
AI 연결이 준비되지 않으면 전체 준비 완료로 표시하지 않으며 백엔드는 유지합니다.

인증된 `GET /health/dependencies`는 `ai`, `chat`, `vision`, `evolution` 상태를 반환합니다.
로컬 라우터의 인증된 `/health/services`를 실제 조회하며 2초간 캐시합니다.
상태는 `disabled`, `off`(연결 불가 포함), `loading`, `ready`, `generating_3d`, `stopping`, `error`입니다.
공유 Gateway가 이 관측 API를 지원하지 않으면 `unknown`입니다. 준비 상태는 추론 결과의 품질이나 성공을 보장하지 않습니다.
Unity 개발 설정은 5초마다 갱신하며 대화 요청·진화 재시도의 ID는 변경하지 않습니다.

## LLM 설정

전용 test 환경에서 사용할 비공개 JSON을 ignored `.runtime/local-gpu-probe/private.json`에 준비합니다.

```json
{
  "environment": "test",
  "server_token": "REPLACE_WITH_GENERATED_SERVER_SECRET",
  "model_path": "PATH_TO_QWEN_BASE",
  "adapter_path": "PATH_TO_READY_ADAPTER",
  "expected_model_version": "v1",
  "expected_model_mode": "lora",
  "embedding_path": "PATH_TO_BGE_M3",
  "warmup": true,
  "full_personality_facts": true
}
```

LoRA는 지정한 `healthmon-model.json`의 버전·해시와 모델 파일을 확인합니다.
`base_only` 모드는 `adapter_path`를 비우고 `expected_base_revision`,
`expected_base_config_sha256`, `base_shard_audit_path`, `expected_base_shard_audit_sha256`을 지정합니다.
이때 `expected_model_version`은 `local-base-<revision>` 형식입니다.
모델 설정·shard와 선택한 구성의 해시를 확인한 뒤 로드합니다.

```sh
python -B -m Server.local_probe.gpu_gateway --config .runtime/local-gpu-probe/private.json
python -B -m Server.local_probe.router --key-config .runtime/local-gpu-probe/private.json
```

대화는 공용 서버의 Activity·Affinity·Initiative와 문맥을 system message에 전달합니다.
설정·응답 캐시·실행 파일은 비공개 설정 폴더에서 관리합니다.
같은 GPU의 LLM과 3D worker는 순서대로 실행합니다.

## 음식 분석

별도 `.runtime/local-vision-probe/private.json`에 `environment="test"`,
`vision_enabled=true`, `server_token`, `vision_python`, `vision_assets`를 지정합니다.
기존 Vision 가중치의 해시를 확인하고 CPU worker에서 JPEG/PNG를 분석합니다.
결과는 후보와 영양 추정값이며 실제 섭취는 공용 서버에서 별도로 확인합니다.

```sh
python -B -m Server.local_probe.vision_gateway --config .runtime/local-vision-probe/private.json
```

공용 서버에는 `AI_MODE=remote`, `AI_BASE_URL=http://127.0.0.1:18090`,
동일한 `AI_SERVER_TOKEN`, 개발용 `ALLOW_HTTP_AI=true`를 설정합니다.
각 서비스의 `/health`에서 설정과 모델 준비 상태를 확인합니다.

## 테스트

```sh
python -m pytest Server/local_probe -q
```

추론 모델·실행 설정·인증 정보·캐시·진단 출력은 Git과 분리해 관리합니다.
