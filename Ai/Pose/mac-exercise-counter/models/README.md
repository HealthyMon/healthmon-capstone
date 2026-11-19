# 로컬 모델

공식 사전학습 ONNX 파일을 변환·양자화 없이 사용합니다. 다운로드 ZIP도 재설치용으로 보관합니다. 파일의 SHA-256, 원본 다운로드 URL, API 입력 크기는 `manifest.json`에 있습니다. 앱은 파일이 없으면 오류를 표시하며 온라인 다운로드를 시작하지 않습니다.

| 역할 | 실제 모델 | ONNX 입력 NCHW | rtmlib 입력 크기 |
|---|---|---|---|
| 자세 | RTMPose-L, Body7 학습, COCO Body 17, `rtmpose-l_simcc-body7_pt-body7_420e-384x288-3f5a1437_20230504` | 1×3×384×288 | `(288,384)` — 너비, 높이 |
| 사람 탐지 | YOLOX-tiny HumanArt, `yolox_tiny_8xb8-300e_humanart-6f3252f9` | 1×3×416×416 | `(416,416)` |

[MMPose 공식 모델 표](https://github.com/open-mmlab/mmpose/tree/main/projects/rtmpose#-model-zoo), [rtmlib 모델 표와 API](https://github.com/Tau-J/rtmlib).

`Body(mode="performance")`는 사용하지 않습니다. rtmlib 0.0.16의 `RTMPose`와 `YOLOX`를 각각 상속하여 로컬 파일과 ORT 세션을 명시합니다. 전처리·사람 영역 crop·SimCC 복호화는 rtmlib 구현을 사용합니다. YOLOX의 NMS 포함 export에서 rtmlib가 0.3으로 고정한 출력 score 필터만 설정값을 따르도록 재정의했습니다.

`coreml-cache/`, `coreml-cache-static/`는 이 Mac에서 ORT가 만드는 로컬 CoreML 컴파일 캐시입니다. 탐지기의 빈 NMS 결과에 CoreML이 실패하는 문제를 막기 위해 탐지기에는 `RequireStaticInputShapes=1`을 사용합니다. 해당 동적 후처리는 CPU에서 실행합니다. 자세 모델에는 0을 사용합니다. 두 모델 모두 `CoreMLExecutionProvider`와 `CPUExecutionProvider`가 실제로 활성화됩니다. 모든 연산이 GPU/ANE에서 실행된다는 뜻은 아닙니다.
