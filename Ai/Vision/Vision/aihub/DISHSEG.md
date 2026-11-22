# DishSeg24K 다중 음식 위치 모델 추가 학습

기존 UEC 위치 모델을 시작점으로 DishSeg24K의 **개체별 COCO 박스**를 학습합니다. 기존 AI Hub 800종 음식명 모델과 중량 모델은 변경하지 않습니다. 물리적인 접시 자체가 아니라 음식 개체 영역을 검출합니다.

원본: `C:/Users/user/Desktop/Dishseg24K/Dishseg24K`. 원본 폴더는 읽기만 합니다. 학습용 이미지와 manifest는 현재 프로젝트의 `assets/dishseg_regions`에 생성합니다. 음식 종류는 위치 모델에서 하나의 `food` 클래스로 통합합니다.

## 데이터와 학습

- 공식 train 19,365장을 사용하되 crowd/ignore 주석이 있는 이미지는 통째로 제외합니다. 부분적으로 라벨을 버려 학습 시 배경으로 오인하지 않도록 하기 위한 처리입니다.
- 공식 test는 마지막 평가에만 사용합니다. 이미지 파일명과 원본 SHA256으로 정확한 split 중복을 차단합니다. near-duplicate까지 보장하는 것은 아닙니다.
- 실제 원본에서 train/test 간 내용이 완전히 같은 이미지가 발견되었습니다. train 또는 replay와 같은 해시를 가진 test 이미지는 평가에서 제외하고, 각 split 내부의 동일 파일도 한 번만 사용합니다. 제외 개수는 provenance.json에 기록합니다. 따라서 최종 평가는 공식 test 전체 숫자보다 작을 수 있습니다.
- 원본 크기를 확인한 후 긴 변 960 이하로 저장하고 모든 박스를 같은 비율로 변환합니다. EXIF를 자동 회전하지 않고 주석 좌표계 그대로 저장합니다.
- 실제 파일과 COCO에 기재된 해상도가 다르면 좌표를 추측해 고치지 않고 해당 이미지를 제외합니다. 제외 파일과 양쪽 해상도는 provenance.json에 기록합니다.
- 이전 UEC train 600장을 4번 반복해 약 2,400장 분량의 replay를 추가합니다. 기존 UEC 평가 96장은 replay에 사용하지 않습니다.
- 이전 가중치 `runs/food_regions_pilot/food_regions.pth`에서 시작합니다. 3 epoch, batch 8, 학습률 0.001, 짧은 변 480/최대 변 800, CUDA mixed precision을 사용합니다.
- 마지막 epoch 파일을 저장합니다. 학습 도중 평가·best 선택·임계값 조정은 하지 않습니다.

```powershell
cd C:\Users\user\Desktop\capstone\Vision
.venv-aihub\Scripts\python.exe aihub\prepare_dishseg.py --source "C:\Users\user\Desktop\Dishseg24K\Dishseg24K" --output assets\dishseg_regions --replay assets\uec_regions_pilot\train.json
.venv-aihub\Scripts\python.exe aihub\train_regions.py --data assets\dishseg_regions --output runs\food_regions_dishseg --init runs\food_regions_pilot\food_regions.pth --epochs 3 --batch 8 --short-side 480 --max-side 800 --lr 0.001 --workers 2 --amp
```

새 위치 가중치에는 해상도 설정도 저장되므로 로더가 동일 설정을 복원합니다. 기존 체크포인트는 원래 320/640으로 로드됩니다. 개선에는 데이터뿐 아니라 입력 해상도 증가도 포함됩니다.

## 마지막에 한 번 비교

`compare_regions_final.py`는 모든 학습이 끝난 뒤 다음을 한 번에 실행합니다.

1. 계약 테스트
2. DishSeg 공식 test의 기존 위치 모델 대 신규 위치 모델 비교
3. 이전 UEC 평가 자료에서 성능 저하 비교
4. 실제 추론 JSON·박스·크롭 예제 생성, 기존 중량 모델 로드

두 모델의 위치 점수 임계값은 0.5, 정답 매칭은 IoU≥0.5입니다. 다중 음식 사진 성능을 별도로 보고합니다. 추가 COCO AP50/AP50:95 계산에서는 0.05 이상 예측을 사용합니다. 클래스 무관 위치 평가이며 음식 이름 정확도는 아닙니다.

사전 선택 기준: **DishSeg F1 증가 + UEC F1 하락이 5%p 이내**일 때만 새 모델을 기본 실행 모델로 선택합니다. 충족하지 않으면 기존 모델을 기본값으로 유지하며 새 파일은 삭제하지 않습니다. `active_region.json`과 `outputs/final_dishseg/metrics.json`에 선택 근거가 기록됩니다. 평가 결과를 보고 다시 학습하지 않습니다.

```powershell
.venv-aihub\Scripts\python.exe aihub\compare_regions_final.py --data assets\dishseg_regions --regression-data assets\uec_regions_pilot --baseline runs\food_regions_pilot\food_regions.pth --candidate runs\food_regions_dishseg\food_regions.pth --output outputs\final_dishseg --user-image "C:\Users\user\Downloads\image.png"
.\Run-FoodAI.ps1 -ImagePath "C:\path\meal.jpg"
```

데이터 출처: https://huggingface.co/datasets/Schwertlilien/Dishseg24K . 배포 카드의 CC-BY-4.0 및 원본 LICENSE를 보존합니다. UEC replay 자료에는 별도의 비상업 연구 조건이 있으므로 이 실험 모델도 상업 배포 가능하다고 단정하지 않습니다.

기존 중량은 원래 cuboid 방식이고 필요한 마스크가 없으면 null입니다. 현재 800종에 없는 이름을 이번 위치 학습으로 새로 알게 되는 것은 아닙니다.
