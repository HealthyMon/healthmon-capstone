# Unity 다중 음식 분석 연결

## 서버

현재 AI는 Android 안에서 직접 실행하는 모델이 아니라 GPU PC에서 실행하는 HTTP 서비스입니다. APK는 사진을 전송하고 결과를 표시합니다.

이 문서가 있는 폴더에서 PowerShell 실행:

```powershell
.\Start-VisionServer.ps1
```

기본 포트는 8001이며 기존 8000 식사 기록 API와 별개입니다. 상태 확인은 `http://127.0.0.1:8001/health`. 서버는 한 번에 사진 하나를 처리합니다. 원본/크롭 파일은 요청 종료 후 삭제합니다. 전체 첫 분석은 모델 로딩 때문에 시간이 걸릴 수 있습니다.

## Unity

- 연결 씬: `Client/HealthMonUnity/Assets/HealthMon/Scenes/MainARScene.unity`
- 음식 탭의 `FoodScanPanel`에 `MultiFoodScanPanel`을 연결했습니다. 기존 FoodScanPrototype/FoodApiSender는 이 씬에서 비활성화하여 중복 요청을 방지합니다.
- Unity Editor 서버 주소: `http://127.0.0.1:8001`
- Android 서버 주소: `http://GPU_PC의_LAN_IP:8001`. 스마트폰과 PC가 같은 네트워크여야 합니다. 스마트폰에서 localhost는 PC가 아닙니다. 네트워크 정책/방화벽이 연결을 차단하는 경우 해당 사설 네트워크에서 TCP 8001을 허용해야 합니다.
- 화면에서 서버 주소를 입력하고 `주소 저장`을 누릅니다.
- `사진 촬영` 버튼: Android에서는 AR 카메라 CPU 이미지, Editor에서는 `Assets/HealthMon/Scripts/Food/food.jpg`를 사용합니다.
- `다시 분석`: 마지막 사진을 재전송합니다.

상단에 서버에서 반환한 bbox 이미지, 아래에 음식별 크롭·이름·중량·탄단지·열량을 표시합니다. CSV의 값은 100g 기준이고 화면의 섭취량 영양소는 중량에 비례 환산합니다.

- 음식 이름 변경: CSV 카탈로그에서 영어 이름으로 검색/선택합니다. 이름과 영양소 기준값을 함께 바꿉니다.
- 중량 변경: g 단위로 입력하고 버튼을 누르면 영양소를 다시 계산합니다.
- 제거: 음식 목록과 상단 박스를 함께 제거합니다.
- 수정 후 상단 사진: 원본 위에 현재 bbox·이름을 Unity가 다시 그립니다.
- 결과 저장: Application.persistentDataPath/food_analysis.json. 수정된 이름·중량·per100·nutrients(현재 중량 기준)·좌표가 포함됩니다. 수정 후 서버의 오래된 annotated_base64는 비우고 원본+수정 좌표를 저장합니다.

이 화면은 AI 분석 및 로컬 수정 결과 저장까지 수행합니다. 기존 반려 캐릭터/식사 기록 서버에 자동으로 식사를 등록하거나 퀘스트를 완료하지 않습니다.

## API

- POST /vision/analyze: multipart `image`, JPG/PNG, 최대 8MB/1600만 화소.
- GET /vision/catalog?q=rice: Food2K class_id, name, per100 등 최대 50개.
- 응답 schema_version=1. foods[].bbox는 EXIF 보정 사진 기준 정규화 xyxy(좌측 상단 원점).
- has_weight와 영양소 has_*로 결측과 0을 구분합니다. 중량 불확실성은 weight_status에 유지합니다.

LAN 시연을 위해 Android 인터넷 권한 및 HTTP 연결 설정을 활성화했습니다. 현재 서비스는 인증 없는 로컬 개발용이며 공용 서버 인증 흐름과 합쳐져 있지 않습니다.

## 검증 기록

- API 계약 테스트 3개 통과: 2,000종 카탈로그·결측값과 0 구분·이미지 요청 검사.
- 실제 food.jpg를 multipart로 API에 전달하여 새 폴더의 모델 전체 실행 완료. 음식 10개 모두 중량·영양소·크롭·상단 이미지 반환. outputs/unity_validation/response.json에 결과 보관.
- Unity 6000.4.6f1에 포함된 C# 컴파일러와 프로젝트 참조 어셈블리로 변경 스크립트의 Editor/Android 분기를 각각 컴파일 통과.
- MainARScene의 신규 컴포넌트 참조·중복 fileID 없음 확인.
- Unity Editor 배치 실행은 프로젝트를 연 직후 종료 코드 1로 끝나 실행 중 UI·Play Mode 검증은 완료하지 못했습니다. APK 빌드·휴대폰 카메라 촬영·실제 화면 배치/터치 동작은 별도 실기기 확인이 필요합니다.
- 자동 검증용 Editor 메뉴 메서드는 ValidateMultiFood.Run입니다. 이는 자동 실행용이며 앱 런타임에 포함되지 않습니다.

테스트 서버는 실행 상태로 남겨두지 않았습니다. 실제 사용 시 Start-VisionServer.ps1을 실행해 둔 상태에서 Unity에서 음식 탭을 여세요.
