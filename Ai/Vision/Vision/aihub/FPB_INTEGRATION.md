# 음식별 크롭 중량 추정

```powershell
cd C:\Users\user\Desktop\capstone\Vision
.\Run-FoodAI.ps1 -ImagePath '.\food.jpg' -OutputPath '.\outputs\food_result'
```

현재 방식은 기존 위치 모델의 음식 bbox마다 독립적으로 이미지를 자른 뒤 FPB YOLOv12XL을 실행합니다. 같은 이름의 음식도 각 박스별로 계산합니다. 모델은 한 번만 로드하고 각 크롭을 순서대로 처리합니다. 음식명은 NoisyViT 결과를 유지합니다.

크롭을 비율 유지한 640 입력으로 letterbox 처리하고, 모델의 디코딩된 원시 출력 [cx, cy, w, h, mass_g, class scores...]에서 중량 후보를 선택합니다. 클래스 점수 × 크롭 전체와의 IoU가 가장 높은 유효 후보의 mass_g를 사용합니다. 전체 사진의 두 모델 박스를 매칭하는 단계와 검출 점수 컷오프는 사용하지 않습니다. 중량을 픽셀 면적으로 비례 보정하거나 고정값으로 채우지 않습니다.

점수 0.35 미만 또는 크롭 IoU 0.5 미만도 값을 반환하되 weight_status=estimated_fpb_crop_low_confidence, needs_weight_confirmation=true로 구분합니다. 그 외에는 estimated_fpb_crop입니다. 모델이 정상적으로 유한 양수 회귀값을 출력하는 경우 박스마다 하나의 값이 나옵니다. 모든 후보가 비정상 값이거나 실행에 실패하면 숫자를 만들지 않고 명시적으로 오류를 반환합니다.

이 방식은 미검출로 인한 빈 값을 줄이기 위한 휴리스틱이며, FPB 원본 평가 방식과 다릅니다. 크롭 확대와 낮은 신뢰도 후보 사용으로 중량 정확도가 보장되지 않습니다. 실측 중량 데이터로 검증·재학습해야 합니다.

영양소는 음식 탐지/noisyvit_food2k_nutrition_all2000.csv의 출력 번호 매핑과 100g당 값을 사용합니다. JSON nutrition.portion은 해당 값에 예측 중량/100을 곱합니다. CSV의 대응 방식·출처·문자 신뢰도는 JSON에 보존합니다.

annotated.jpg에는 박스와 이름만 표시합니다. overview.jpg에는 전체 사진과 음식별 중량·영양소 정보 박스를 표시합니다. result.json에는 weight_g, weight_status, weight_details(크롭 좌표·후보 점수·IoU), 영양소가 포함됩니다.

최종 기능 테스트 21개 통과. food.jpg의 음식 10개 모두 유효한 양수 중량과 영양소 환산 결과를 반환했습니다. 결과는 outputs/food_result_crop_weight에 저장했습니다. 실측 정답이 없어 중량 정확도를 평가한 결과는 아닙니다.
