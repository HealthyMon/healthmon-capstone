# 확장 실험 실행과 직접 대화

작업 경로는 `E:\qwen-llm`이다. 기존 `runs/pilot-20260929`는 보존한다. 216건 학습 데이터의 본 학습 폴더는 `runs/expanded-20260929`이다. 학습 중에는 API를 중단하여 GPU 모델을 하나만 올린다.

본 학습은 2 epochs, 54 optimizer updates 뒤 완료됐다. 43건 검증 loss와 체크포인트별 16건 대화로 epoch 1을 선택했다. 현재 API는 이 어댑터를 실험용으로 제공한다. 최종 비교에서 기억·퀘스트 회귀가 남았으므로 운영 승인이나 전체 품질 우수 판정은 아니다. 자세한 수치는 [결과 보고서](IMPROVEMENT_RESULTS.md)에 있다.

보존된 학습 로그 확인:

```powershell
Set-Location E:\qwen-llm
Get-Content runs\expanded-train.stdout.log -Tail 8
Get-Content runs\expanded-train.stderr.log -Tail 8
nvidia-smi
```

현재 학습은 BF16, batch=1, gradient accumulation=8, rank=8/alpha=32, max_length=1024다. 정답 토큰만 학습한다. 96건 선행 실험에서 epoch2 validation이 악화되어, 확장 본 실험은 기존 파일럿 어댑터에서 학습률 5e-5로 시작한다. 새 데이터의 순서는 epoch마다 재현 가능하게 섞는다. 기존 optimizer를 새 데이터에 복원하지 않는다.

재현은 반드시 새로운 run 이름과 로그 이름으로 한다:

```powershell
.\.venv\Scripts\python.exe scripts\stop_api.py
.\scripts\run_job.ps1 -Name expanded-repeat -Arguments '-u','scripts/train_lora.py','--run','expanded-repeat','--data','data/improvement_v3','--init-adapter','runs/pilot-20260929/checkpoint-epoch-3','--epochs','3','--lr','0.00005'
```

이 명령은 정리된 43건 검증을 사용한다. 실제 보존된 본 학습 로그는 v2의 44건 온라인 검증이며, 학습 파일은 동일하다. 과거 로그 조건 자체를 재현하려는 경우에만 `--data data/improvement_v2`를 사용한다.

안전하게 다음 epoch 저장 뒤 중단하려면 해당 run 폴더에 `stop.request` 파일을 만든다. 중단한 체크포인트를 동일 데이터로 재개할 때는 새 run 이름과 `--resume runs/<기존실험>/checkpoint-epoch-N`을 사용하고 `--init-adapter`는 빼야 한다. 데이터 해시가 다르면 resume을 거절한다. 전체 프로세스를 임의로 종료하거나 기존 체크포인트를 지우지 않는다.

서버가 실행된 상태에서 새 펫으로 대화:

```powershell
.\.venv\Scripts\python.exe scripts\chat_cli.py
.\.venv\Scripts\python.exe scripts\chat_cli.py --speech-level formal --profanity none --name 파도
```

다음 순서로 직접 확인할 수 있다. CLI는 기억 ID, 상태 버전, 실행 결과, fallback을 표시한다.

1. `나는 달리기보다 걷는 게 좋아.`
2. `내 운동 취향 기억나?`
3. `지금은 뭐가 좋다고 알고 있어?`
4. `/memories 내 운동 취향` → 실제 기억 ID 확인
5. `/correct <기억ID> 나는 걷기보다 수영이 좋아.`
6. `정정한 내 운동 취향 알려 줘.`
7. `내 운동 취향은 기억하지 마.`
8. `내가 좋아하는 운동 알고 있어?`
9. `보고서 쓰다가 굳은 어깨를 가볍게 움직이고 싶어.`
10. `제출할 보고서 완성본을 대신 작성해 줘.`
11. `오늘은 쉬고 싶으니 퀘스트 권하지 마.`를 두 번 입력
12. `/state`, `/quests`로 실제 DB 상태 확인

까칠함·장난·표현 수위의 강제 상태 검증은 자연 성장과 별개다. API를 끈 뒤 아래 명령을 각각 실행한다. 원문 시도와 최종 응답이 모두 출력되며 DB 성격은 바뀌지 않는다.

```powershell
.\.venv\Scripts\python.exe scripts\stop_api.py
.\.venv\Scripts\python.exe scripts\try_personality.py --style play
.\.venv\Scripts\python.exe scripts\try_personality.py --style blunt
.\.venv\Scripts\python.exe scripts\try_personality.py --style rough
.\.venv\Scripts\python.exe scripts\try_personality.py --style clean
.\.venv\Scripts\python.exe scripts\try_personality.py --style formal
```

서버가 꺼졌을 때만 다음을 실행한다. DB가 이미 실행 중이면 setup 스크립트는 해당 로컬 DB를 확인한다. 서버는 127.0.0.1에 바인딩한다.

```powershell
.\.venv\Scripts\python.exe scripts\setup_db.py
.\.venv\Scripts\python.exe scripts\serve.py --warmup --adapter runs/expanded-20260929/checkpoint-epoch-1
```

직접 파일럿과 비교하고 싶으면 먼저 서버를 중단하고 어댑터 경로만 바꾼다. 기존 어댑터는 그대로 남아 있다.

```powershell
.\.venv\Scripts\python.exe scripts\stop_api.py
.\.venv\Scripts\python.exe scripts\serve.py --warmup --adapter runs/pilot-20260929/checkpoint-epoch-3
```

대화 창과 별도 PowerShell에서 위 명령을 실행한다. 현재 확장 서버 로그는 `runs/api-expanded-20260929.stdout.log`, `runs/api-expanded-20260929.stderr.log`이다. 기존 로그 이름은 재사용하지 않는다. 독립 비교 원문은 `runs/improvement-20260929/final-comparison.json`에 있다. `scripts/evaluate_improvement.py --help`로 재현 옵션을 확인하되, 이미 공개된 58건 재실행은 회귀 시험이지 새 독립 시험이 아니다.

준비한 수량은 학습216/검증44/독립시험60이었고, 근접 표현을 보수적으로 회귀셋으로 이동한 최종 평가용 수량은 학습216/검증43/독립시험58이다(`data/improvement_v3`). 목표800/100/200와 다르다. 학습 파일은 v2와 v3가 동일하다. 본 학습 로그의 온라인 validation은 원래44건 기준이고, 최종 체크포인트 선택용 loss는 정리한43건으로 모두 다시 계산한다. 216 학습 예제는 177개 구체적 상황 그룹이며 무작위 자동 생성하지 않았다. 정답·시험 판정 모두 Codex 검토이고 사람 검수는 0건이다. 최종 시험은 한 번 평가한 뒤에는 해당 버전의 공개된 회귀 자료가 된다. 다음 개선의 독립 시험으로 재사용하지 않는다.
