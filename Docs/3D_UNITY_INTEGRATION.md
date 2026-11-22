# 3D 진화와 Unity 연결

공용 모드에서는 서버의 v2.2 상태와 진화 프로필을 사용합니다.
레벨 10·20·30에서 각각 1·2·3단계로 진행하며 초기종부터 한 단계씩 부모 모델을 계승합니다.

## 처리 순서

1. 홈의 **진화하기** 버튼이 기존 진화 연출 화면을 열고, Unity가 `POST /pets/{pet}/evolutions`에 고유 `request_id`를 전달합니다.
2. 공용 서버가 상태·진화 프로필·부모 정보를 동결하고 작업을 저장합니다.
3. 3D Gateway가 인증한 작업을 저널에 기록합니다.
4. GPU worker가 부모 이미지·종 계약과 스탯을 반영해 이미지를 생성합니다.
5. TRELLIS.2로 재구성하고 RigAnything으로 리깅한 뒤 GLB와 해시를 게시합니다.
6. 공용 서버가 결과를 검증하고 최신 모델 참조를 갱신합니다.
7. Unity가 해시를 확인한 자산을 다운로드해 홈·진화 미리보기·AR의 시각 모델을 교체합니다.
8. 홈과 결과 미리보기에 같은 revision이 실제 적용된 뒤 **진화 성공** 화면을 표시합니다. 확인 버튼으로 홈에 돌아갑니다.

같은 요청 ID는 같은 작업을 조회합니다. 서버·펫·단계와 부모 revision이 일치해야 다음 단계로 진행합니다.
모델을 교체할 때 배치 루트의 위치·회전·콜라이더를 유지합니다.
일시적인 연결 오류·503 응답은 동일 요청 ID로 자동 재확인합니다. 서버의 실패 상태는 성공으로 표시하지 않습니다.
다운로드·적용 실패 시 기존 모델을 보존하고, 홈의 **진화 외형 다시 받기**로 생성 요청 없이 다시 불러옵니다.
앱을 재실행하면 저장된 진화 요청을 재개합니다. 홈과 진화 화면의 초기 슬라임은 유지하고 생성된 1단계 이상부터 교체합니다.

## 스탯과 외형

서버가 사용하는 축은 `upper_body`, `lower_body`, `nutrition`, `energy_balance`,
`activity`, `affinity`, `initiative`입니다.
EnergyBalance는 공용 계약의 -100~100 값을 3D 경계에서 정규화합니다.
체형 프로필은 근력·상하체 균형·영양·에너지 상태를 함께 계산하며 11개 appearance를 지원합니다.
초기종의 종 계약과 이미지 특징을 부모 정보로 계승합니다.
기존 Lucan 경로의 1·2단계는 사족, 3단계는 직립 이족 설계를 사용합니다.

## API와 소스

| API | 용도 |
| --- | --- |
| `POST /pets/{pet}/evolutions` | 진화 요청 |
| `GET /pets/{pet}/evolutions/{job_id}` | 작업 상태 |
| `GET /pets/{pet}/assets/{job_id}` | 인증된 모델 다운로드 |
| `GET /pets/{pet}/state` | 현재 stage와 모델 참조 |

- `Scripts/API/CommonServerConnection.cs`: 공용 연결과 상태
- `Scripts/API/EvolutionClient.cs`: 요청·재개·다운로드
- `Scripts/AR/ArEvolutionModel.cs`: glTFast 모델 로딩
- `Scripts/UI/EvolutionFlowController.cs`: 실제 요청·홈 모델·진화 연출의 상태 연결
- `Server/healthmon/worker.py`: 작업 전달과 자산 등록
- `Ai/Generation3D/runtime/common_gateway`: GPU 계약과 저널
- `Ai/Generation3D/runtime/unity/evolution_worker.py`: 기존 생성 파이프라인

초기종은 `Server/assets/starter/slime`의 실제 게임 슬라임 자산을 사용합니다.
Unity의 `pet_starter` 프리팹에서 `HealthMonStarterExport.Run`으로 내보낸 GLB·정면 PNG와
`Ai/Generation3D/configs/species/slime.json`의 종 계약이 함께 등록됩니다.
2511 진화는 슬라임 부모 계약을 요구하며, 이전 늑대 부모를 받으면 GPU 생성 전에 거부합니다.
첫 진화는 인증된 `parent_asset`의 PNG·종 계약·SHA를 전달해 부모를 자동 연결합니다.
최신 상태와 일치하는 revision만 화면에 반영하며 자산 크기 상한은 64 MiB입니다.
실행 설정은 [3D Gateway](../Ai/Generation3D/runtime/common_gateway/README.md)를 따릅니다.

실제 진화 검증은 서버 작업 성공만으로 통과하지 않습니다. 진화 전 모델과 다른 SHA의 결과가
홈과 진화 미리보기 양쪽에 적용된 다음에만 완료 화면이 나와야 합니다. 완료 화면을 닫은 뒤의
홈, 앱을 완전히 재실행한 뒤의 홈에서도 동일한 서버 revision·SHA가 유지되는지 확인합니다.
720×1280, 720×1440, 720×1600에서 정면·외형·잘림·겹침을 캡처로 검사합니다.
`StartEvolution`/`CompleteEvolution`을 직접 호출하는 화면 상태 검사는 실제 추론·진화 완료의 근거가 아닙니다.


## 2026-11-22 verification status

The first slime evolution was exercised through the real Unity action, the 2511
LoRA inference pipeline, asset publication, and replacement of the home and
result-preview models. The same published SHA was verified after a complete
Unity process restart and in the AR preview and adventure battle. The test pet
used prepared level/stat values; model generation and application were real.

- Unity: 100 checks across 720x1280, 720x1440, and 720x1600; 79 screenshots; no runtime errors or detected control/label clipping.
- Linux backend with isolated PostgreSQL: 515 passed, 12 Windows-specific cases skipped.
- Windows launcher menu: 19 passed; PowerShell lifecycle checks passed.
- Evolution contracts and portable installation tests: 42 passed.
- CPU food/pose remained usable during evolution; GPU dialogue resumed afterward.

Remaining validation: physical Android camera/AR and mobile performance; complete
second/third-stage generation; a first network download and installation on a
separate teammate PC. The generated first-stage GLB is about 53.6 MiB with
995,154 triangles and no animation clips, so surface quality and mobile asset
optimization remain open. Portable-install checks used an isolated checkout,
database, and credentials but reused already downloaded model caches.

`configs/evolution_2511/upload_manifest.json` preserves the original uploaded
artifact's provenance; its upload-time deployment status is historical. The
verification status above describes the integrated runtime. Raw captures and
logs stay under the local ignored `.runtime/acceptance-20261122` directory.
