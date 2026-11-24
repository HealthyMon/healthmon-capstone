# 평가용 미디어 출처

파일은 로컬 개발·평가용으로 다운로드했습니다. 앱에서 사용자 카메라 영상을 저장하지 않습니다. 아래 공개 샘플의 이용권은 각 원본 권리자/저장소의 조건을 확인해야 하며, 이 프로젝트가 미디어의 재배포 권리를 별도로 부여하지 않습니다.

| 로컬 파일 | 원본 |
|---|---|
| rtmlib-demo.jpg | https://raw.githubusercontent.com/Tau-J/rtmlib/main/demo.jpg |
| real-exercise-demo.mp4 | https://raw.githubusercontent.com/RiccardoRiccio/Fitness-AI-Trainer-With-Automatic-Exercise-Recognition-and-Counting/main/demo_2.mp4 |
| real-pushup.mp4 | https://raw.githubusercontent.com/shreyanshsatvik/personal_trainer-using-mediapipe/main/videos/pushup2.mp4 |
| real-squat.mp4 | https://raw.githubusercontent.com/shreyanshsatvik/personal_trainer-using-mediapipe/main/videos/squats2.mp4 |
| real-squat-side.mp4 | https://raw.githubusercontent.com/shreyanshsatvik/personal_trainer-using-mediapipe/main/videos/squats3.mp4 |
| real-dumbbell-curl.mp4 | https://raw.githubusercontent.com/shreyanshsatvik/personal_trainer-using-mediapipe/main/videos/weight%20lifting%202.mp4 |
| pushups.mp4 / squat.mp4 / curl.mp4 | 아래 3D 애니메이션 목록 |

`real-exercise-demo.mp4`는 실제 사람이 바벨 컬을 하는 영상입니다. 물체를 검출하지 않는 카운터의 양팔 동시 운동 확인에 사용했습니다. 실제 덤벨 교대 컬은 별도 `real-dumbbell-curl.mp4`로 확인했습니다.

처음 발견한 [exercise-db 저장소](https://github.com/michael-lemarec/free-exercise-db-api)는 영상을 실제 시연으로 설명했지만, 직접 열어 보니 다음 세 파일은 **3D 인체 애니메이션**이었습니다. 실제 사람 정확도 결과에 포함하지 않았습니다.

- https://pub-585d42eb1aa64a67aedf483ec328d3fe.r2.dev/exercise-videos/male/push-ups.mp4
- https://pub-585d42eb1aa64a67aedf483ec328d3fe.r2.dev/exercise-videos/male/squat.mp4
- https://pub-585d42eb1aa64a67aedf483ec328d3fe.r2.dev/exercise-videos/male/dumbbell-biceps-curl.mp4

## 2026-11-06 부분 촬영 비교

`partial-framing/`은 위 로컬 원본 5개로 만든 검증용 파생 MP4입니다. 상체/하체/한쪽 팔다리 크롭, 상체 픽셀 가림, 첫 반복 중 한쪽 팔 가림, 정지 영상의 ±2px 흔들림을 포함합니다. 원본은 보존했습니다. `reports/partial-framing/crops.json`에 원본 SHA-256, 프레임 수, 크롭 좌표와 변환 방식을 기록했습니다. 새 영상 픽셀에서 탐지·pose·카운터를 모두 재실행했으며 원본에서 얻은 관절을 카운터 입력으로 재사용하지 않았습니다. 상체를 제거한 하체 영상의 마스크 경계를 만드는 데만 원본 골반 위치를 사용했습니다.
