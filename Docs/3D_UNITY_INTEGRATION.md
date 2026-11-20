# 3D 진화와 Unity 연결

공용 모드에서는 서버의 v2.2 상태와 진화 프로필을 사용합니다.
레벨 10·20·30에서 각각 1·2·3단계로 진행하며 초기종부터 한 단계씩 부모 모델을 계승합니다.

## 처리 순서

1. Unity가 `POST /pets/{pet}/evolutions`에 고유 `request_id`를 전달합니다.
2. 공용 서버가 상태·진화 프로필·부모 정보를 동결하고 작업을 저장합니다.
3. 3D Gateway가 인증한 작업을 저널에 기록합니다.
4. GPU worker가 부모 이미지·종 계약과 스탯을 반영해 이미지를 생성합니다.
5. TRELLIS.2로 재구성하고 RigAnything으로 리깅한 뒤 GLB와 해시를 게시합니다.
6. 공용 서버가 결과를 검증하고 최신 모델 참조를 갱신합니다.
7. Unity가 자산을 다운로드해 기존 AR 배치 루트의 시각 모델을 교체합니다.

같은 요청 ID는 같은 작업을 조회합니다. 서버·펫·단계와 부모 revision이 일치해야 다음 단계로 진행합니다.
모델을 교체할 때 배치 루트의 위치·회전·콜라이더를 유지합니다.

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
- `Server/healthmon/worker.py`: 작업 전달과 자산 등록
- `Ai/Generation3D/runtime/common_gateway`: GPU 계약과 저널
- `Ai/Generation3D/runtime/unity/evolution_worker.py`: 기존 생성 파이프라인

초기종은 `Server/assets/starter/lucan`의 게임 자산을 사용합니다.
첫 진화는 인증된 `parent_asset`의 PNG·종 계약·SHA를 전달해 부모를 자동 연결합니다.
최신 상태와 일치하는 revision만 화면에 반영하며 자산 크기 상한은 64 MiB입니다.
실행 설정은 [3D Gateway](../Ai/Generation3D/runtime/common_gateway/README.md)를 따릅니다.
