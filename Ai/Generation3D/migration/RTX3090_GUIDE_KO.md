# RTX 3090 이식 기준

현재 실행 절차는 프로젝트 루트 README.md 및 COMMANDS_KO.md를 따른다. 가중치는 models/에 실파일로 복사됐다. 새 다운로드나 HF 로그인으로 시작하지 않는다.

- 대상: x86_64 Linux, RTX 3090 24GB.
- base: `nvidia/cuda:13.0.0-devel-ubuntu24.04`의 amd64 manifest digest `sha256:435220c0fef35cbf712e11999f8670a83835ef3cdd18564e5e8122f83078c88c`.
- Python: 모델 환경 3.12; matting은 원래 3.10.21 소스를 포함해 별도 빌드.
- PyTorch/torchvision: `2.10.0+cu130` / `0.25.0+cu130`.
- Blender: Ubuntu `4.0.2+dfsg-1ubuntu8`, embedded Python 3.12 확인을 Docker 빌드 단계에 넣음.
- Qwen/TRELLIS/RigAnything: 환경별 requirements 및 constraints 파일을 따름. 기존 관측 전체 freeze는 환경 폴더에 보존하되 ARM/NVIDIA 전용 전체 freeze를 그대로 설치하지 않음.
- CUDA 소스: CuMesh, FlexGEMM, O-Voxel, nvdiffrast, FlashAttention과 Eigen/CUTLASS/CK/cubvh 하위 모듈을 실제 포함함. setup pin이나 공개 tag로 확보한 네이티브 소스는 삭제된 원래 ARM 바이너리 빌드 commit과 동일하다고 증명할 수 없음.
- utils3d가 선언한 moderngl/glcontext는 원래 Spark에서 미설치였으나 새 환경의 정상 의존성 설치를 위해 버전 고정함. 추론 모델이나 정밀도 변경이 아님.

Dockerfile은 새 target 환경만 구축한다. 이미지 밖 기존 Spark, ARM 가상환경, CUDA cache를 변경하거나 설치에 이용하지 않는다. weights/assets는 bind mount하고 이미지에 복제하지 않는다. 환경 venv는 bind mount 밖 `/opt/healthmon-envs/`에 둔다.

기본 Qwen cuda 모드는 기존 약 39.21GB peak 때문에 24GB에 맞지 않을 수 있다. README 예제의 명시적인 기존 CPU offload 옵션을 검토하되, 같은 BF16 모델의 3090 실행 성공은 별도 확인해야 한다. 양자화/정밀도/샘플링은 자동 변경하지 않았다.

검증 구분: 소스·가중치 파일 무결성 및 구조/설정 정적 검사는 Spark에서 수행했다. 대상 Docker build, x86 native import/ABI, 24GB VRAM, 이미지 생성, GLB 생성, rig deformation은 대상 PC에서 검증해야 한다. 빌드 실패를 파일 확보 성공과 혼동하지 않는다. 실제 설치 목록은 빌드된 이미지의 `/opt/healthmon-build/*.freeze.txt`로 확인한다.

Docker/PyTorch/driver와 외부 패키지 관련 공식 근거 링크는 README에 있다. 패키지 버전의 공개 배포 여부를 확인한 결과는 `reports/pypi_dependency_availability.json`에 있으며 이는 성공적인 x86 설치나 빌드를 의미하지 않는다.
