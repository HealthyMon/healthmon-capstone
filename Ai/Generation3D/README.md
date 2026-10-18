# HEALTHMON Generation3D

현재 이식 범위는 **GLB/FBX → Blender 렌더 → Qwen-Image-2.1 → BRIA matte → TRELLIS.2 512 → RigAnything → `final_rigged.glb`**이다. Spark에서 쓰던 추론 Python 코드는 보존했다. 기존 파일명을 변경하거나 새 FastAPI 서버를 만들지 않았다.

로컬 준비 폴더에는 검증된 필수 모델/설정 **42개, 47,511,319,763 bytes**와 공식 구현 및 CUDA 확장 소스가 실제로 있다. GitHub ZIP에는 동일한 사용자 코드·환경 재현 파일·manifest를 넣고, `models/`, `vendor/`, 개인 에셋을 제외했다. **파일 준비와 RTX 3090 실행 성공은 별개다. 이 패키지로 대상 환경 구축과 추론 시험을 시작할 수 있지만, 대상 Docker 빌드 및 GPU 추론은 아직 시험하지 않았다.**

| 경로 | 역할 | GitHub |
|---|---|---|
| `run_pipeline.py` | 원래 종/단계 기반 통합 진입점 | 포함 |
| `src/healthmon/` | 기존 렌더·Qwen·TRELLIS·RigAnything와 사용자 생성 로직 | 포함 |
| `scripts/` | 기존 입력 준비/실행/설치 스크립트와 단계별 명령 연결 | 포함 |
| `configs/` | 기존 설정, 이식용 경로 템플릿 | 포함; `runtime.local.json` 제외 |
| `Dockerfile`, `compose.yaml`, `.env.example` | 새 x86_64 Docker 환경 | 포함 |
| `requirements.txt`, `migration/environment/` | 모델별 독립 환경, 관측 버전·설치 제약 | 포함 |
| `tests/`, `migration/tools/` | CPU 파일 검증·경로 구성·소스 복원 | 포함 |
| `migration/model_manifest.json` | 가중치 원본/목적지 경로·revision·크기·SHA-256 | 포함 |
| `migration/source_manifest.json` | 공식 구현과 하위 모듈 commit·파일 해시 | 포함 |
| `vendor/` | 공식 구현 9개 저장소, Eigen/CUTLASS 등 하위 모듈, Python 3.10 소스 | 로컬만 |
| `models/` | 실제 필수 모델·설정·tokenizer·VAE | 로컬만 |
| `assets/`, `web/fixed/assets/` | 허용된 개인 참조·샘플 입력; 웹 서버 구현은 포함하지 않음 | 로컬만 |
| `outputs/`, `cache/`, `.venvs/` | 결과·실행 캐시·선택적 로컬 환경 | 로컬만 |
| `migration/evidence/`, `migration/source_variants/` | 기존 성공 근거, 과거 사용자 코드 차이 보존 | evidence는 로컬만; variants는 읽기 전용 기록 |

전체 파일 목록과 역할은 `migration/FILE_ROLES.tsv`, 구조는 `migration/PROJECT_TREE.txt`를 참고한다. 공개 업로드에서 서버 전체 Docker 인벤토리는 제외했다. 이전 보고서는 당시 상태의 기록이며 현재 판정은 `migration/READY_REPORT_KO.md`를 따른다.

## 대상 환경

Linux x86_64 및 RTX 3090 24GB 기준이다. Docker 안에는 Ubuntu 24.04, CUDA 13.0, Python 3.12, PyTorch `2.10.0+cu130`/torchvision `0.25.0+cu130`를 구성한다. Matting은 원래 Python `3.10.21`/NumPy `1.24.4`를 별도로 구축한다. Blender는 Ubuntu 패키지 `4.0.2+dfsg-1ubuntu8`로 고정하고 내장 Python 3.12를 검사한다. [Ubuntu 패키지 근거](https://packages.ubuntu.com/noble/blender), [PyTorch 설치 버전](https://pytorch.org/get-started/previous-versions/).

CUDA 13.0에 맞춰 Linux NVIDIA 드라이버 580.65.06 이상을 기준으로 준비한다. [NVIDIA CUDA 13.0 문서](https://docs.nvidia.com/cuda/archive/13.0.0/cuda-toolkit-release-notes/index.html). RAM 64GB 이상은 Qwen offload를 고려한 준비 권장치이며 측정된 최소 사양은 아니다. 모델 폴더 외에 Docker 이미지·빌드 임시 공간·출력에 수십 GB 이상이 추가로 필요하다.

Docker Engine와 Compose plugin 설치는 [Docker 공식 절차](https://docs.docker.com/engine/install/ubuntu/), GPU 연결은 [NVIDIA Container Toolkit 설치 절차](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)를 따른다. 다음 설정은 **개인 PC에서만** 실행하며 공용 Spark Docker에 적용하지 않는다.

```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

이 패키지는 모델 파일을 이미 포함하지만 OS/Python 패키지 설치에는 인터넷을 사용한다. Windows 호스트의 WSL2/Docker Desktop 연결은 이 조사에서 검증하지 않았다.

## 복사 후 파일 검증

현재 디렉터리를 `healthmon-capstone/Ai/Generation3D/`로 이동한다. Python 3.11 이상에서 모델을 로드하지 않고 검사할 수 있다.

```bash
python3 migration/tools/verify_ready.py
python3 -B -m unittest discover -s tests -v
```

첫 명령은 약 47.51GB 모델을 끝까지 읽는다. `--quick`은 파일 경로·크기 검사이므로 전송 후 전체 해시 검사를 대체하지 않는다. DINOv3도 실파일로 복사됐으며 HF 인증 없이 검증된다. HF snapshot 링크는 복사 시 실파일로 풀었고 로컬 cache ref를 정확한 revision에 고정했다.

모델 위치:

```text
models/
├── huggingface/models--Qwen--Qwen-Image-2.1/{snapshots,refs}/
├── trellis/huggingface/hub/
│   ├── models--microsoft--TRELLIS.2-4B/{snapshots,refs}/
│   ├── models--microsoft--TRELLIS-image-large/{snapshots,refs}/
│   └── models--facebook--dinov3-vitl16-pretrain-lvd1689m/{snapshots,refs}/
├── RigAnything/riganything_ckpt.pt
└── matting/bria-rmbg.onnx
```

GitHub만 clone했다면 같은 프로젝트 위치에 준비 폴더의 `models/`, `vendor/`, 필요한 `assets/`와 `web/fixed/assets/`를 복사한다. 공식 구현만 없을 때는 `python3 migration/tools/fetch_sources.py`로 고정 commit을 복원할 수 있다. 가중치 재다운로드는 기본 절차가 아니다. 별도 복사본도 없을 때만 `migration/tools/models.py`의 고정 revision downloader를 사용하며, 그 경우 gated 모델 인증이 필요할 수 있다.

## Docker 환경 구축

아래 명령은 대상 PC에서 수행한다. 공개 모델 구현을 이미 포함한 로컬 준비 폴더에서 빌드한다. `.dockerignore`가 가중치/개인 에셋을 이미지 빌드 전송에서 제외하고 Compose가 같은 프로젝트 폴더를 마운트한다.

```bash
export HEALTHMON_UID="$(id -u)"
export HEALTHMON_GID="$(id -g)"
docker compose config --quiet
docker compose build generation3d
docker compose run --rm generation3d nvidia-smi
```

빌드 스크립트는 기존 Spark의 ARM 가상환경·바이너리를 복사하지 않는다. 모델별 venv는 이미지의 `/opt/healthmon-envs/`에 있으므로 프로젝트 bind mount로 가려지지 않는다. 컨테이너 시작 시 현재 경로에 맞춘 `configs/runtime.local.json`을 생성한다. 이 도구가 생성한 설정만 갱신하며 수동 설정을 덮어쓰지 않는다. 실제 설치 버전은 이미지의 `/opt/healthmon-build/*.freeze.txt`에 기록된다.

CuMesh/FlexGEMM/O-Voxel/nvdiffrast는 `TORCH_CUDA_ARCH_LIST=8.6`으로 재빌드한다. 고정 FlashAttention 소스는 `FLASH_ATTN_CUDA_ARCHS=80`과 강제 소스 빌드를 사용한다. 같은 major의 낮은 minor cubin을 상위 minor에서 실행할 수 있다는 [NVIDIA Ampere 호환 규칙](https://docs.nvidia.com/cuda/ampere-compatibility-guide/index.html)에 따른 구성이다. 실제 빌드·커널 호환성은 대상 PC에서 확인해야 한다.

## 전체 실행

실제 포함된 GLB를 입력 예제로 쓸 수 있다. `prompt.txt`는 원하는 편집 내용을 직접 작성한 파일이다. 결과 폴더는 새 경로를 사용한다.

```bash
printf '%s\n' 'Keep the same character identity and create a clean full-body front-facing reference image.' > prompt.txt
# 원래 Qwen 기본값(cuda)은 기록상 약 39.21GB를 사용했다.
# 아래는 기존 CPU offload 옵션을 명시적으로 선택하는 명령이다. BF16 정밀도는 그대로다.
HEALTHMON_QWEN_MEMORY_MODE=model-cpu-offload docker compose run --rm generation3d \
  bash scripts/run_stages.sh assets/examples/lucan_s2_healthy.glb prompt.txt outputs/first_3090
```

`run_stages.sh`는 기존 Blender/Qwen CLI와 `run_image_to_rigged.py`를 연결하는 명령 래퍼다. Qwen 프로세스가 끝나야 TRELLIS를 시작하고, 기존 3D coordinator가 TRELLIS 종료 후 RigAnything을 시작한다. 원래 `outputs/gpu.lock`을 공유해 권장 진입점끼리 GPU 모델이 겹치지 않게 한다. 직접 개별 명령을 여러 터미널에서 동시에 실행하지 않는다.

결과: `outputs/first_3090/reconstruction/rigging/final_rigged.glb`. `rigged.glb`는 사용자 표현이며 원래 코드의 파일명은 `final_rigged.glb`이다. 이미지 및 단계별 로그/메타데이터도 같은 출력 폴더에 저장된다.

기존 `run_pipeline.py`도 보존했다. 다만 이 진입점은 Qwen offload 옵션을 전달하지 않는다. 3090 첫 시험에는 위 명령을 사용하고, 원래 종/진화 규칙 실행은 `migration/COMMANDS_KO.md`의 별도 설명을 따른다.

## 메모리와 실패 처리

Qwen 기본 모드의 기존 peak는 약 39.21GB다. CPU offload도 24GB에서 성공을 보장하지 않는다. 위 예제는 사용자가 기존 offload 옵션을 선택하는 것이며 기본값은 `cuda`로 유지했다. 양자화, 모델 교체, FP16 변경, 자동 해상도 축소는 적용하지 않았다. OOM 시 로그를 보존하고 기존 `--vae-tiling`, `--no-kv-cache`를 단계별 명령에서 검토한다. 정밀도/샘플링 변경이 필요하면 별도 변경으로 결정한다.

RGB/완전 불투명 이미지를 TRELLIS에 바로 넘기면 현재 없는 HF BiRefNet 모델을 요구한다. 제공하는 경로는 기존 CPU ONNX matte로 유효한 alpha를 만든 뒤 넘긴다. 마스크 검증 실패는 입력 문제로 보고하고 모델을 임의로 대체하지 않는다.

## 향후 FastAPI 연결

현재 새 API 서버는 구현하지 않았다. 서버의 작업 큐에서 `scripts/run_stages.sh`를 인자 배열로 호출하고, 프로세스 종료 코드와 출력 JSON/GLB를 확인하는 방식으로 연결할 수 있다. 입력 계약은 GLB/FBX 경로, UTF-8 prompt 파일, 새 출력 디렉터리다. 요청마다 고유 출력 디렉터리를 만들고 한 GPU 작업만 실행한다. HTTP timeout과 분리된 작업 큐/상태 저장은 향후 서버 구현 범위다. 기존 Server/LLM/Vision/Unity 코드는 변경하지 않았다.

과거 Hunyuan `last.pt`와 Mongle legacy 참조 일부는 미확보다. 현재 위 GLB/FBX 경로에는 사용하지 않으며 필수 패키지로 가장하지 않는다. 원래 LoRA 상태와 보존 범위는 `migration/READY_REPORT_KO.md`에 기록했다.

## 비공개 모델 백업

검증된 모델 백업 저장소: https://huggingface.co/emc2square/healthmon-3d-models (소유자 인증 필요). 모델은 `models/` 아래의 프로젝트 상대 경로를 보존한다. 이 GitHub 저장소에는 가중치를 포함하지 않는다. 각 모델의 원본 revision과 SHA-256은 `migration/model_manifest.json`을 따른다. 복원 후 `python3 migration/tools/verify_ready.py`로 검사한다. 모델 라이선스 조건은 비공개 보관에도 적용되며 상업 사용 허가를 뜻하지 않는다.
