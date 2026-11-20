# 로컬 AI Gateway

공용 서버의 `healthmon.ai.v1` 요청을 기존 LLM·임베딩·음식 모델에 연결합니다.
CPU 공용 API와 별도 프로세스로 실행하며 모델은 지정한 로컬 경로에서 읽습니다.

| 서비스 | 기본 주소 | 기능 |
| --- | --- | --- |
| `router` | `127.0.0.1:18090` | 기능별 요청 라우팅 |
| `gpu_gateway` | `127.0.0.1:18091` | 대화·임베딩 |
| 3D Gateway | `127.0.0.1:18093` | 진화·GLB |
| `vision_gateway` | `127.0.0.1:18094` | 음식 분석 |

## CMD 통합 실행

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

이후에는 `Start-HealthMon.cmd` 하나로 대화·음식 분석·3D Gateway·자동 생성 worker와 API·DB를
함께 켭니다. Docker API의 AI 주소와 서버 전용 인증도 자동 연결합니다.
이미 실행 중인 같은 설정의 서비스는 재사용합니다. 단일 GPU에서는 요청된 3D 생성 동안 대화 모델을
잠시 내리고 완료·실패 후 다시 올립니다. 음식 분석은 CPU에서 계속 실행합니다.
기본 캐릭터를 보여주는 데에는 새 3D 생성이 필요하지 않습니다.

`Stop-HealthMon.cmd`는 로컬 AI 종료도 요청합니다. 이미 생성 중인 3D 작업은 끝난 후 종료합니다.
오류는 `.runtime/local-services.stderr.log`, 서비스별 `local-*.stderr.log`,
상태는 `.runtime/local-services-status.json`에서 확인합니다.

로컬 모델을 설치하지 않는 PC는 `.env`에 공유 AI Gateway의 `AI_MODE=remote`, `AI_BASE_URL`,
`AI_SERVER_TOKEN`을 지정합니다. 개발 HTTP를 사용하는 경우에만 `ALLOW_HTTP_AI=true`를 지정합니다.
AI 연결이 준비되지 않으면 CMD는 전체 서비스가 준비됐다는 안내를 표시하지 않습니다.

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
