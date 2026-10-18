> 이전 조사 당시 상태를 보존한 문서입니다. 현재 실제 복사/보완 결과는 READY_REPORT_KO.md와 루트 README.md를 따릅니다.

# 실제 환경 및 필수 파일 조사 결과

## 조사 범위와 보존

대상은 `seungwoo-hy3d21` (`43bfd7f61b76`)이다. 사용자가 이 컨테이너의 HEALTHMON 작업물이 본인 소유이며 필요한 파일을 복사해도 된다고 확인한 후 반출했다. 기존 컨테이너·이미지·가중치·실행 코드는 수정/삭제하지 않았고, 프로세스를 중단하지 않았다. 새 GPU 모델 실행, 환경 설치, Docker 빌드, GitHub Push를 하지 않았다. LLM/Vision/Unity 영역을 수정하지 않았다.

호스트는 aarch64이며 조사 시작 시 디스크 가용량은 약 3.1TiB였다. 코드와 허용된 개인 에셋만 새 호스트 폴더에 저장했다. Hugging Face 토큰·SSH 키·전체 환경변수·다른 사용자의 파일을 반출하지 않았다.

GitHub `HealthyMon/healthmon-capstone`의 `Ai/Generation3D/`는 조사 시 `.gitkeep`만 있었다. 마지막 해당 경로 변경 commit은 `47b0c308629ce4bc1b9f78430d13007f052ce31b`이다. 따라서 GitHub만으로 실행 코드를 복원할 수 없다.

## Docker와 환경

| 항목 | 직접 확인한 값 |
|---|---|
| 컨테이너 | seungwoo-hy3d21, 실행 중 |
| 이미지 태그 | nvcr.io/nvidia/pytorch:25.11-py3 |
| 이미지 ID | sha256:eea3fe49e8a583008e4ea66fbeb36b2a7a111db8e1e322d2f310fd697baad95b |
| RepoDigest | sha256:417cbf33f87b5378849df37983552cd1f8bc8b62fe1ceabe004de816a55dff21 |
| 대상 마운트/볼륨 | 없음. /workspace 작업물은 컨테이너 쓰기 레이어에 존재 |
| 현재 배포 코드 | /workspace/generation |
| 실행 환경·vendor·가중치 | /workspace/healthmon-evolution |
| Blender 번들 | /workspace/3d_pipeline_lab/runtime/blender_arm/root |
| ONNX 보조 모델 | /workspace/3d_model_comparison/20261005/cache/u2net/models/bria-rmbg/bria-rmbg.onnx |
| Python | 주 실행 환경 3.12.3; matting만 3.10.21 |
| PyTorch / torchvision | 2.10.0+cu130 / 0.25.0+cu130 |
| CUDA toolkit | 13.0, nvcc 13.0.88 |
| Blender | 4.0.2, libpython3.12 연결 |
| TRELLIS 확장 | CuMesh 0.0.1, O-Voxel 0.0.1, FlexGEMM 1.0.0, nvdiffrast 0.4.0, flash-attn 2.7.3 |
| 아키텍처 | 검사한 확장 6개 ELF e_machine=183(AArch64); CUDA sm_121 또는 sm_120 |

이미지 자체에는 실행 후 생성된 모델·가상환경·수정 코드가 포함되지 않는다. 이미지 태그만 이동하면 동일 문제가 반복된다. 전체 조사 메타데이터는 `reports/docker_structure.json`, `reports/docker_inventory.json`, `environment/*.packages.json`, `reports/native_binaries.json`에 있다. ARM64 가상환경과 .so 파일은 x86_64로 복사하지 않는다.

## 모델별 식별 및 복원

모든 실제 파일명·바이트 크기·해시는 `MODEL_FILES.tsv`와 `model_manifest.json`을 기준으로 한다. 전체 조사 56개 파일의 논리적 크기는 **54,101,514,614 bytes**이다. 현재 실행 경로에 필요한 복원 선택은 **47,511,319,763 bytes**이다. 두 수치에는 가중치뿐 아니라 필수 설정 등도 들어 있다. 미사용 TRELLIS 1024 전용 flow·encoder는 기본 다운로드에서 제외된다.

| 모델/역할 | 코드 commit | 모델 revision | 실제 조사 크기 | 복원/백업 |
|---|---|---|---:|---|
| Qwen-Image-2.1 | QwenLM/Qwen-Image-2.1 `1993c3a4821f977df0b6dd2661ff5b40239aa55a`; Diffusers `1d5d056ecff3a8c1d887a7dd1aa66ca4a0323458` | `d26bb61231c349cf6b7896fa83353113880e1ba3` | 33,134,949,561 | A: 공식 재다운로드; 커스텀 가중치 아님 |
| TRELLIS.2-4B | microsoft/TRELLIS.2 `75fbf0183001ed9876c8dbb35de6b68552ee08bd` | `af44b45f2e35a493886929c6d786e563ec68364d` | 16,237,485,044 | A; 현재 worker는 512 모델만 로드 |
| TRELLIS sparse decoder | TRELLIS loader 사용 | microsoft/TRELLIS-image-large `25e0d31ffbebe4b5a97464dd851910efc3002d96` | 147,592,217 | A; 별도 repo의 .json + .safetensors가 필수 |
| DINOv3 conditioning | Transformers 4.57.3; TRELLIS feature extractor | facebook/dinov3-vitl16-pretrain-lvd1689m `ea8dc2863c51be0a264bab82070e3e8836b02d51` | 1,212,560,553 | A, gated: 새 계정의 승인/인증 필요 |
| RigAnything | Isabella98Liu/RigAnything `d03cdb21dd134fa81df6b0947522469db3f78bd2` | Isabellaliu/RigAnything `30df7c0c390db1d5453c5af12da8d227c5025db6` | 2,344,595,770 | A; riganything_ckpt.pt |
| BRIA RMBG-2.0 ONNX | 기존 background_matte.py + onnxruntime 1.23.2 | rembg release `v0.0.0`, bria-rmbg-2.0.onnx | 1,024,331,469 | A; 공식 rembg 코드에 적힌 SHA-256과 일치 |
| 요청한 UniRig | 현재 코드 없음; 사용했던 commit 불명 | 원래 skeleton/skin revision·파일명 불명 | 현재 대상 파일 없음 | 원래 사용 파일/별도 백업 확보 필요 |
| 요청한 Qwen-Image-Edit | 현재 활성 구현 아님 | 원래 정확한 버전 불명 | 현재 해당 파일 없음 | Qwen-Image-2.1과 구분 필요 |

Qwen 체크포인트에는 text_encoder 4개 shard, transformer 2개 shard, VAE 1개 가중치, 각 index/config, processor의 tokenizer/vocab/merges/special tokens/chat template/preprocessor, scheduler 및 model_index가 필요하다. 단일 transformer 파일만 확보하면 실행할 수 없다.

TRELLIS는 `pipeline.json`이 지정한 모델 중 `_1024`로 끝나는 flow를 worker가 제외한다. 나머지 sparse structure flow, shape decoder, shape flow 512, texture decoder, texture flow 512와 각각의 JSON, 별도 TRELLIS-image-large decoder를 모두 복원한다. DINOv3는 config.json와 model.safetensors가 필요하며 설치된 extractor는 자체 전처리를 사용한다.

불투명/RGB 이미지를 TRELLIS에 바로 넘기면 Hugging Face의 `briaai/RMBG-2.0` BiRefNet 코드·가중치가 추가로 필요하다. 현재 그 별도 HF snapshot은 없다. 이번 명령은 기존 CPU ONNX 마스킹을 먼저 적용하고 의미 있는 alpha를 가진 RGBA를 TRELLIS에 입력한다. 이 ONNX와 HF BiRefNet을 같은 파일이라고 취급하지 않는다.

RigAnything은 vendor의 config.yaml, model/, inference.py, inference_utils/, utils/를 포함한 고정 commit 전체와 checkpoint가 필요하다. 로컬 adapter는 strict state_dict 로드를 강제하고, seed를 AST로 변경하며, proxy에서 원본 메시로 공간 기반 skinning을 전송한다. 이 커스텀 부분을 원본 그대로 보존했다. UniRig adapter가 아니다.

공식 URL: [Qwen 코드](https://github.com/QwenLM/Qwen-Image-2.1), [Qwen 가중치](https://huggingface.co/Qwen/Qwen-Image-2.1), [Diffusers](https://github.com/huggingface/diffusers), [TRELLIS 코드](https://github.com/microsoft/TRELLIS.2), [TRELLIS 가중치](https://huggingface.co/microsoft/TRELLIS.2-4B), [decoder](https://huggingface.co/microsoft/TRELLIS-image-large), [DINOv3](https://huggingface.co/facebook/dinov3-vitl16-pretrain-lvd1689m), [RigAnything 코드](https://github.com/Isabella98Liu/RigAnything), [RigAnything 가중치](https://huggingface.co/Isabellaliu/RigAnything), [ONNX 배포 해시](https://github.com/danielgatis/rembg/blob/main/rembg/sessions/bria_rmbg.py), [UniRig](https://github.com/VAST-AI-Research/UniRig).

## 가중치 무결성과 커스텀 파일

각 가중치를 끝까지 읽어 SHA-256을 계산했다. HF snapshot 심볼릭 링크는 실제 blob까지 확인하고 크기·해시를 공식 revision의 LFS 메타데이터와 대조했다. Safetensors는 header 길이·JSON·tensor offset 연속성·최종 payload 길이를 검사했다. PyTorch .pt는 ZIP 엔트리 구조와 전체 해시를 검사했으며 pickle/torch.load를 실행하지 않았다. 이 검사는 tensor 연산 또는 모델 추론 검증을 대신하지 않는다.

조사한 대상 모델 범위에서 깨진 링크, LFS 포인터, .incomplete 파일, 공식 가중치와의 해시 불일치는 없었다. Qwen shard index의 파일 목록도 보존된 파일들과 대조했다. Hugging Face 링크만 ZIP에 넣는 방식으로 백업하지 않았다. 가중치는 이번 코드·에셋 패키지에 넣지 않았다.

실행 관련 가중치가 모두 공식 해시와 일치하고 기존 runner에 별도 LoRA/adapter 로딩이 없어, **현재 활성 파이프라인에서 직접 학습한 별도 가중치는 발견하지 못했다.** 삭제되었거나 조사 범위 밖에 있던 과거 학습 파일까지 없었다는 뜻은 아니다. `reports/historical_cleanup_excerpt.json`에는 `/workspace/checkpoints` 7개 파일(395,105,151 bytes), 과거 runtime/checkpoints 및 UniRig 디렉터리 삭제 기록이 있다. 그 개별 파일명·내용은 현재 자료만으로 복구할 수 없고 필수 여부도 확인되지 않는다.

개인 커스텀 코드와 참조 이미지는 B 보존 대상으로 분류했다. 현재 generation과 과거 healthmon-evolution의 실행 관련 차이는 source_variants에 보관했다. 공개 vendor 4개는 Git tracked/untracked 변경이 없는 상태였다. 네이티브 패키지의 원래 build source 경로는 사라져 setup script의 commit pin과 설치된 바이너리 commit의 동일성을 증명할 수 없다. target용 source pin은 이 한계를 표시한다.

## 기존 실행 증거와 입력·출력 계약

| 단계 | 확보한 코드/파일 | 기존 성공 증거 | RTX 3090 상태 |
|---|---|---|---|
| GLB/FBX 렌더 | blender_tool.py render, Blender 4.0.2 | 기존 render_metadata와 GLB import/validation 기록 | 미실행; OBJ 직접 입력 불가 |
| Qwen 이미지 편집 | qwen_runner.py, QwenImage21Pipeline, 7개 가중치 shard 등 | 보존 PNG SHA `39a8e5b8dcf00e7dc50248e1e7f92234c333f9f875a1c528251093023400dcab` 일치; 768²/40step/BF16 | 미실행; 기록 peak 39.21474304GB |
| 입력 matte | prepare_3d_input.py, background_matte.py, ONNX | 기존 segmentation 기록 및 ONNX SHA 일치 | CPU 패키지 조합 별도 검증 |
| TRELLIS 512 | trellis_runner.py, 모델·decoder·DINOv3 | 7개 작업의 actual_inference_called 및 GLB 해시 재확인 | 확장 재컴파일·메모리 검증 필요 |
| RigAnything | rigging_runner.py, Blender entry, checkpoint | 같은 7개 작업에서 final_rigged.glb 해시 재확인; skin/joints 검증 기록 | Blender/Python ABI·실제 추론 미검증 |
| UniRig | 없음 | 이번 조사로 입증한 현재 실행 경로 없음 | 복구/별도 구현·검증 필요 |

검사한 기존 7개 case의 TRELLIS GLB 7개와 rigged GLB 7개의 바이트 해시가 기록과 일치했다. Qwen 기록 1건도 실제 PNG 해시와 일치했다. 단, 이것들을 서로 다른 기록에서 임의로 연결해 “OBJ → Qwen-Image-Edit → UniRig 전체 성공”으로 해석하지 않는다. 과거 문서가 가리키는 삭제된 실행 폴더는 재검증했다고 주장하지 않는다. 이번 작업에서는 새로운 렌더·샘플링·리깅을 실행하지 않았다.

렌더 출력은 front/three_quarter/side/back PNG, Qwen 입력은 순서와 역할이 지정된 1–10개 이미지+prompt, 출력은 RGBA PNG이다. TRELLIS는 matte RGBA에서 PBR textured GLB를 만든다. RigAnything은 GLB를 8192-face proxy로 처리한 후 원본 메시/텍스처에 관절과 skinning을 옮겨 `rigging/final_rigged.glb`를 만든다. 사용자 표현의 `rigged.glb`와 실제 파일명이 다르다. 기술적 binding 성공은 해부학적 관절 품질·보행 애니메이션 완성을 의미하지 않는다.

## 미확보 파일과 필요한 조치

- 원래 UniRig source checkout, 실행 adapter, config, skeleton/skin checkpoints: `/workspace/3d_pipeline_lab/runtime/unirig`, `unirig_arm`, `checkpoints`가 없다. 원래 백업에서 확보해야 정확한 과거 revision을 복원할 수 있다. 현재 공개 모델 정보는 `unirig_reference_only.json`에 참고용으로만 적었으며 과거 버전으로 오인하지 않는다.
- 원래 Qwen-Image-Edit 모델 경로/revision: 확인 불가. 현재 코드가 사용하는 Qwen-Image-2.1은 전부 식별했다.
- `healthmon_evolution_reference_pack.zip`: 원본 없음. 복구한 일부 ZIP은 새로운 해시이며 Lucan/Tori reference 경로를 위한 자료다.
- `healthmon_references/species_sheets/mongle/{A_fit_then_heavy,B_heavy_then_recovery}.png` 두 파일.
- `healthmon_references/candidate_crops_NOT_CLEAN/mongle/{A_fit_then_heavy,B_heavy_then_recovery}/stage_{0,1,2,3}.png` 여덟 파일.
- OBJ를 import하는 기존 커스텀 renderer: 현재 파일에서 발견하지 못했다. 현재 renderer에는 지원 코드가 없다.
- x86_64/sm_86 native builds, target Docker image digest, target Blender/Python ABI 검증, 24GB에서의 추론 결과: 아직 확보하지 않은 검증 항목이다.

추가 GPU 실험이나 새 기능 구현 없이 확인할 수 있는 범위는 여기까지이다. 기존 RigAnything 경로의 복원 준비와 요청한 UniRig 경로의 완전 복원 여부를 분리해야 한다.

현재 공개 UniRig 모델의 참고 revision은 `36842e2b5947e9e60f89275b83208c8e74071c63`이다. 아래 파일은 공식 저장소에서 확인한 **현재 후보**이며, 삭제된 원래 설치와 동일하다고 확인한 것이 아니다. 이번 패키지에 다운로드/통합하지 않았다.

- `skeleton/articulation-xl_quantization_256/model.ckpt`: 1,439,617,174 bytes; SHA-256 `d8cf9b42d56e7bc316d293597ecf8c4c39a8631cdd44a261ecf388242fabd0f4`.
- `skeleton/rignet/model.ckpt`: 621,660,032 bytes; SHA-256 `e68121ed9ef1ad8bd396c51e8c5e985048e45951d7e4be740b44723653659c45`.
- `skin/articulation-xl/model.ckpt`: 4,375,464,854 bytes; SHA-256 `9d40cf42fb9d4c10d8b373d9f4f557c6fbbc5ebacae7ae6b3dce5a0d8a18bc33`.
