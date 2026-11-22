# 음식 인식 AI — 실행 및 재학습 안내

> 최신 다중 음식 구현과 실행법은 [aihub/README.md](aihub/README.md)를 참조하세요. 아래 FPB 설명은 초기 실험 기록입니다. 현재는 기존 AI Hub 800종 모델을 유지하면서 별도로 학습한 음식 위치 모델을 앞단에 연결합니다.

사진 → 여러 음식의 위치·종류·추정 중량 → JSON / 박스 이미지 / 음식별 크롭을 구현했습니다.
이 폴더는 독립 Python 프로젝트이며 기존 HealthMon 파일은 수정하지 않았습니다.
APK와 Unity 화면 구현은 포함하지 않습니다. 접시라는 물체를 따로 검출하는 모델이 아니라 **음식 영역을 검출**합니다. 같은 접시 위의 서로 다른 음식도 별도 박스로 출력될 수 있습니다.

## 현재 확보한 것

- 공식 학습 완료 모델: `assets/Model Weights/YOLOv12S.pt` (21,647,135 bytes)
- 실물 공개 데이터: 학습 24장 + 검증 24장과 대응 라벨. 전체 학습/검증 데이터 다운로드 명령도 제공.
- 실제 RTX 4070 Ti에서 이미지 추론, 1 epoch 재학습 및 체크포인트 저장 검증.
- 재학습 검증용 모델: `runs/smoke/weights/best.pt`. **소량 학습 실행 확인용**이며 완성 모델로 권장하지 않습니다.
- 결과 계약 및 중량 평가 매칭 테스트 4개 통과.

`.pt`와 `.pth`는 모두 PyTorch에서 흔히 쓰는 확장자입니다. 이 모델은 공식 로더가 `.pt`를 기대하므로 이름을 바꾸지 마세요. 확장자보다 모델 구조·라벨 순서·전처리·가중치가 함께 맞아야 합니다. 일반 `pip install ultralytics`로 교체하면 중량 헤드가 없어 호환되지 않습니다. 아래 공식 포크를 사용해야 합니다.

## 데이터와 모델 선택 근거

[FPB 공식 데이터](https://huggingface.co/datasets/issai/Food_Portion_Benchmark)는 총 14,083장, 138종 음식의 박스 및 중량 주석을 제공하는 데이터셋입니다. 학습 9,521장 / 검증 2,365장 / 테스트 2,197장으로 안내되며 테스트 정답은 비공개입니다. 일부 공개 라벨은 중량이 `-1`인 결측입니다. 이를 임의 중량으로 채우지 않고 원본 포크의 결측 처리로 학습합니다.

[공식 소스](https://github.com/IS2AI/Multitask-Food-Portion-Estimation)는 YOLOv12에 중량 회귀 헤드를 추가한 모델입니다. `vendor`에 커밋 `307a903d49ab073ed83f01c527981aafe5da59b3`를 보관했고 공식 LICENSE도 그대로 포함했습니다. Windows에서는 FlashAttention 대신 PyTorch attention 경로로 실행됩니다.

중요한 한계: FPB는 중앙아시아 음식 중심입니다. **돈가스·된장국·피클·양배추샐러드·와사비를 정확하게 식별하는 한식 완성 모델이 아닙니다.** 첨부 스크린샷의 실제 추론에서 돈가스를 `lulya_kebab`으로 오인했습니다. `outputs/user_image`에 수정하지 않은 결과가 있습니다. UI의 음식 이름을 정답으로 추론 결과에 덮어쓰지 않았습니다. 카드 속 음식 사진도 중복으로 인식되므로 앱에서는 카메라 원본만 전달해야 합니다.

학습 데이터는 CC-BY-NC-4.0, 공식 코드 포크는 AGPL-3.0으로 표기되어 있습니다. 출처와 라이선스를 유지하고 상업 배포 가능 여부는 각 배포물 조건을 별도로 확인하세요. FPB 전체 학습을 해도 없는 한식 클래스가 자동으로 추가되지는 않습니다.

## 지금 이 PC에서 바로 추론

PowerShell:

```powershell
cd C:\Users\user\Desktop\capstone\Vision
.venv\Scripts\python.exe food_ai.py "C:\Users\user\Downloads\image.png" --device 0 --output outputs\my_photo
```

`--device cpu`도 지원합니다. `--confidence 0.35`로 탐지 임계값을 조절합니다. 낮추면 탐지 수와 오탐이 함께 늘 수 있습니다.

출력 폴더:

- `result.json`: 음식명, class_id, 신뢰도, 박스, 추정 중량, 크롭 경로
- `annotated.jpg`: 박스가 표시된 사진
- `food_000.jpg` 등: 음식별 크롭 이미지

EXIF 방향을 적용한 사진 기준으로 `bbox_xyxy=[왼쪽, 위쪽, 오른쪽, 아래쪽]`를 반환합니다. 정규화 좌표도 제공합니다. Unity 화면에 나중에 표시할 때는 원본 비율과 여백을 고려해 좌표를 변환해야 합니다.

`weight_status=estimated`는 측정값이 아니라는 뜻입니다. `weight_g=null`은 유효한 양수 중량이 나오지 않은 경우입니다. 신뢰도는 음식 탐지 점수이며 **중량 정확도 점수가 아닙니다**. `needs_weight_confirmation=true`로 사용자 수정이 필요함을 표시합니다. 영양소는 이번 AI 출력에 넣지 않았습니다. 이후 검증된 음식별 100g 성분표 × 확인된 중량 / 100으로 계산하세요.

## 환경을 다시 만들 때

Python은 uv로 3.11을 설치합니다. 이 PC에는 전용 `.venv`가 이미 준비되어 있습니다. 새 PC에서는 uv 설치 후:

```powershell
cd C:\Users\user\Desktop\capstone\Vision
.\setup.ps1
.venv\Scripts\python.exe download.py
```

설치 스크립트는 CUDA 12.4 PyTorch 2.6.0과 torchvision 0.21.0을 설치합니다. 의존성은 `requirements.lock.txt`, 소스 버전은 `upstream_commit.txt`, 데이터 버전은 `dataset_revision.txt`, 모델 SHA256은 `assets/provenance.json`에 기록됩니다. 데이터 다운로드는 고정 revision을 재사용합니다.

## 직접 학습하기

소량 실행 검증:

```powershell
.venv\Scripts\python.exe download.py --limit 24
.venv\Scripts\python.exe validate_data.py data_sample.yaml
.venv\Scripts\python.exe train.py --data data_sample.yaml --epochs 1 --batch 2 --imgsz 320 --name smoke_new
```

전체 학습/검증 자료 확보 후 실제 미세조정:

```powershell
.venv\Scripts\python.exe download.py --full
.venv\Scripts\python.exe train.py --data data_full.yaml --epochs 50 --batch 4 --imgsz 640 --name food_finetune
.venv\Scripts\python.exe evaluate.py --data data_full.yaml --model runs\food_finetune\weights\best.pt
.venv\Scripts\python.exe food_ai.py "C:\path\meal.jpg" --model runs\food_finetune\weights\best.pt --device 0
```

다운로드에는 디스크 공간·시간이 필요합니다. `--full`은 공개 train/val을 받으며 테스트 정답을 만들지 않습니다. 소량/전체 이미지 목록을 별도 manifest로 저장해 같은 폴더에 있어도 선택이 섞이지 않습니다. 학습 폴더 이름이 이미 있으면 upstream이 번호를 붙이므로 실제 로그의 저장 경로를 확인하세요. VRAM 부족 시 batch를 2로 줄이세요.

학습 시 원본 포크의 중량 라벨을 그대로 유지합니다. 음식 일부를 자르는 증강에서 중량 정답이 틀어지는 위험을 줄이기 위해 mosaic, mixup, 공간 크롭/변형 계열을 껐습니다. 색상 증강과 좌우 반전은 유지했습니다. 검증은 detection mAP와 같은 클래스·IoU≥0.5로 일대일 매칭된 물체의 중량 MAE를 함께 저장합니다. 검출 실패를 제외한 MAE만으로 전체 성능을 판단하면 안 됩니다.

## 사진 속 한식으로 확장하는 방법

1. 먼저 필요한 종류를 정합니다. 예: 돈가스, 된장국, 쌀밥, 양배추샐러드, 피클, 와사비. 기존 FPB 이름을 한식 이름으로 바꾸기만 하면 잘못된 학습이 됩니다.
2. 음식별 박스 라벨이 있는 사진을 확보합니다. 한 장에 음식 하나만 있는 **분류 데이터**만으로는 여러 음식 위치 학습을 할 수 없습니다. 공개 데이터에서도 실제 주석 종류를 확인해야 합니다.
3. 한국 음식 공개 데이터 후보로 AI Hub의 음식 이미지/영양정보 자료를 검토할 수 있습니다. 계정·이용 조건을 확인하고 실제 파일을 확보한 뒤 해당 JSON 구조에 맞춰 변환해야 하며 이 작업에서는 해당 자료와 가중치를 확보했다고 주장하지 않습니다. 기존 프로젝트의 `food_detector.pth`는 LFS 포인터여서 실행할 수 없는 상태였습니다.
4. 중량 학습은 각 박스 음식의 **저울 실측 g**가 필요합니다. 1인분 기준 중량이나 영양정보 기준 100g을 실제 사진 중량으로 사용하면 안 됩니다. 중량이 없으면 `-1`로 두고 탐지만 학습할 수 있으나, 해당 음식 중량 정확도는 별도 실측 데이터가 필요합니다.
5. 동일 접시를 연속 촬영한 사진, 다른 각도, 같은 식사 회차는 같은 split에 둡니다. 다른 촬영일·장소의 식사를 검증/테스트로 남깁니다. 기본 검증기는 완전히 동일한 파일의 train/val 중복은 차단하지만 같은 식사를 다른 각도로 찍은 것까지 식별하지는 못합니다.
6. 아래 형식으로 변환하여 `train.py --data custom/data.yaml`을 실행합니다. 클래스 수가 달라지면 탐지 헤드가 재구성되어 추가 학습이 필요합니다. 기존 가중치를 로드했다고 바로 새 클래스가 인식되는 것은 아닙니다.

```text
custom/
  data.yaml
  train/images/meal_001.jpg
  train/labels/meal_001.txt
  val/images/meal_002.jpg
  val/labels/meal_002.txt
```

라벨 한 줄은 `class_id center_x center_y width height grams`입니다. 박스 좌표는 0~1 정규화, 클래스 ID는 0부터, 음식이 여럿이면 줄을 추가합니다. 예: `0 0.50 0.50 0.30 0.25 180`. 중량 결측: `0 0.50 0.50 0.30 0.25 -1`.

```yaml
path: C:/Users/user/Desktop/capstone/Vision/custom
train: train/images
val: val/images
names: [돈가스, 된장국, 쌀밥, 양배추샐러드, 피클, 와사비]
```

`evaluate.py`의 추가 중량 평가 루프는 다운로드 도구가 만드는 **val 이미지 목록 txt**를 입력으로 받습니다. 자체 데이터에도 절대 이미지 경로를 한 줄씩 쓴 목록을 만들어 YAML의 val로 지정하면 됩니다. 폴더 경로만 있는 YAML은 학습 검증의 기본 mAP까지만 지원합니다.

## 검증 기록 (2026-11-06)

- PyTorch 2.6.0+cu124 / Python 3.11.15 / RTX 4070 Ti 12GB.
- 공식 S 모델, 샘플 검증 24장·60개 음식: mAP50 0.8936, mAP50–95 0.8095.
- confidence 0.35에서 같은 클래스 IoU≥0.5 매칭 50/60개. 유효한 실측 중량이 있는 46개 매칭에서 MAE 약 104.85g.
- 이 수치는 작은 선정 샘플에서의 실행 점검 결과입니다. 전체 데이터 벤치마크나 한식 정확도가 아닙니다. 1 epoch smoke 모델은 공식 모델보다 좋아졌다고 주장하지 않습니다.
- 원본 모델과 새 `best.pt` 모두 다시 로드하여 추론 확인. 4개 계약 테스트 통과.

원본 결과: `outputs/sample_evaluation.json`, `outputs/user_image/result.json`, `outputs/fpb_example`, `outputs/retrained_example`.

단일 RGB 사진으로 절대 중량을 보장할 수 없습니다. 실제 서비스 수준의 중량을 목표로 하면 음식별 실측 학습자료를 늘리고, 같은 촬영 조건·기준 크기 또는 깊이 정보를 활용하는 후속 설계가 필요합니다. APK 안에서 오프라인 실행하려면 이 Python/커스텀 PyTorch 모델을 별도로 변환하고 모바일 런타임을 검증해야 합니다. 현재 완료 범위는 PC/GPU에서 실행·학습 가능한 AI입니다.
