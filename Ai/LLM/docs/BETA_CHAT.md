# 몽글이 모바일 대화 베타

`http://127.0.0.1:8000/`을 열면 같은 PC의 로컬 베타 세션으로 연결된다. 입력은 기존 Qwen3.5-9B 확장 LoRA로 전달된다. 캐릭터를 누를 때의 짧은 인사와 첫 화면 안내는 UI 자체 표현이고, 대화 말풍선은 실제 모델 응답이다.

## 구현한 화면

- 모바일 공원 배경, 민트 스카프를 두른 몽글이 SVG, 입력창·말풍선·생성 대기 표시.
- `speech`를 대사, `emotion`을 표정, `animation`을 허용된 모션으로 연결. 알 수 없는 값은 neutral/idle로 처리.
- ‘우리의 기억’에서 실제 검색·원본 정정·기억 재등록·삭제. 원본 변경 즉시 무효화된 이전 답변을 지우며 저장 중 다른 변경을 잠금.
- ‘작은 도전’에서 서버 제안 수락/거절과 진행 조회. 진행바는 모델 대사가 아닌 DB의 `progress`·`template.target` 사용. 확인된 운동 기록 연동 전에는 채팅만으로 완료·보상을 올리지 않음.
- 이름·반말/존댓말·가벼운 거친 표현 상한 설정. 한국어 IME 입력 지원, Shift+Enter 줄바꿈, 같은 request_id로 전송 재시도.

## Unity와 공유하는 구조

`web/api.js`는 통신, `web/app.js`는 브라우저 표시, `src/app.py`는 서버·DB·모델 실행을 담당한다. Unity는 같은 healthmon.v1 API에 연결하고 화면과 캐릭터 표현만 바꾼다.

```text
모바일 웹 표시 계층 ─┐
                   ├─ FastAPI ─ Memory / PostgreSQL ─ GPU Qwen
Unity 표시 계층 ────┘
```

[Unity 가이드](UNITY_BETA_INTEGRATION.md)와 `integrations/unity/`의 C# 클라이언트·DTO·캐릭터 bridge를 준비했다. 실제 Unity 프로젝트가 없어 Editor import·플랫폼 빌드·기기 실행은 미검증이다. 캐릭터 파일은 `web/assets/mongle.svg`의 2D 벡터이며 3D 모델/리깅 산출물이 아니다. Unity에서 사용할 이미지는 프로젝트의 2D/벡터 처리 방식으로 가져오고, CSS 모션은 Animator로 연결한다.

새 API는 `GET /pets`, `GET /pets/{pet}/messages?limit=50`이다. 기존 Bearer 계약을 유지한다. 브라우저는 `/beta/session`의 서명된 HttpOnly 쿠키를 쓰며 토큰·producer secret을 HTML/JS에 넣지 않는다.

## 저장과 현재 제한

브라우저 localStorage에는 현재 pet_id만 남긴다. 대화·기억·설정은 서버에서 조회한다. 정정된 사용자 원문은 최신 revision으로 보여주고, 무효화된 이전 답변은 복원하지 않는다. 기존 서버 무효화 범위가 넓어 기억 변경 후 해당 펫의 과거 답변 여러 개가 사라질 수 있다. fallback 턴은 원본 입력이 저장되지 않아 현재 화면에서는 보이지만 새로고침 후 history에서 복원되지 않는다.

네트워크 실패 시 pending ID·문장은 페이지 메모리에 남아 ‘다시 보내기’에 사용된다. 브라우저 새로고침을 넘는 pending 복구는 아직 없어 응답 대기 중 새로고침을 피한다. Unity에는 pending export/restore 인터페이스를 제공했다.

로컬 베타는 첫 DEV_TOKENS 계정을 공유한다. 브라우저별 pet_id가 달라도 운영 사용자별 로그인은 아니다. 브라우저 세션은 loopback·localhost Host·동일 Origin만 허용하며, 이번 작업으로 외부 휴대폰 접속을 열지 않았다. Unity의 Bearer 인증 경로는 유지한다.

기존 모델의 기억·숫자·반복·혼합 말투 오류는 남아 있다. UI 추가가 모델 품질 승인을 의미하지 않는다. [학습 비교 결과](IMPROVEMENT_RESULTS.md)를 참고한다.

## 실행

현재 서버가 켜져 있으면 주소만 열면 된다. 꺼져 있을 때 PowerShell에서:

```powershell
Set-Location E:\qwen-llm
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe scripts\setup_db.py
.\.venv\Scripts\python.exe scripts\serve.py --warmup
```

모델 경로는 `config/serving.json`을 사용한다. 명시한 `--adapter` 또는 `ADAPTER_PATH` 환경값이 있으면 그 값을 우선한다. 기본 모델만 실행할 때는 `--base`를 명시한다. `/health`의 `adapter`로 실제 선택 경로를 확인할 수 있다. 중단은 `scripts/stop_api.py`. 현재 로그는 `runs/api-mobile-beta-lora-20260929.stdout.log`와 `.stderr.log`다. 정적 화면 변경은 브라우저 새로고침, Python 변경은 API 재시작이 필요하다.

초기 UI 확인 3턴은 재시작 시 어댑터 옵션이 빠져 기본 Qwen으로 실행됐다. 이 문제를 발견해 기본 시작 명령이 설정 파일을 읽도록 수정하고 관련 테스트 2개를 통과했다. 이후 확장 LoRA를 로드한 것을 health에서 확인하고 실제 대화를 다시 수행했다. 두 단계 결과를 [검증 기록](BETA_VERIFICATION.json)에 구분한다.

대표 입력: `나는 달리기보다 걷는 게 좋아.`, `내 운동 취향 기억나?`, `오늘 가볍게 할 걷기 퀘스트 추천해 줘.`, `오늘은 쉬고 싶어.`. [검증 기록](BETA_VERIFICATION.json)을 함께 확인한다.
