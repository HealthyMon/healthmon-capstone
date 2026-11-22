# Food2K 음식명·영양소와 FPB 중량

현재 실행 방법과 상세 구조는 [FPB_INTEGRATION.md](FPB_INTEGRATION.md)를 참고하세요.

- 기본 위치 모델: active_region.json의 DishSeg 모델.
- 기본 음식명: 사용자가 제공한 NoisyViT-B/16 384 가중치.
- 기본 매핑·영양소: 음식 탐지/noisyvit_food2k_nutrition_all2000.csv. noisyvit_prediction_index를 직접 사용합니다.
- 기본 중량: 음식 탐지/Multitask-Food-Portion-Estimation/YOLOv12XL.pt.
- annotated.jpg: 음식 bbox와 이름만 표시.
- overview.jpg: 전체 사진과 음식별 크롭·중량·100g당 영양소·예측 중량 기준 영양소 카드.
- result.json: 좌표, 후보 5개, 점수, 중량 대응 상태, 영양소와 출처.

새 CSV는 auto 또는 csv 클래스 순서를 사용합니다. 과거 imagefolder/numeric 옵션은 명시적 매핑이 없는 이전 형식 CSV용이며 새 CSV와 함께 사용하면 오류를 반환합니다.

NoisyViT는 torchvision ViT에 state_dict를 엄격하게 변환해 로드합니다. RGB 384 resize와 ImageNet 정규화를 사용하며, 음식 크롭을 한 장씩 추론합니다. 이전 검증에서 독립 ViT 연산과 logits 최대 차이 0.00000704를 확인했습니다. 분류 점수는 보정되지 않은 softmax이며 인식 정확도 검증과는 다릅니다.

공식 구현 참고: https://github.com/Tonmoy-Ghosh/NoisyViT_Food

과거 outputs/final_food2k 기록은 당시 모델 연결 검증입니다. 현재 통합 결과는 outputs/food_result_fpb 및 outputs/fpb_integration_tests.log를 참고하세요.
