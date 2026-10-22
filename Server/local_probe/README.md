# 로컬 AI Gateway

공용 서버의 `healthmon.ai.v1` 요청을 기존 LLM·임베딩·음식 모델에 연결합니다.
CPU 공용 API와 별도 프로세스로 실행하며 모델은 지정한 로컬 경로에서 읽습니다.

| 서비스 | 기본 주소 | 기능 |
| --- | --- | --- |
| `router` | `127.0.0.1:18090` | 기능별 요청 라우팅 |
| `gpu_gateway` | `127.0.0.1:18091` | 대화·임베딩 |
| 3D Gateway | `127.0.0.1:18093` | 진화·GLB |
| `vision_gateway` | `127.0.0.1:18094` | 음식 분석 |

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
