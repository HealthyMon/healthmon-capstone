"""Small synthetic event fixtures for lab replay, never model training data."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

SCENARIOS = {
    "steady_exercise_success": "꾸준한 운동과 퀘스트 성공",
    "exercise_then_stop": "초반 운동 후 최근 2주 중단",
    "novel_exercise_food": "새로운 운동과 음식 탐색",
    "repetitive_exercise_quiet": "같은 운동 반복과 적은 대화",
    "frequent_failure_steady_chat": "잦은 퀘스트 실패와 꾸준한 대화",
    "steady_food_low_exercise": "적은 운동과 꾸준한 식생활 관리",
}

_TOPICS = [
    ("독서", "책 속 등장인물이 인상 깊었어"), ("음악", "이 멜로디는 부드러운 기분이야"),
    ("날씨", "맑은 하늘을 보니 마음이 편해"), ("가족", "가족과 즐겁게 웃던 일이 떠올라"),
    ("여행", "처음 가는 동네를 탐색하고 싶어"), ("요리", "따뜻한 수프 향기가 좋았어"),
    ("공예", "작은 종이배를 정성껏 접었지"), ("꿈", "바닷속을 날아다니는 꿈을 꿨어"),
    ("친구", "친구에게 고마움을 전하고 왔어"), ("영화", "영화의 마지막 장면이 기억나"),
    ("반려식물", "새 잎이 나오는 모습을 관찰했어"), ("그림", "노란색으로 풍경을 그려봤어"),
    ("별자리", "밤하늘에서 반짝이는 별을 찾았어"), ("퍼즐", "어려웠던 조각이 딱 맞아서 즐거워"),
]
_FOODS = [
    ("현미밥", "곡류"), ("브로콜리", "채소"), ("사과", "과일"),
    ("두부", "콩류"), ("요거트", "유제품"), ("연어", "생선"),
    ("달걀", "달걀"), ("호두", "견과류"),
]
_EXERCISES = ["walk", "stretch", "cycle", "swim", "dance", "yoga", "hike", "pilates"]


def scenario_events(name: str, days: int = 30, start: datetime | None = None) -> list[dict]:
    if name not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {name}")
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 30:
        raise ValueError("Scenario duration must be 1..30 days")
    start = start or datetime(2026, 10, 1, tzinfo=ZoneInfo("Asia/Seoul"))
    if start.tzinfo is None or start.utcoffset() is None:
        raise ValueError("Scenario start must have a timezone")
    events = []

    def add(day: int, hour: int, kind: str, payload: dict, suffix: str = "", verified: bool = True) -> dict:
        identifier = f"sim:{name}:{day:02d}:{kind}:{suffix}"
        event = {"event_id": identifier, "user_id": "test-persona-lab", "character_id": f"test-{name}",
                 "event_type": kind, "occurred_at": (start + timedelta(days=day, hours=hour)).isoformat(),
                 "source": "simulation", "verification_status": "verified" if verified else "unverified",
                 "confidence": 1.0 if verified else 0.4, "payload": payload, "idempotency_key": identifier}
        events.append(event)
        return event

    add(0, 0, "inactivity_period", {"anchor_only": True, "synthetic": True})
    for day in range(days):
        quest_type = "exercise"
        exercise = (name in ("steady_exercise_success", "novel_exercise_food", "repetitive_exercise_quiet")
                    or (name == "exercise_then_stop" and day < 16)
                    or (name == "steady_food_low_exercise" and day in (4, 18)))
        has_success = name == "steady_exercise_success" and day % 3 == 0
        has_failure = name == "frequent_failure_steady_chat" and day % 2 == 0
        quest_id = "walk_100" if (day // 3) % 2 == 0 else "walk_500"
        instance = f"attempt:{name}:{day}"
        quest_payload = {"quest_id": quest_id, "quest_instance_id": instance, "quest_type": quest_type}
        if has_success or has_failure:
            add(day, 7, "quest_proposed", quest_payload)
            add(day, 8, "quest_accepted", quest_payload)
        if exercise:
            exercise_type = _EXERCISES[day % len(_EXERCISES)] if name == "novel_exercise_food" else "walk"
            recorded = add(day, 9, "exercise_recorded", {"exercise_type": exercise_type, "steps": 1200, "minutes": 15})
            if has_success:
                add(day, 10, "quest_progressed", dict(quest_payload, progress=0.5, evidence_event_ids=[recorded["event_id"]]))
                add(day, 11, "quest_completed", dict(quest_payload, evidence_event_ids=[recorded["event_id"]]))
            if day % 7 == 0:
                events.append(dict(recorded))  # Exact duplicate deliberately probes idempotency.
        if has_failure:
            add(day, 19, "quest_failed", quest_payload)
        if name in ("novel_exercise_food", "steady_food_low_exercise"):
            food, group = _FOODS[day % len(_FOODS)]
            add(day, 12, "food_recorded", {"food_name": food, "food_group": group, "balanced": True,
                                             "confirmed": True, "amount": 1, "unit": "serving"})
        if name != "repetitive_exercise_quiet" or day in (0, 20):
            topic, text = _TOPICS[day % len(_TOPICS)]
            add(day, 18, "positive_interaction", {"text": text, "meaningful": True, "topic": topic})
        if day == 9:
            add(day, 20, "exercise_recorded", {"exercise_type": "unverified-claim", "steps": 9999}, "unverified", False)
    return events
