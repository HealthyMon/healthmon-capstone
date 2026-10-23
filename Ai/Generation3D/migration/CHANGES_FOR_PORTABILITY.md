# 원본 보존과 이식 변경

원래 추론 Python/Shell 코드 및 일반 설정 42개는 source_code_manifest 기준 원본 Docker와 바이트 단위로 일치한다. `configs/runtime.json`만 새 환경 경로를 표현하도록 변경했다. 모델 함수/샘플러/가중치/정밀도는 수정하지 않았다.

추가한 실행 연결은 `scripts/run_stages.sh` 하나다. 기존 Blender/Qwen CLI와 기존 `run_image_to_rigged.py`를 순차 호출하며, 새로운 생성·리깅 구현을 갖고 있지 않다. Qwen 기본 memory-mode는 cuda이고 offload는 사용자 명시 선택이다.

Dockerfile/Compose/환경 빌드 및 entrypoint, 경로 생성/파일 검증/공식 소스 복원 도구, CPU 검증 테스트, 문서와 manifest는 이식용으로 추가·정리했다. 이전 migration helper는 모델 파일을 다운로드해야만 경로 설정을 만들 수 있던 조건을 제거하고 실제 복사본을 사용하도록 바꿨다.

TRELLIS 계열 캐시 목적지를 `models/trellis/`로 통일했다. snapshot 링크는 실파일로 풀었고 정확한 revision의 로컬 refs/main을 만들었다. 원본 Docker의 캐시/refs는 건드리지 않았다.

공식 구현 4개는 원본 Docker의 tracked 파일과 Git commit 객체를 복사했다. 파일 기록에 쓰이는 git rev-parse가 잘못된 부모 GitHub commit을 반환하지 않도록 각 vendor의 Git identity도 보존했다. 나머지 CUDA 빌드 소스 및 Python 3.10.21 소스는 공개 저장소에서 고정한 버전으로 새 반출본에만 확보했다. 공식 tracked source 수정은 없다.

`migration/source_variants/`는 과거 실행 코드 차이를 보존한 읽기 전용 증거이며 두 번째 개발 코드베이스가 아니다. 원래 source Docker, 다른 프로젝트/브랜치/팀원 코드, 실행 중 프로세스, GitHub에는 변경을 수행하지 않았다.
