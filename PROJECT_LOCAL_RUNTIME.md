# 프로젝트 내부 실행 구성

## 실행
- `Start-HealthMon.cmd`: 음식 AI → Qwen 대화 AI → 공통 서버, 완료 후 기존 연결 안내 페이지.
- `Start-VisionServer.ps1`: 음식 AI만 실행.
- `Run-FoodAI.ps1 -ImagePath <사진>`: 음식 분석 CLI.

## 내부에 포함된 파일
- `Ai/Vision/Vision`: 음식 모델, 영양 CSV, 추론 코드와 실제 Python 환경(외부 junction 없음).
- `.runtime/qwen4b-venv`: Qwen 패키지 환경.
- `.runtime/python`: 각 환경의 기본 Python 런타임.
- `.runtime/python-environments.json`: 환경과 기본 런타임 매핑.
- `.runtime/postgres-data`: 실행 중 사용하는 PostgreSQL 데이터.
- `.runtime/database-backups/before-localize.dump`: DB 이전 전 백업.
- `Ai/LLM/models`, `Ai/LLM/runs`: 대화 모델과 선택된 학습 체크포인트.

`Server/scripts/project_runtime.ps1`은 실행 시 현재 프로젝트 위치로 Python home을 갱신합니다. 실행에는 프로젝트 내부 `python.exe` 또는 위 런처를 사용하세요. pip 작업은 `python.exe -m pip` 방식으로 실행하세요.

## 이동·백업
숨김 폴더 `.runtime`, `.env`, 모델과 가상환경도 함께 복사해야 합니다. Git clone만으로 모델·환경·DB가 포함되지는 않습니다. DB 파일 복사 전 `Stop-HealthMon.cmd`로 DB를 종료하세요. 다른 PC의 Docker/Unity/NVIDIA 드라이버는 별도로 설치해야 하며 Windows x64 환경 기준입니다. 동시에 두 복사본을 같은 포트로 실행하지 마세요.

기존 외부 Vision 폴더, 상위 Qwen 환경과 Docker database 볼륨은 복구용으로 보존했습니다. 내부 복사본 실행에는 이 원본을 사용하지 않습니다. Unity/Android SDK, Docker Desktop/WSL, GPU 드라이버, Windows 시스템 글꼴은 설치형 실행 환경으로 남습니다. 이번 검증 범위는 음식 분석·대화 AI·공통 API·DB이며 3D 생성 모델의 신규 설치는 포함하지 않습니다.
