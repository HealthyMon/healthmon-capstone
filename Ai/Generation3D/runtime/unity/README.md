# Unity 진화 API

이 폴더는 `ai/3d` 저장소의 실제 API·저장소·GPU 워커입니다. 모델 가중치·vendor·outputs를 별도 런타임 경로로 두고 실행기는 현재 체크아웃의 소스를 Docker에 바인드합니다.

- [실행과 TLS 설정](../../../../Docs/LOCAL_DEVELOPMENT.md)
- [Unity 연결·점수·API 계약](../../../../Docs/3D_UNITY_INTEGRATION.md)

```powershell
python Ai/Generation3D/scripts/launch_unity_bridge.py --runtime-root '<generation-runtime>' --gpu-lock '<repo>/Ai/LLM/runtime/gpu.lock'
```

현재 부모 이미지를 시각 설계에 사용하고 Qwen 새 이미지 → TRELLIS.2 → RigAnything을 순차 실행합니다. 기본 전달물은 원본 GLB입니다. `--delivery-quality mobile`은 별도 검수가 필요한 축소 사본이며 기본값이 아닙니다.

불변 버전은 `outputs/unity_service/pets/{pet}/versions/{revision}`에 저장하고 `current.json`만 원자적으로 갱신합니다. 실패하면 이전 모델을 유지합니다. 2차 큰 변화 판정·부모/정책/검사 해시는 3D와 게시 전에 확인합니다.

`test_jobs.py`, `test_species_contracts.py`, `test_second_stage.py`, `test_evolution_gate.py`는 실제 GPU를 사용하지 않는 회귀 검사입니다. 실제 생성과 시각·애니메이션 품질 검토는 별도입니다.
