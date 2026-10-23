# Unity 임시 계약 healthmon.v1

실제 팀 서버 인증·웨어러블 이벤트 규격·Unity 애니메이션 enum은 미확보다. 이 문서는 로컬 테스트 계약이다. 실행 중인 API의 `/docs`에 모든 스키마가 있다.

1. `Authorization: Bearer <.env의 A 또는 B 토큰>`으로 인증한다.
2. `POST /pets`에 `{"name":"몽글이","profanity":"mild","speech_level":"casual","timezone":"Asia/Seoul"}`를 보내 반환된 pet_id를 보관한다.
3. `POST /pets/{pet_id}/chat`에 아래 JSON을 보낸다. 같은 메시지 재전송에는 같은 request_id를 쓴다. 다른 내용으로 재사용하면 409다.

```json
{"request_id":"unique-request-0001","text":"오늘 운동 퀘스트 추천해줘","state_version":0}
```

응답 예시(설명용이며 ID/숫자는 실제 반환값을 사용):

```json
{
  "schema_version":"healthmon.v1",
  "request_id":"unique-request-0001",
  "response":{
    "speech":"500걸음 걷기 퀘스트를 해볼까?",
    "emotion":"encouraging",
    "animation":"encourage",
    "action":{"type":"offer_quest","target_id":"walk_500"},
    "memory_ids":[],
    "personality_update":null
  },
  "state_version":1,
  "execution":{"offer_id":"server-issued-offer-id"}
}
```

실제 응답에는 state_used/state_after와 metrics도 있다. 말풍선에는 `response.speech`만 표시한다. `target_id`는 템플릿 식별자, 수락 대상은 서버가 발급한 `execution.offer_id`다. JSON과 내부 ID를 사용자 대사로 보여주지 않는다.

`POST /pets/{pet}/quests/{offer_id}/decision` + `{"decision":"accept"}` 또는 `reject`. 오래된 state_version의 제안, 만료 제안, 다른 펫 제안은 실행되지 않는다. 상태 조회는 `GET /pets/{pet}/quests`.

확인된 활동은 `/pets/{pet}/activities`에 인증과 `X-Producer-Token`을 함께 보낸다. 일반 채팅은 확인된 기록으로 승격되지 않는다.

```json
{
  "event_id":"backend-event-0001","revision":1,
  "occurred_at":"2026-09-29T12:00:00+09:00",
  "kind":"walk","amount":500,"unit":"steps",
  "source":"backend","confirmed":true,"label":"local synthetic test"
}
```

occurred_at은 실제 발생 시각이어야 하며 미래 시각은 거부한다. 위 예시 시각을 현재 입력에 그대로 재사용하지 않는다. 같은 event_id/revision/내용은 중복 처리되고, 정정은 revision+1을 사용한다. 활동 사진은 source=photo, confirmed=false이다.

기억 검색: `GET /pets/{pet}/memories?query=좋아하는+운동`. 응답의 source_id/revision을 기준으로 원본을 관리한다. 정정: `PATCH /pets/{pet}/sources/{source_id}` + `{"expected_revision":1,"text":"나는 수영이 좋아."}`. 그 뒤 `POST /pets/{pet}/memories` + `{"source_id":"...","revision":2,"slot":"preference"}`로 최신 원본을 기억에 등록한다. 삭제: `DELETE /pets/{pet}/memories/{memory_id}?expected_revision=2` 또는 원본 삭제 API.

채팅에서 `방금 말한 걷기 취향은 기억하지 마.`처럼 대상 슬롯이 명시되고 활성 원본이 하나로 식별되면 서버가 삭제한다. `execution.deleted_memory_id`가 있어야 실제 삭제된 것이다. 모호한 `그거 기억하지 마.`는 확인 질문을 한다. 이 경로는 모델에 삭제 권한을 주지 않고 인증된 서버 규칙으로 처리한다.

확인 활동 입력 후 적절한 후보가 있으면 제안 대기 작업을 DB에 남긴다. `/quests` 응답의 `pending_activity_suggestions`를 확인하고 `POST /pets/{pet}/activity-suggestions/{event_id}?revision=1`을 호출하면 로컬 Qwen이 후보를 판단해 제안을 저장한다. 같은 이벤트 revision을 재호출하면 저장된 결과를 반환한다. 이 인터페이스는 팀 서버가 이벤트 후 또는 다음 접속 시 호출할 수 있다. 푸시 알림이나 자동 백그라운드 스케줄러는 포함하지 않는다.

활동 기간 조회는 `GET /pets/{pet}/activities?start=ISO시각&end=ISO시각`, 기억 검색도 선택적 start/end를 지원한다. 시각에는 시간대가 필요하고 end는 미포함이다. 채팅의 오늘/어제/이번 주/지난주 걸음 수는 서버가 해당 기간의 확인된 활동을 직접 합산한다.

오류: 401 인증 없음, 403 확인 활동 생산 권한 없음, 404 소유하지 않은 펫/자료, 409 진행 중/버전 충돌, 410 정정·삭제로 무효화된 응답, 422 입력 형식/시각/단위/토큰 예산 오류, 503 DB 장애. 모델 형식 오류는 최대 1회 보정 후 fallback/action=none이고, fallback으로 상태를 바꾸지 않는다.
