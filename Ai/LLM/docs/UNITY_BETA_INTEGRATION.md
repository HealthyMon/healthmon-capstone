# Unity 연결용 백본 — healthmon.v1

브라우저 베타 화면과 Unity는 같은 FastAPI·DB·GPU 모델을 사용한다. Unity로 옮길 때 모델이나 기억 처리를 이식하지 않고, 입력창·말풍선·캐릭터 표현을 Unity 컴포넌트로 교체하면 된다. 아래 클라이언트는 기존 HTTP JSON 계약을 호출한다. **Unity 프로젝트/Editor는 이 작업 폴더에 없으므로 Unity 가져오기·플랫폼 빌드·기기 실행은 검증하지 않았다.**

## 파일과 연결 순서

`integrations/unity/`의 세 `.cs` 파일을 Unity 프로젝트의 `Assets/Healthmon/`에 복사한다. 별도 JSON 패키지, 모델 파일, DB 드라이버는 필요하지 않다. `UnityWebRequest.Result`를 사용하는 API를 기준으로 작성했으며 실제 대상 Unity 버전에서 가져오기 확인이 필요하다.

1. 빈 GameObject에 `HealthmonApiClient`와 `HealthmonCharacterBridge`를 추가한다.
2. 런타임 로그인/테스트 설정에서 서버 주소와 사용자 Bearer 토큰을 제공한다. 토큰을 소스·Inspector·빌드에 넣지 않는다. 예시 컴포넌트는 토큰을 저장하지 않는다.
3. `ConnectNew(baseUrl, token, "몽글이")`로 새 펫을 만들거나 `ConnectExisting(baseUrl, token, petId)`로 기존 펫을 선택한다. 기존 목록은 `api.ListPets(...)`로 조회한다. `api.PetId`를 해당 사용자 계정에 연결해 보관한다.
4. 입력창의 전송 이벤트를 `bridge.Send(text)`에 연결한다. 동시에 한 요청만 진행한다. `api.IsBusy` 동안 전송 버튼을 비활성화하고 대기 표시를 한다.
5. 아래 이벤트를 자신의 말풍선·Animator·퀘스트 UI에 연결한다. 애니메이션 문자열은 임의의 Animator 트리거를 실행하지 말고 정해진 매핑으로 처리한다.

```csharp
// 로그인에서 받은 값이며 실제 토큰을 코드에 작성하지 않는다.
bridge.onSpeech.AddListener(text => bubble.SetText(text));
bridge.onEmotion.AddListener(value => character.SetExpression(value));
bridge.onAnimation.AddListener(value => character.PlayKnownAnimation(value));

// 최근 대화 복원: 각 row의 user를 먼저, assistant가 null이 아닐 때만 답변 표시.
api.Configure(serverUrl, userToken);
api.SelectPet(savedPetId);
api.GetState(state => api.GetHistory(history => RenderHistory(history.messages)));
```

`bubble`, `character`, `RenderHistory`는 프로젝트가 구현할 표시 계층의 예시다. `ConnectExisting`의 상태 조회가 완료된 뒤 history 등 다음 호출을 한다. 저수준 클라이언트는 호출을 자동 큐잉하지 않으며 동시 호출은 오류 이벤트로 알린다. `GetState(success)` 안에서 다음 요청을 시작하면 순서를 보장할 수 있다.

## 응답을 화면에 연결하기

| 서버 응답 / 클라이언트 이벤트 | Unity 사용처 |
|---|---|
| `response.speech` / `SpeechReceived`, `onSpeech` | 캐릭터 말풍선 |
| `response.emotion` / `EmotionReceived`, `onEmotion` | neutral, happy, encouraging, sad, tired, grumpy, playful 표정 |
| `response.animation` / `AnimationReceived`, `onAnimation` | idle, wave, cheer, encourage, rest, pout, laugh 모션 |
| `execution` / `ExecutionReceived` | 서버가 실제 처리한 결과 |
| `execution.offer_id` / bridge `onOffer` | 수락·거절 버튼의 대상 ID. 빈 문자열이면 버튼 숨김 |
| `execution.deleted_memory_id` | 서버가 기억 삭제를 실제 실행했는지 확인 |
| `state_after`, `state_version` | 서버가 계산한 성격·기분·버전 갱신 |
| `metrics.fallback` | 정상 생성과 기본 응답 대체 구분; 오류 문구는 별도 상태 UI |
| `GET /quests`의 `offers[].progress`, `template.target`, `status`, `reward_balance` | 퀘스트 진행·완료·보상 표시 |

알 수 없는 표정/모션 문자열은 neutral/idle로 표시한다. `ChatReceived`는 전체 응답을 받는 C# 이벤트다. bridge는 표시 계층 예시이며 팀의 Animator 상태 이름을 가정하지 않는다. 이미지·모션 리소스는 별도 캐릭터 프리젠터가 담당한다.

**모델 대사는 사실의 권위가 아니다.** 모델이 목표와 진행 숫자를 뒤집어 말하는 기존 오류가 남아 있다. 진행바와 보상은 `/quests`가 반환한 구조화된 DB 값으로 표시한다. `response.action`이나 `personality_update`를 클라이언트에서 직접 실행해 상태·성격·보상을 바꾸지 않는다. 퀘스트 수락은 `execution.offer_id`로 `DecideQuest(offerId, true, ...)`를 호출한다. `action.target_id`는 템플릿 ID이므로 수락 주소로 쓰면 안 된다. 결정 후 `GetState`와 `GetQuests`를 다시 호출한다. bridge의 수락/거절 메서드는 이 새 조회를 수행한다.

## HTTP 계약

모든 아래 요청은 `Authorization: Bearer <사용자 토큰>`을 보낸다. 브라우저 로컬 세션 초기화는 Unity 인증 대신 사용하지 않는다.

| 동작 | 메서드·경로 | 클라이언트 |
|---|---|---|
| 내 펫 목록 | `GET /pets` | `ListPets` |
| 펫 생성 | `POST /pets` | `CreatePet` |
| 상태 | `GET /pets/{pet}/state` | `GetState` |
| 최근 대화 | `GET /pets/{pet}/messages?limit=50` | `GetHistory` |
| 대화 | `POST /pets/{pet}/chat` | `SendChat`, `RetryPendingChat` |
| 퀘스트 | `GET /pets/{pet}/quests` | `GetQuests` |
| 수락·거절 | `POST /pets/{pet}/quests/{offer_id}/decision` | `DecideQuest` |

history의 `limit`는 사용자 턴 수(1~100)이며 시간순 `messages`를 반환한다. 각 항목은 `user`, nullable `assistant`, `response`, `execution`, `metrics`, 원본 ID·revision을 포함한다. 원본 정정 시 예전 답변은 숨기고 정정된 사용자 문장을 복원하며, 삭제된 원본은 반환하지 않는다. 현재 서버는 fallback 대화를 exchanges에 저장하지 않아 새 접속의 history에서 해당 턴을 복원할 수 없다. `has_more=true`는 오래된 대화가 더 있다는 의미이며 현재 커서 페이지네이션은 제공하지 않는다.

DTO는 Unity `JsonUtility`에 맞게 public 필드·배열·객체 wrapper만 사용한다. nullable 수치나 Dictionary를 UI가 필요하지 않은 곳에 억지로 매핑하지 않는다. 예를 들어 nullable `metrics.raw_valid`와 서버 적용 대상이 아닌 `personality_update`는 DTO에서 생략한다. 원본 응답 전체 계약은 `/openapi.json`, `docs/API_EXAMPLES.md`와 `src/contracts.py`를 참조한다.

## 재시도와 취소

`SendChat`는 GUID `request_id`와 당시 `state_version`을 한 번 만든다. 요청 실패·timeout·취소 후 `RetryPendingChat`는 **동일 ID·동일 문장·동일 버전**을 다시 전송한다. 서버가 이미 완료했다면 저장된 응답을 받는다. 재전송을 새 메시지처럼 말풍선에 중복 추가하지 말고 `request_id`로 기존 대기 항목을 갱신한다. pending 요청이 있으면 다른 문장의 신규 전송과 펫 전환을 차단한다.

- 기본 timeout은 240초이며 Inspector에서 조정할 수 있다. GPU 최초 로딩·대기·생성에 시간이 걸릴 수 있다. 스트리밍은 아직 없고 최종 JSON 한 번을 받는다.
- `CancelCurrent`와 컴포넌트 비활성화는 HTTP 대기를 중단한다. **GPU 생성·DB 처리가 취소됐다는 뜻은 아니다.** pending ID를 보존하고 재시도로 결과를 확인한다.
- 네트워크 오류/503은 연결 복구 후 같은 요청으로 재시도한다. 자동 반복·새 request_id 생성은 하지 않는다.
- 409는 응답 detail로 구분한다. `Request in progress`는 같은 ID로 잠시 뒤 다시 확인한다. 명시적 상태 버전 충돌은 `GetState` 완료 → `RebasePendingChatToLatestState` → `RetryPendingChat` 순서로 처리한다. ID와 문장은 계속 유지된다. 서로 다른 문장으로 ID를 재사용하면 안 된다.
- 410은 기억 정정·삭제로 저장 답변이 무효화된 상태다. history/state를 새로 조회하고 pending을 폐기한 뒤 사용자가 새 질문을 보내게 한다. 기존 답변을 다시 노출하지 않는다.
- 401은 같은 사용자 세션의 토큰을 새로 받은 후 `SetBearerToken`으로 갱신한다. 계정을 바꾸는 경우 기존 계정의 pending을 새 계정에 넘기지 않는다.
- 422는 입력을 고쳐 새 요청으로 보낸다. `DiscardPendingChat`는 로컬 추적만 삭제하며 서버 작업을 되돌리지 않는다. timeout 직후 무조건 폐기하면 서버에 중복 대화가 생길 수 있다.

pending은 기본적으로 메모리에만 있다. 앱 종료까지 복구하려면 `ExportPendingChat()`의 JSON을 앱의 보호된 저장소에 저장하고, 같은 사용자·같은 펫 선택 후 `RestorePendingChat(json)`으로 복원한다. 내보낸 JSON에 사용자 문장이 포함되므로 일반 로그로 출력하지 않는다. 토큰은 내보내지 않는다. HTTP 오류 원문은 `Failed` 이벤트에서 진단할 수 있고, bridge는 이를 캐릭터 대사와 분리해 안내한다.

펫 생성에는 채팅과 같은 request_id 계약이 없다. 생성 응답이 유실되면 곧바로 재생성하지 말고 `ListPets`로 생성 여부를 확인한다. 퀘스트 결정은 같은 offer ID·같은 결정을 재전송하면 서버가 중복을 처리한다.

## 모바일·운영 전 남은 점

PC의 Unity Editor는 `http://127.0.0.1:8000`을 사용할 수 있다. 휴대폰에서 `127.0.0.1`은 휴대폰 자신이므로 PC의 LAN 주소 또는 HTTPS 서버 주소가 필요하다. API의 listen 주소·방화벽·동일 네트워크 설정은 별도다. 이번 백본 추가만으로 외부 접속을 열지 않는다. 모바일 빌드의 HTTP 허용 정책과 Unity WebGL의 CORS 설정은 실제 배포 환경에서 확인해야 한다.

지금은 로컬 베타 사용자 토큰 방식이다. 운영 로그인, 토큰 만료/갱신 서버, 사용자별 GPU 요청 제한, Unity 플랫폼별 연결 테스트는 별도 작업이다. **`X-Producer-Token`은 Unity·브라우저에 포함하지 않는다.** 확인된 걸음 수/운동 기록의 생산 권한은 신뢰된 서버/센서 연동에 남기며, 채팅이나 휴대폰 클라이언트 주장만으로 퀘스트 완료·보상을 확정하지 않는다.

구현에 참고한 Unity 공식 문서: [UnityWebRequest.SendWebRequest](https://docs.unity3d.com/ScriptReference/Networking.UnityWebRequest.SendWebRequest.html), [UnityWebRequest.Abort](https://docs.unity3d.com/ScriptReference/Networking.UnityWebRequest.Abort.html), [JsonUtility](https://docs.unity3d.com/ScriptReference/JsonUtility.html).
