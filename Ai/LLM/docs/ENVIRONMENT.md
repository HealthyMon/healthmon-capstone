# 2026-09-29 실제 조사

- 작업 폴더 `E:\qwen-llm`은 최초 비어 있었음. 요청한 md가 없어 사용자 첨부에서 실행 프롬프트 229줄을 복원하고 모두 읽음.
- Windows 11 Home 10.0.22000 x86-64, Intel i7-12700, RAM 33,341,304 KiB(약 31.8GiB), 초기 가용 약 17.9GiB.
- RTX 3090 24GB, NVIDIA 드라이버 610.47, 드라이버 지원 CUDA UMD 13.3. 실제 PyTorch는 CUDA 12.6 빌드. 드라이버를 교체하지 않음.
- 최초 GPU 사용 3,113MiB, E 여유 약 1TB, C 약 95GB, D 약 1.38TB.
- Python 3.10.5. 전용 `.venv`에 torch 2.12.0+cu126 / transformers 5.5.1 / PEFT 0.18.1 설치. 전체 재현 버전은 requirements.lock.txt.
- WSL 배포판 없음, Docker CLI 28.1.1은 있으나 daemon 미실행. OS 설치·재부팅 없이 Windows 네이티브 경로를 사용.
- Visual Studio Community 2022 C++ 도구로 pgvector 0.8.2 공식 태그 빌드. PostgreSQL 17.11 포터블 서버를 프로젝트 내에 설치, 포트 55432.
- `E:\healthmon-capstone`은 기존 Git/Unity 기본 구조가 있으나 `Ai\LLM`, Server, Docs에 실제 구현 없음. Unity 게임 API·애니메이션 매핑 코드 없음. 저장소 변경하지 않음.
- 제한 검색한 관련 경로에서 train240/val60, checkpoint-60/150, 기존 시스템 프롬프트, 연구실 스크립트 없음. 연구실에 접속하지 않음. 기존 사용자 파일/캐시를 삭제하지 않음.

ms-swift 설치·기존 실행 환경이 없어 재사용할 대상이 없었다. 먼저 Windows에서 이미 검증 가능한 PyTorch/Transformers의 BF16 로딩을 확인하고 PEFT로 필요한 텍스트 LoRA만 구현했다. ms-swift의 Windows 미지원이라고 단정하지 않는다. 다른 학습 프레임워크를 혼합 설치하지 않았다.

공식 Qwen 전체 모델을 BF16 로드하되 시각 인코더와 원본 파라미터는 동결하고 `model.language_model.layers.*` Linear의 LoRA 21,639,168개 파라미터만 학습한다. 공식 채팅 템플릿 `enable_thinking=False`, assistant target 토큰에만 loss를 적용한다. GGUF/4비트로 변경하지 않았다.

공식 자료: [Qwen](https://huggingface.co/Qwen/Qwen3.5-9B), [Transformers](https://huggingface.co/docs/transformers/en/model_doc/qwen3_5), [ms-swift](https://github.com/modelscope/ms-swift), [Unsloth 가이드](https://unsloth.ai/docs/models/qwen3.5/fine-tune), [BGE-M3](https://huggingface.co/BAAI/bge-m3), [pgvector](https://github.com/pgvector/pgvector), [PostgreSQL Windows](https://www.postgresql.org/download/windows/).

Unsloth 가이드는 9B BF16 LoRA 약 22GB와 4비트 양자화 학습 비권장을 명시한다. 이 PC의 측정값과 동일하다고 가정하지 않았다. 모델 revision과 PostgreSQL 배포 파일 SHA256은 config에 기록했다.

[AI Hub 주제별 일상 대화](https://aihub.or.kr/aihubdata/data/view.do?aihubDataSe=data&currMenu=115&dataSetSn=543&topMenu=10)는 후보 페이지를 확인했으나 이번 환경에서 원문 접근/이용 조건 검증 및 인증된 다운로드를 완료하지 못했다. 확보·라이선스 검수 완료로 간주하지 않고 학습에 넣지 않았다.
