# 공용 서버 3D Gateway

`healthmon.ai.v1` 진화 요청을 기존 Qwen 이미지 생성·TRELLIS.2·RigAnything 파이프라인에 연결합니다.
HTTP 서비스는 작업을 SQLite 저널에 저장하고, 별도 GPU worker가 생성 작업을 처리합니다.

## 계약

- `PUT /v1/evolutions/{job_id}`: 동결한 상태·진화 프로필·부모 정보 등록
- `GET /v1/evolutions/{job_id}`: 동일 작업 상태 조회
- `GET /v1/assets/{job_id}/model.glb`: 인증된 결과 다운로드

기본 지원 단계는 초기종에서 **1→2→3 순차 진화**입니다.
`HEALTHMON_GPU_SUPPORTED_STAGES`로 실행할 단계 집합을 지정할 수 있습니다.
동일 ID·입력은 같은 작업을 반환하며, 같은 ID의 다른 입력은 409로 처리합니다.
각 단계는 직전 부모 revision과 공용 서버의 v2.2 프로필을 검사합니다.
11개 appearance를 이미지 설계와 최종 프롬프트에 반영합니다.

첫 요청의 `parent_asset`은 PNG, 종 계약과 이미지·모델 SHA를 포함합니다.
이 정보를 검증해 부모와 작업을 원자적으로 등록합니다.
이후 단계는 저널에 저장한 이전 생성 결과를 계승합니다.
재시작할 때 작업 저널과 부모 이미지를 유지합니다.
완료 자산은 원본 품질로 보관하며 크기 상한은 64 MiB입니다.

## 실행

프로젝트의 GPU Python 환경에서 서버 전용 `AI_SERVER_TOKEN`과
ignored 작업 경로 `HEALTHMON_GPU_WORK_ROOT`를 환경변수로 설정합니다.

```sh
python -m Ai.Generation3D.runtime.common_gateway.cli prepare --work-root WORK_ROOT --model-root MODEL_ROOT --vendor-root VENDOR_ROOT
python -m uvicorn Ai.Generation3D.runtime.common_gateway.service:from_env --factory --host 127.0.0.1 --port 18093
```

동일 GPU의 다른 추론 작업을 종료한 뒤 worker를 실행합니다.

```sh
python -m Ai.Generation3D.runtime.common_gateway.cli run-once --work-root WORK_ROOT --model-root MODEL_ROOT --vendor-root VENDOR_ROOT --allow-gpu
```

기존 부모 자산을 가져올 때는 `cli bind-parent`를 사용합니다.
일반 새 펫은 공용 서버의 기본 초기종과 자동 부모 연결을 사용합니다.
worker는 기존 `healthmon-3d:3090` 이미지와 읽기 전용 모델·vendor mount를 사용합니다.
커널 캐시와 작업 출력은 작업 경로에 별도로 저장합니다.
GPU 단계의 lease와 고정 작업 ID로 중단 후 재시도를 관리합니다.

공용 서버의 AI 주소는 [로컬 router](../../../../Server/local_probe/README.md)를 통해
대화·음식·진화 기능을 함께 연결할 수 있습니다.
초기종 설정은 [공용 서버](../../../../Docs/COMMON_SERVER.md)를 참고합니다.

## 테스트

```sh
python -m pytest Server/tests/test_gpu_v22_adapter.py Ai/Generation3D/runtime/unity/test_jobs.py Ai/Generation3D/runtime/unity/test_species_contracts.py Ai/Generation3D/runtime/unity/test_second_stage.py Ai/Generation3D/runtime/unity/test_evolution_gate.py -q
```
