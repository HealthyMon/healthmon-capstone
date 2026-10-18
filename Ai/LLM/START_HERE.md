> 2026-10-04 Character Lab 추가: [http://127.0.0.1:8001/](http://127.0.0.1:8001/) · 7개 영역·12 presets·Analyzer/Responder 검수·분리 JSONL Export. [구현·규칙·실제 Qwen·최종 302개 테스트 보고서](E:/qwen-llm/docs/character-lab.md). 기본 dry-run이며 실제 사용자 DB에는 쓰지 않는다. 기존 LoRA를 재학습하지 않았다.
>
> 2026-10-01 생활 기록 입력·9개 dry-run preset·말투/퀘스트 전후 비교 추가: [생활 기록 실행·결과 보고서](E:/qwen-llm/docs/persona-lifestyle.md), [정확한 학습 상태](E:/qwen-llm/docs/persona-training-audit.md).

# 헬스몬 로컬 LLM 실행

**2026-10-01 Persona Lab 추가:** 새 4축 육성 규칙·30일 시뮬레이션·실제 epoch 1 LoRA A/B 비교는 별도 로컬 개발 화면 `http://127.0.0.1:8001/`에서 사용한다. [실행 방법](docs/persona-lab.md), [구현·실제 평가 보고서](docs/persona-system-audit.md), [원본 데이터 감사](docs/persona-data-audit.md)를 참고한다. 기존 7축 베타와 PostgreSQL은 자동 변환하지 않았다. 아래 “현재 서버 실행 중” 등의 문장은 9월 29일 당시 기록이다.

**모바일 대화 베타:** 서버 실행 중 [몽글이와 대화하기](http://127.0.0.1:8000/)를 연다. 캐릭터·채팅·기억·퀘스트 화면과 Unity용 C# 연결 코드를 추가했다. [베타 사용법](docs/BETA_CHAT.md), [Unity 연결](docs/UNITY_BETA_INTEGRATION.md)을 참고한다.

2026-09-29 확장 실험까지 완료했다. 현재 로컬 API는 `runs/expanded-20260929/checkpoint-epoch-1`을 실험용으로 제공한다. 학습216/검증43/새 시험58건이며 목표800/100/200에는 미달한다. 출력 형식·일부 말투는 개선됐지만 기억·퀘스트 회귀가 남아 운영 승인은 하지 않았다. [확장 결과 보고서](docs/IMPROVEMENT_RESULTS.md), [직접 대화·정정·성격 비교 명령](docs/EXPANDED_RUN_GUIDE.md), [현재 상태 JSON](IMPROVEMENT_STATUS.json)을 먼저 확인한다. 기존 파일럿 결과는 보존했다.

작업 위치는 `E:\qwen-llm`이다. 첨부 실행 프롬프트를 복원하고 Windows RTX 3090에서 Qwen3.5-9B BF16 LoRA 파일럿 학습을 실제 실행했다. 모델 원본, BGE-M3, PostgreSQL, pgvector, API와 테스트가 이 폴더 안에 있다. 과거 연구실 데이터/어댑터는 확보되지 않았다.

## 바로 실행

이번 작업에서 서버를 이미 시작했다. `http://127.0.0.1:8000/health`가 응답하면 서버를 중복 실행하지 말고 아래 `chat_cli.py`부터 실행한다. 서버가 종료되었을 때만 DB/serve 명령을 사용한다.

PowerShell에서:

```powershell
Set-Location E:\qwen-llm
.venv\Scripts\python.exe -u scripts\setup_db.py
.venv\Scripts\python.exe scripts\serve.py --warmup --adapter runs/expanded-20260929/checkpoint-epoch-1
```

다른 터미널에서:

```powershell
Set-Location E:\qwen-llm
$env:PYTHONUTF8='1'
.venv\Scripts\python.exe scripts\chat_cli.py
```

API 문서: http://127.0.0.1:8000/docs, 상태: http://127.0.0.1:8000/health. 현재 서버는 warmup을 마쳤다. warmup 없이 재실행하면 첫 답변은 모델 로딩 때문에 더 오래 걸린다. CLI에 표시되는 pet_id를 `--pet ID`로 다시 주면 같은 펫과 대화를 이어간다. `.env`의 로컬 A/B 사용자 토큰과 producer 토큰은 코드/로그/원격 저장소에 복사하지 않는다. 중단은 `.venv\Scripts\python.exe scripts\stop_api.py`로 이 프로젝트의 기록된 worker만 종료한다. 실행 중에는 GPU 메모리를 사용한다.

학습과 API 추론을 동시에 실행하면 VRAM이 부족하다. 아래 상태 명령으로 실험이 끝났는지 먼저 확인한다. 같은 포트에 서버를 중복 실행하지 않는다.

## 환경·데이터·학습

```powershell
# 새 설치에서만 실행. 현재 .venv는 이미 준비됨.
.\scripts\setup_environment.ps1
.venv\Scripts\python.exe scripts\download_assets.py qwen
.venv\Scripts\python.exe scripts\download_assets.py bge
.venv\Scripts\python.exe scripts\model_integrity.py
.venv\Scripts\python.exe scripts\validate_data.py

# 새 실험 폴더 이름 사용. 기존 실행 폴더는 덮어쓰지 않음.
.venv\Scripts\python.exe -u scripts\train_lora.py --smoke --run my-smoke
.venv\Scripts\python.exe -u scripts\train_lora.py --run my-pilot --epochs 3
```

현재 데이터는 `data/pilot_v2/train.jsonl` 34건, validation 8건이다. assistant 정답 토큰만 학습하며 최대 660토큰, truncation 0건이다. 본래 목표 800/100/200은 미완료다. 출처·검수·해시는 `data/pilot_v2/manifest.json`, 배경은 `docs/DATA_REVIEW.md`에 있다. v1은 토큰 수 메타데이터 오류가 있는 보존 초안으로 학습에 사용하지 않는다.

기본 설정은 BF16, r=8, alpha=32, batch=1, accumulation=8, lr=1e-4, checkpointing, max_length=1024이다. 이미지 인코더/원본 가중치는 동결한다. 4비트 양자화나 작은 모델로 바꾸지 않았다. Windows에서 재사용할 ms-swift 환경이 없어 Transformers+PEFT를 사용했다.

## 장기 실행·중단·재개

```powershell
.\scripts\run_job.ps1 -Name my-training -Arguments '-u','scripts/train_lora.py','--run','my-training','--epochs','3'
Get-Content runs\my-training.stdout.log -Tail 10
Get-Content runs\my-training.stderr.log -Tail 10
Get-Process -Id (Get-Content runs\my-training\pid)

# 현재 epoch 저장 후 정상 중단 요청
New-Item -ItemType File runs\my-training\stop.request

# 다른 출력 폴더에서 저장된 epoch 다음부터 재개 (예시)
.venv\Scripts\python.exe -u scripts\train_lora.py --run my-resumed --resume runs/my-training/checkpoint-epoch-1 --epochs 3
```

급히 종료해야 하면 학습 worker PID(`runs/my-training/pid`)가 이 작업의 Python인지 `Get-CimInstance Win32_Process -Filter "ProcessId=PID"`로 확인하고 해당 프로세스만 중단한다. `runs/my-training.pid`는 Windows 런처 PID일 수 있어 구분한다. API worker는 `runs/server-worker.pid`다. 강제 종료 시 마지막으로 저장된 epoch 이후 진행은 사라진다. 재개 기능은 구현되어 있지만 전체 epoch 중단·재개 동일성 비교는 아직 별도 검증 대상이다.

## 검증·연동

```powershell
.venv\Scripts\python.exe -m pytest tests -q
.venv\Scripts\python.exe scripts\restart_check.py
.venv\Scripts\python.exe scripts\evaluate_model.py --output runs/my-baseline.json
.venv\Scripts\python.exe scripts\evaluate_model.py --output runs/my-lora.json --adapter runs/pilot-20260929/checkpoint-epoch-3
.venv\Scripts\python.exe scripts\integration_real.py --adapter runs/pilot-20260929/checkpoint-epoch-3 --output runs/my-integration.json
.venv\Scripts\python.exe scripts\evaluate_flows.py --adapter runs/pilot-20260929/checkpoint-epoch-3
```

`tests/test_postgres.py`는 실제 PostgreSQL/BGE와 제어 가능한 가짜 생성기를 사용해 오류·동시성 등을 검사한다. `integration_real.py`, `evaluate_flows.py`는 실제 Qwen을 사용한다. 이 둘을 혼동하지 않는다. 다중 턴 20흐름×10턴은 개발 시험으로, 세션 간격은 테스트 시계로 재현하며 동결 test200이 아니다.

API 요청/응답과 Unity 임시 계약은 `docs/openapi.json`, `docs/response.schema.json`, `docs/API_EXAMPLES.md`에 있다. 사용자 소유권은 인증 토큰으로 결정하며 user_id를 본문에서 받지 않는다. 확인된 활동 입력은 producer 토큰이 추가로 필요하다.

```powershell
# 실제 웨어러블 대신 쓰는 합성 테스트 입력기
.venv\Scripts\python.exe scripts\mock_activity.py --pet YOUR_PET_ID --steps 500
```

## DB와 복구

DB 데이터: `runtime/pgdata`, PostgreSQL 로그: `runs/postgres.log`. API를 재시작해도 데이터는 유지된다. DB는 `127.0.0.1:55432`에 바인딩한다. DB 중단: `runtime\pgsql\bin\pg_ctl.exe -D runtime\pgdata -m fast -w stop`. 재시작: `scripts/setup_db.py`.

DB 최초 설치를 다시 해야 한다면 `download_assets.py postgres` → `scripts/build_pgvector.cmd` → `scripts/setup_db.py` 순서다. 빌드 스크립트는 현재 PC의 Visual Studio 경로를 사용한다. 기존 pgdata가 있으면 다시 초기화하지 않는다. `migrations/001_initial.sql`과 `002_suggestion_jobs.sql`은 순서대로 적용된다.

Docker 경로는 `compose.yaml`에 제공하지만 이 PC에선 Docker daemon/WSL이 없어 미실행이다. 네이티브 DB와 같은 포트를 쓰므로 둘 중 하나만 실행한다. 팀 운영 DB를 자동 마이그레이션하지 않는다.

문제 발생 시: VRAM 부족이면 다른 GPU 작업을 종료한 뒤 단일 작업으로 재시도한다. 원본 모델 크기와 dtype을 몰래 변경하지 않는다. 형식 보정은 1회이며 실패 응답은 상태를 변경하지 않는다. 상태 충돌 409는 최신 상태로 재시도하고, 삭제로 무효화된 과거 request_id는 410이므로 새 요청을 사용한다. 모델/의존성/실행 기록과 남은 제한은 `docs/RESULTS.md`에서 확인한다.
