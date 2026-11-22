# 프로젝트 내부 실행 환경

2026-11-21 기준 Start-HealthMon.cmd로 실행하는 LLM, 음식 분석, 공통 API의 프로젝트 자산과 DB 저장소를 이 폴더 안으로 모았습니다.

- LLM Python 패키지: `.runtime/qwen4b-venv`
- Python 기본 실행 파일: `.runtime/python` (환경별 위치는 `.runtime/python-environments.json`)
- 음식 분석 Python 패키지: `Ai/Vision/Vision/.venv`, `.venv-aihub`
- Qwen 및 임베딩 가중치: `Ai/LLM/models`
- 현재 LoRA: `Ai/LLM/runs/parameter-dialogue-20261121/training/checkpoint-epoch-2`
- PostgreSQL 데이터: `.runtime/postgres-data`
- 이동 전 DB 백업: `.runtime/database-backups/before-localize.dump`
- Unity 연결 안내: `.runtime/local-server-connection.html`

실행 스크립트는 프로젝트 위치를 기준으로 경로를 계산합니다. `Server/scripts/project_runtime.ps1`은 Python 환경의 home 경로를 현재 프로젝트 위치에 맞춥니다. 패키지 명령은 이전 위치가 내장될 수 있는 pip.exe 대신 해당 환경의 `python.exe -m pip` 방식으로 실행하세요.

다른 PC에서도 Docker Desktop/WSL, 호환되는 NVIDIA 드라이버가 필요합니다. Unity 프로젝트를 편집하려면 해당 Unity Editor와 빌드 모듈도 설치해야 합니다. Docker 이미지와 컨테이너 자체는 Docker가 관리하며, 새 PC의 첫 빌드는 다운로드가 필요할 수 있습니다. 모든 기능의 완전한 오프라인 배포를 의미하지는 않습니다.

폴더를 백업하거나 옮길 때는 서버와 DB를 먼저 종료하고 숨김 폴더 `.runtime`, `.env`, 모델 가중치까지 포함해 전체 복사하세요. Git만 복제하면 제외된 모델/환경/DB가 함께 복사되지 않습니다. 과거 학습 로그에 기록된 절대 경로는 이력 보존을 위해 유지했습니다. 원본 AI Hub 데이터 전체가 포함된 재학습 배포본을 뜻하지 않습니다.

최종 확인: 내부 Python 실행 기반, DB bind mount, LLM 준비 상태, 음식 분석 서버 준비 상태, 공통 API 준비 상태 확인. 기존 Unity 세션과 펫을 사용한 대화 API 요청은 HTTP 200, 5.25초였습니다. Unity 화면 자체와 3D 생성 전체 흐름은 이번 확인 대상이 아닙니다. 결과는 `.runtime/relocation-verification.json`에 있습니다.
