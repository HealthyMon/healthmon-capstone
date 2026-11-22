# 여러 음식 인식 AI

DishSeg24K 개체별 박스로 위치 모델을 추가 학습하는 최신 작업은 [DISHSEG.md](DISHSEG.md)를 참조하세요. `Run-FoodAI.ps1`은 마지막 평가에서 선택한 `active_region.json`의 가중치를 사용합니다.

학습 완료 및 마지막 통합 검증 결과는 [RESULTS.md](RESULTS.md)에 있습니다. 다중 음식 평가 72장에서 위치 재현율 72.4%, 정밀도 87.5%를 기록했습니다. 음식명 정확도 수치가 아니며 첨부 UI 스크린샷의 음식명은 모두 미확인으로 남았습니다.

## 현재 구조

`사진 → 새 음식 위치 모델 → 음식별 크롭 → 기존 AI Hub 800종 인식 모델 → 이름·박스·크롭·JSON`

71564 단일 음식 데이터로 학습된 모델을 다시 같은 자료로 학습하지 않습니다. 여러 음식의 위치를 담당하는 모델을 별도로 학습하고 기존 분류 가중치는 그대로 유지합니다. 새 위치 모델은 torchvision Faster R-CNN/MobileNetV3-320의 COCO 가중치에서 시작합니다. 찾은 위치에 이름을 붙이지 못하면 `미확인 음식`으로 반환하며 박스는 남깁니다.

박스는 음식 영역입니다. 접시 자체의 개수나 재질을 인식하는 모델이 아니며 한 접시에 여러 음식 영역이 나올 수 있습니다. 기존 800종에 없는 음식명을 새로 배운 것은 아닙니다. 이름 모델은 학습하지 않은 음식도 기존 음식으로 잘못 판단할 수 있습니다.

## 실행

PowerShell:

```powershell
cd C:\Users\user\Desktop\capstone\Vision
.\Run-FoodAI.ps1 -ImagePath "C:\Users\user\Downloads\image.png"
```

직접 실행:

```powershell
.venv-aihub\Scripts\python.exe aihub\detect.py "C:\path\meal.jpg" --regions runs\food_regions_pilot\food_regions.pth --output outputs\my_meal
```

`--device cpu`도 가능합니다. 기존 모델만 실행하려면 `--regions`를 생략합니다. `--region-threshold` 기본값은 0.5, `--name-threshold` 기본값은 0.5입니다. 이름 점수와 위치 점수는 서로 다른 의미입니다.

출력 폴더의 `annotated.jpg`는 한글 이름과 박스, `food_000.jpg` 등은 음식 크롭, `result.json`은 전체 결과입니다. `input_upright.jpg`는 EXIF 방향 보정 입력입니다. `bbox_xyxy`는 방향 보정 입력의 픽셀 `[왼쪽,위,오른쪽,아래]`이고 `bbox_normalized_xyxy`는 0~1 좌표입니다. Unity에서는 사진 표시 영역의 비율과 여백을 반영하세요.

UI 스크린샷에는 카드 속 음식 사진도 있으므로 중복으로 인식될 수 있습니다. 실제 앱에서는 카메라 원본을 넘겨야 합니다. 현재 구현은 PC/GPU Python AI이며 APK 내 오프라인 추론 변환은 포함하지 않습니다.

## 학습 자료와 한계

[공식 UECFoodPixComplete](https://mm.cs.uec.ac.jp/uecfoodpix/)의 수작업 semantic mask에서 음식 클래스별 연결 영역의 박스를 만들었습니다. 작은 잡음을 제거하고 5×5 closing을 적용합니다. 이것은 수작업 instance box가 아닌 **약한 박스 정답**입니다. 같은 종류가 붙어 있으면 합쳐지고 떨어진 음식 조각은 여러 개로 나뉠 수 있습니다. 이 한계를 감안해 실제 다중 접시 촬영 자료로 보완해야 합니다.

이번 학습: 공식 train에서 600장(다중 영역 450장, 총 1,603영역). 최종 평가: 공식 test에서 96장(다중 영역 72장, 총 256영역). 고정 seed 42로 선정하고 정확히 같은 원본 파일의 해시 중복을 제거했습니다. `assets/uec_regions_pilot/provenance.json`에 기록돼 있습니다. UEC 음식명을 기존 800종에 억지로 대응시키지 않고 새 모델은 음식/배경만 학습합니다.

원본 archive는 `assets/UECFOODPIXCOMPLETE.tar`입니다. 데이터는 비상업 연구용 조건이므로 상업 배포에는 별도 확인이 필요합니다.

## 가중치

- `01.음식 탐지 및 분류 모델/학습모델파일.pth`: 기존 AI Hub 800종 모델, 수정하지 않음
- `02.중량 예측 모델/food_weight_checkpoint.pth`: 기존 중량 모델, 수정하지 않음
- `runs/food_regions_pilot/food_regions.pth`: 새 음식 위치 모델
- `runs/food_regions_pilot/training.json`: epoch별 학습 손실

새 가중치는 600장으로 3 epoch 학습한 초기 모델입니다. 실행 가능한 학습 산출물이지 모든 한식/촬영 조건에 대해 검증된 완성품은 아닙니다. 별도 위치 모델을 추가하는 방식이며 기존 800종 분류기를 직접 미세조정한 것은 아닙니다.

## 중량은 기존 방법 유지

`legacy_weight.py`는 기존 프로젝트의 RGB+CUBoid 마스크 전처리, ResNet18 복원과 `raw × 480 + 620` 역정규화를 보존합니다. `--weight-labels weights_map.json`으로 각 탐지 ID에 해당하는 기존 라벨을 연결할 수 있습니다.

```json
{"0": "labels/food0.json", "1": "labels/food1.json"}
```

라벨은 각 음식의 원본 사진 기준 cuboid, 파일명과 크기에 맞아야 합니다. EXIF 회전이 있으면 이미지와 라벨을 함께 방향 보정해야 합니다. 대응 마스크가 없으면 `weight_g=null`을 반환합니다. 기존 `cuboid_model.pth`는 LFS 포인터라 자동 cuboid 가중치는 아직 확보되지 않았습니다. 중량 모델 정확도 개선 및 가짜 중량 생성은 하지 않았습니다.

## 학습 재현

Python 3.10 / torch 1.13.1+cu117 / torchvision 0.14.1+cu117 / mmcv-full 1.7.0 / mmdet 2.26.0. `.venv-aihub`를 사용하며 FPB용 `.venv`와 다릅니다. 환경 설치는 `aihub/setup.ps1`입니다.

```powershell
.venv-aihub\Scripts\python.exe aihub\uec_regions.py --archive assets\UECFOODPIXCOMPLETE.tar --output assets\uec_regions_new --train-count 600 --eval-count 96
.venv-aihub\Scripts\python.exe aihub\train_regions.py --data assets\uec_regions_new --output runs\food_regions_new --epochs 3 --batch 4
```

학습 중 검증은 실행하지 않습니다. 마지막 epoch 가중치를 저장하며 test 점수로 epoch를 고르지 않습니다. 저장 파일에는 추론용 state_dict가 있고 optimizer resume 상태는 없습니다. 더 많은 자료로 학습하려면 새 출력 폴더와 증가한 train-count를 사용합니다.

## 최종 검증 한 번

```powershell
.venv-aihub\Scripts\python.exe aihub\final_validation.py --data assets\uec_regions_pilot --regions runs\food_regions_pilot\food_regions.pth --output outputs\final_multifood --user-image "C:\Users\user\Downloads\image.png"
```

한 번의 실행에 계약 테스트, 기존/새 모델의 held-out 위치 비교, 실제 추론 예제, 기존 중량 모델 로드를 포함합니다. 위치 평가는 IoU≥0.5의 클래스 무관 일대일 매칭 precision/recall/F1이고 다중 음식 사진만의 결과도 분리합니다. 음식명 정확도·실제 접시 수 정확도·중량 정확도가 아닙니다. 결과는 `outputs/final_multifood/metrics.json`, 테스트 로그는 `tests.txt`에 남습니다.

## 자체 다중 음식 데이터로 분류기까지 학습할 때

`prepare.py`는 COCO train/val 이미지·JSON을 기존 클래스 순서로 정리합니다. `--allow-new-classes`로 기존 클래스 뒤에 새 클래스를 추가할 수 있습니다. 같은 식사를 여러 각도로 촬영한 것은 동일 `group_id`로 관리해 한 split에만 배치해야 합니다. `--grids`는 train 이미지 4장을 2×2 배치하는 보조 합성이고 실제 다중 음식 검증 자료를 대신하지 않습니다.

```powershell
.venv-aihub\Scripts\python.exe aihub\prepare.py --train-json custom\train.json --train-images custom\train --val-json custom\val.json --val-images custom\val --allow-new-classes --grids 100 --output assets\custom_prepared
.venv-aihub\Scripts\python.exe aihub\finetune.py --data assets\custom_prepared --epochs 12 --work-dir runs\custom_multifood
.venv-aihub\Scripts\python.exe aihub\evaluate.py --data assets\custom_prepared --model runs\custom_multifood\epoch_12.pth --output outputs\custom_final.json
```

`runs/aihub_integration_ONLY*`는 이전 개발 중 도형으로 학습 코드만 확인한 파일입니다. 음식 모델이 아니므로 사용하지 않습니다. 실제 사용할 위치 가중치는 `runs/food_regions_pilot/food_regions.pth`입니다.
