# 응답 시간 개선 기록 — 2026-11-10

동일한 6개 입력을 사용한 최종 비교에서 요청당 처리 시간 중앙값이 9.491초에서 3.712초로 감소했다(약 60.9% 감소, 2.56배 처리 속도). 두 설정 모두 6건 전부 한 번의 생성으로 공통 서버 응답 계약을 통과했다. 이 수치는 오프라인 모델 호출 비교이며 Unity 전체 응답 시간과 동일하지 않다.

적용 후 실제 Unity용 공통 API 경로(`/pets/{pet}/chat`)로 보낸 새 요청은 HTTP 200, `provenance=real`, 전체 9.062초였다. 응답은 “좋아! 천천히 즐기면 좋겠다. 응원하고 있어.”였다. 네트워크·DB·실제 대화 맥락이 포함되므로 오프라인 수치보다 길 수 있다.

현재 추론 방식:

- 학습에 사용한 NF4 기본 가중치를 로딩한 뒤 BF16으로 복원한다. 원본 파일을 바꾸거나 다시 학습하지 않는다.
- 텍스트 전용 대화 프로세스에서 사용하지 않는 이미지 인코더만 메모리에서 제외한다. 별도 음식/영상 서비스는 변경하지 않는다.
- 확인된 LoRA를 복원된 가중치에 메모리상 병합하고 BF16으로 고정한다. 원본 모델과 LoRA 파일은 보존한다.
- FLA 선형 어텐션 커널을 사용하고, 서버 준비 전에 짧은 생성으로 커널을 준비한다.
- CPU 스레드 1개, 요청마다 GPU 할당 캐시를 비우지 않는다. 대화 간 KV 상태를 공유하지 않으며 각 요청은 새 생성 캐시로 시작한다.
- 입력 성격/최근 대화/기억과 기존 출력 계약, 최대 생성 토큰 440은 유지한다.

버전: torch 2.11.0+cu128, triton-windows 3.6.0.post26, fla-core 0.4.2, flash-linear-attention 0.4.2, einops 0.8.2. 전체 환경은 `requirements.qwen4b.lock.txt`에 기록되어 있다.

최종 근거: `.runtime/qwen4b-latency-v5/summary.json`, `baseline.json`, `optimized.json`, `live-api.json`. 앞선 v1~v4 비교는 미채택 시도이며 최종 개선 수치로 사용하지 않는다. 4비트 상태에서 직접 LoRA를 병합하는 설정은 답변 변동·재시도 문제 때문에 금지했다.

한계: GPU 메모리를 기존 NF4 추론보다 많이 사용한다. 다른 GPU 프로그램과 동시에 실행하면 속도가 달라질 수 있다. 일부 문법/표현 문제가 남았으며 이 최적화는 별도의 언어 품질 개선을 대체하지 않는다. 커널 캐시가 없는 첫 실행은 준비 시간이 더 길 수 있다.

참고: [PEFT LoRA 병합](https://huggingface.co/docs/peft/en/package_reference/lora), [Triton Windows 호환 버전](https://github.com/triton-lang/triton-windows), [FLA 구현](https://github.com/fla-org/flash-linear-attention).
