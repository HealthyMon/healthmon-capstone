# 실제 복사 및 GitHub 통합 준비 결과

현재 활성 GLB/FBX → Blender → Qwen-Image-2.1 → BRIA matte → TRELLIS.2 512 → RigAnything 경로의 파일 구성을 준비했다. 원본 Docker와 추론 코드는 보존했다. 대상 x86_64 Docker 빌드와 RTX 3090 실제 추론은 미실행이다.

| 구성 | 필수 파일 수 | 실제 복사 bytes | 전체 SHA-256 | 필수 누락 | 가중치 추가 다운로드 |
|---|---:|---:|---|---|---|
| Qwen/Qwen-Image-2.1 | 25 | 33,131,609,424 | PASS | 없음 | 불필요 |
| facebook/dinov3-vitl16-pretrain-lvd1689m | 2 | 1,212,560,553 | PASS | 없음 | 불필요 |
| microsoft/TRELLIS-image-large | 2 | 147,592,217 | PASS | 없음 | 불필요 |
| microsoft/TRELLIS.2-4B | 11 | 9,650,630,330 | PASS | 없음 | 불필요 |
| Isabellaliu/RigAnything | 1 | 2,344,595,770 | PASS | 없음 | 불필요 |
| BRIA ONNX | 1 | 1,024,331,469 | PASS | 없음 | 불필요 |

합계 42개, 47,511,319,763 bytes. 전송 중 해시 검사와 복사본 전체 재읽기 검사를 모두 통과했다. 14개 미사용 1024/encoder/부가 파일은 복사하지 않았으며 manifest에서 required=false로 구분했다.

공식 구현은 원래 Docker에서 Qwen upstream, Diffusers, TRELLIS.2, RigAnything tracked code 및 정확한 Git identity를 복사했다. 추가로 CuMesh, FlexGEMM, utils3d, nvdiffrast, FlashAttention과 재귀 하위 모듈(Eigen, cubvh, CUTLASS, CK)을 고정 commit으로 확보했다. 원래 비어 있던 TRELLIS Eigen도 포함했다.
공식/native 구현 working-tree 파일은 17,684개, 308,116,753 bytes다. Git metadata 및 Python 3.10.21 source tarball은 별도다. 저장소 9개의 commit과 파일별 hash는 source_manifest.json에 있다.

기존 코드 43개 대조: 42개 원본과 동일, configs/runtime.json만 경로 템플릿 변경. 추가한 run_stages.sh는 원래 CLI들을 연결하며 모델 함수를 구현하거나 교체하지 않는다. README/환경/검증 도구의 변경 범위는 CHANGES_FOR_PORTABILITY.md에 기록했다.

| 판단 항목 | 결과 |
|---|---|
| GitHub Push용 파일 선별 | 준비됨; 실제 Push/merge는 안 함 |
| 코드 이전 | 가능; GitHub ZIP과 로컬 폴더를 같은 소스에서 생성 |
| 실제 모델 가중치 이전 | 가능; models/에 42개 실파일 및 pinned refs 존재 |
| 공식 모델 코드/빌드 소스 | 로컬에 확보; GitHub에는 URL/commit/hash/복원 도구 제공 |
| Docker 재구축 파일 준비 | Dockerfile/Compose/독립 venv/설치 스크립트 준비; x86 build 미시험 |
| RTX 3090 실제 추론 성공 | 미검증 |

DINOv3 등 가중치는 HF symlink를 실파일로 풀어 반출했다. Qwen의 pinned revision 및 각 cache refs를 유지해 모델 파일 취득 때문에 새 HF 인증을 요구하지 않는 구성이다. tokens, API keys, 원본 가상환경, 다른 사용자 파일을 포함하지 않았다. OS/PyPI 패키지의 새 설치에는 인터넷이 필요하다.

현재 활성 필수 가중치/추론 source의 알려진 누락은 없다. 남은 실행 검증은 target Docker build, native ABI/커널, Blender Python ABI, Qwen 24GB/offload 메모리 및 end-to-end 생성/rig 결과다. 설치된 원래 ARM 확장의 build commit을 증명하지 못하는 경우 target source pin의 출처와 한계를 manifest에 표시했다.

과거 Hunyuan LoRA last.pt, adapter_targets.json 및 당시 config는 현재 없다. 해당 모델은 활성 경로에서 쓰이지 않아 필수 패키지에 포함하지 않았다. 현재 모델 가중치들은 공식 원본이며 별도 개인 학습 가중치는 발견하지 못했다. Mongle legacy 참조 10개와 원래 전체 reference ZIP도 미확보다. 복구한 partial reference ZIP과 Lucan/Tori 파일은 보존했지만, 과거 모든 numeric/profile 실험을 재현한다고 주장하지 않는다.

검증 근거: copied_weights_verified.json, copy_from_spark.json, current_code_preservation.json, source_manifest.json, ready_static_validation.json, github_selection_check.json. SOURCE Docker는 읽기 전용 조사·반출만 수행했고 새 GPU 추론이나 package 설치를 하지 않았다.

현재 로컬 폴더를 PC로 복사하면 활성 파이프라인의 가중치와 필수 추론 source 누락 없이 환경 구축과 추론 시험을 시작할 수 있다. 환경 빌드 및 실제 추론 성공 판정은 아직 내리지 않는다.

폴더/ZIP의 최종 크기·해시·전송 명령은 healthmon_3d_ready 루트의 TRANSFER_INFO.json과 DOWNLOAD_KO.txt를 참고한다.
