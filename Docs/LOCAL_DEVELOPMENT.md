# 로컬 실행

## 준비

- Git LFS를 설치하고 `git lfs pull`로 기존 팀 Vision 가중치를 받습니다.
- 팀 Unity 버전은 `Client/HealthMonUnity/ProjectSettings/ProjectVersion.txt`를 따릅니다.
- Python·PostgreSQL·LLM 모델은 기존 `Ai/LLM` 실행 안내를 따릅니다.
- 이미지·3D 가중치와 Docker 환경은 `Ai/Generation3D/README.md` 및 그 안의 마이그레이션 도구로 복원합니다. Hugging Face 인증은 `hf auth login`으로 로컬에만 저장합니다.

아래는 런타임 데이터를 `E:/qwen-llm`에 둔 예입니다. 저장소 폴더 이름은 고정하지 않습니다. 런타임 `.env`와 가중치·출력·인증서는 Git에 넣지 않습니다.

## 실행

저장소 루트에서 PowerShell로 실행합니다.

```powershell
$runtime = 'E:/qwen-llm'
& "$runtime/.venv/Scripts/python.exe" Ai/LLM/scripts/launch_ecosystem.py --runtime-root $runtime
```

이 명령은 3D API와 기존 대화·음식 API의 준비 상태를 확인하고 팀 `MainARScene`을 엽니다. 계정 소유 펫 중 시작 3D 모델이 등록된 개체를 선택합니다. `--pet <pet_id>`로 명시할 수도 있습니다. Unity에서 Play를 누릅니다.

- 대화·음식 API: `http://127.0.0.1:8000`
- 진화 API: `https://127.0.0.1:8010`
- 3D 실행 데이터: `$runtime/healthmon-generation3d/Ai/Generation3D`

처음에는 검증된 시작 이미지와 리깅 GLB를 해당 펫 ID의 stage 0으로 등록해야 합니다. `runtime/unity/job_store.py`의 `Store.publish`가 종 계약·GLB 스킨·불변 버전을 검사합니다. 등록 전에 실제 재구성·리깅 보고서의 PASS와 파일 해시를 확인해야 합니다. 기존 `provision_starter.py`는 검증된 `lucan-starter` 폴더를 등록하는 로컬 예시이며 범용 설치 CLI가 아닙니다. 이미 등록된 펫은 그대로 사용하고, 모델 없이 가짜 완료 상태를 만들지 않습니다.

## 개발 인증서

```powershell
pwsh -File Ai/Generation3D/runtime/unity/setup_tls.ps1 -RuntimeRoot "$runtime/healthmon-generation3d/Ai/Generation3D"
```

개인 키와 로컬 설정은 런타임 `outputs/unity_service/tls`에 남습니다. 앱 실행기가 공개 인증서 DER의 SHA256을 계산해 `HEALTHMON_EVOLUTION_CERT_SHA256`으로 Unity 프로세스에 전달합니다. 공유 Resources 설정에는 특정 PC의 인증서 핀을 넣지 않습니다. Unity를 직접 열 경우 공개 핀과 개체 ID를 환경변수 또는 로컬 설정으로 제공해야 합니다. 핀이 없을 때는 플랫폼 인증서 검증을 사용하며 인증서 검증을 우회하지 않습니다.

`HEALTHMON_EVOLUTION_URL`, `HEALTHMON_EVOLUTION_PET`, `HEALTHMON_EVOLUTION_TOKEN`으로 주소·개체·인증을 설정합니다. 토큰은 씬·에셋·로그에 저장하지 않습니다.

## 검사

```powershell
& "$runtime/.venv/Scripts/python.exe" -m unittest discover -s Ai/Generation3D/runtime/unity -p 'test_*.py' -v
```

실제 추론은 별도 GPU 작업입니다. 성장 점수는 [연동 계약](3D_UNITY_INTEGRATION.md)을 따릅니다. 전체 성장 점수 생산자와 실기기 AR·모바일 성능 검증은 별도 작업입니다.
