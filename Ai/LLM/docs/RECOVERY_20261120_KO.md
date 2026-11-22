# LLM 파일 복구 결과 (2026-11-20)

## 복원 완료

- `Start-HealthMon.cmd`, `Start-Qwen4B.ps1`: `recovery-previous` 백업에서 LLM 자동 실행 기능을 복원. 변경 전 파일은 외부 작업 폴더의 `recovery-20261120/llm-recovery/*.before`에 보존.
- 프로젝트 상위 `.runtime/qwen4b-venv`: Python 3.10.11로 재구성. `requirements.qwen4b.lock.txt`의 버전으로 설치했고 torch는 공식 cu128 저장소를 사용.
- `models/qwen3.5-4b`: 공식 저장소의 기존 고정 revision `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`로 재다운로드. 가중치 2개, 총 9,319,828,096바이트. 두 파일 모두 다운로드 메타데이터의 SHA-256과 일치하며 index의 모든 shard가 존재.
- 토크나이저와 모델 설정도 같은 revision에서 확보.

## 남아 있는 자료

- 학습 스크립트, 프롬프트, 서버 코드, 연결 설정.
- 학습 데이터: candidate 245건, common_v2 91건, natural 147건, healthmon_sft 350건, axis_priority 352건.
- BGE-M3 기억 검색 모델 파일.
- 과거 학습 로그와 성능 보고서. 기록이 남았다는 사실은 학습 가중치가 복원됐다는 의미가 아님.

## 현재 복구하지 못한 파일

- `runs/qwen4b-axis-priority-v1/checkpoint-epoch-2/adapter_model.safetensors`: 최종 파라미터 학습 결과. 기존 SHA-256 `a4353a9b4ec24e92f2c611a33e7678932a744c492cebb972f9577d707b82f753`.
- 해당 체크포인트의 `adapter_config.json`, `healthmon-model.json` 등 배포 메타데이터.
- `Ai/LLM/runs` 아래 이전 candidate/common/natural/healthmon_sft 학습 가중치와 체크포인트 부속 파일.

현재 작업 폴더, 프로젝트 복사본, recovery-previous, 바탕화면, 다운로드, 존재하는 OneDrive 경로, 사용자 모델 캐시, 접근 가능한 휴지통을 검색했으나 LoRA 파일을 찾지 못했다. 외장 디스크·다른 PC·클라우드 버전 기록·삭제 영역의 전문 복구까지 확인한 것은 아니므로 영구 소실을 단정하지 않는다.

학습 가중치는 소스 코드나 로그에서 원본 그대로 재생성할 수 없다. 백업이 없다면 보존된 데이터로 재학습해야 하며, 이는 원본 복원이 아니라 새 모델 생성이다. 누락된 가중치의 메타데이터만 만들어 정상 모델로 표시하지 않았다. 기본 모델만으로 서버를 대체하지 않았으며 기존 최종 어댑터 선택은 유지했다.

현재 상태에서 기존 학습 모델의 대화 서버 정상 작동을 보장할 수 없다. 런처는 LoRA 누락을 명확히 안내하고 중단한다. 재학습은 이번 파일 복구 작업에 포함하지 않았다.

검증 자료: 프로젝트 상위 `recovery-20261120/llm-recovery/verification.json`.
