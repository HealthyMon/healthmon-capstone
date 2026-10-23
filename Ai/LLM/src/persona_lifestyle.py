"""Compile aggregate lifestyle inputs into explicit synthetic replay fixtures.

This module never infers a person's actual dates, exercises, dishes or nutrients.
It builds one reproducible development scenario compatible with the existing
event engine. It does not train a model, write a database, or calculate growth.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

COMPILER_VERSION = "persona-lifestyle.v1"


class LifestyleInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    days: Literal[1, 7, 14, 30] = 7
    exercise_sessions: int = Field(default=0, ge=0, le=120, strict=True)
    exercise_minutes: float = Field(default=0, ge=0, le=28800)
    exercise_intensity: float = Field(default=3, ge=1, le=5)
    exercise_streak: int = Field(default=0, ge=0, le=30, strict=True)
    exercise_types: int = Field(default=0, ge=0, le=30, strict=True)
    upper_sessions: int = Field(default=0, ge=0, le=120, strict=True)
    lower_sessions: int = Field(default=0, ge=0, le=120, strict=True)
    cardio_sessions: int = Field(default=0, ge=0, le=120, strict=True)
    flexibility_sessions: int = Field(default=0, ge=0, le=120, strict=True)
    quest_successes: int = Field(default=0, ge=0, le=120, strict=True)
    quest_failures: int = Field(default=0, ge=0, le=120, strict=True)
    food_days: int = Field(default=0, ge=0, le=30, strict=True)
    food_records: int = Field(default=0, ge=0, le=180, strict=True)
    new_foods: int = Field(default=0, ge=0, le=180, strict=True)
    new_food_groups: int = Field(default=0, ge=0, le=30, strict=True)
    food_diversity: Literal["low", "medium", "high"] = "low"
    balanced_meals: int = Field(default=0, ge=0, le=180, strict=True)
    fast_food_meals: int = Field(default=0, ge=0, le=180, strict=True)
    unknown_foods: int = Field(default=0, ge=0, le=180, strict=True)
    food_streak: int = Field(default=0, ge=0, le=30, strict=True,
                             description="전체 식사 기록의 최장 연속일수. 성장 보너스에 유효한 음식 연속일수와 다를 수 있습니다.")
    last_exercise_gap_days: int = Field(default=0, ge=0, le=30, strict=True)
    duplicate_events: int = Field(default=0, ge=0, le=20, strict=True)
    unverified_events: int = Field(default=0, ge=0, le=20, strict=True)

    @field_validator("days", "exercise_minutes", "exercise_intensity", mode="before")
    @classmethod
    def numbers_not_booleans(cls, value):
        if isinstance(value, bool):
            raise ValueError("숫자 입력에는 true/false를 사용할 수 없습니다.")
        return value

    @model_validator(mode="after")
    def compatible_totals(self):
        categories = (self.upper_sessions, self.lower_sessions, self.cardio_sessions, self.flexibility_sessions)
        if sum(categories) > self.exercise_sessions:
            raise ValueError("상체·하체·유산소·유연성 횟수 합은 전체 운동 횟수를 넘을 수 없습니다.")
        if self.last_exercise_gap_days > self.days:
            raise ValueError("마지막 운동 이후 날짜는 전체 기간 이하여야 합니다.")
        span = self.days - self.last_exercise_gap_days
        if self.exercise_sessions > span * 4:
            raise ValueError("운동 배분은 활동 가능한 날짜마다 최대 4회입니다. 기간 또는 횟수를 조정하세요.")
        if self.exercise_sessions:
            if not self.exercise_sessions <= self.exercise_minutes <= self.exercise_sessions * 240:
                raise ValueError("전체 운동 시간은 회당 1~240분 범위여야 합니다.")
            if self.exercise_streak > min(self.exercise_sessions, span):
                raise ValueError("운동 연속일수는 운동 횟수 및 활동 가능한 날짜를 넘을 수 없습니다.")
            if self.exercise_types > self.exercise_sessions:
                raise ValueError("운동 종류 수는 운동 횟수를 넘을 수 없습니다.")
            category_count = sum(value > 0 for value in categories) + (sum(categories) < self.exercise_sessions)
            if self.exercise_types and self.exercise_types < category_count:
                raise ValueError("운동 종류 수는 지정한 부위 분류 수보다 적을 수 없습니다.")
        elif any((self.exercise_minutes, self.exercise_streak, self.exercise_types, *categories)):
            raise ValueError("운동 횟수가 0이면 시간·연속일수·종류·부위별 횟수도 0이어야 합니다.")
        if not self.exercise_sessions and self.last_exercise_gap_days not in (0, self.days):
            raise ValueError("기간 내 운동이 0회이면 마지막 운동 이후 날짜는 미지정(0) 또는 전체 기간이어야 합니다.")
        if self.food_records > self.days * 6:
            raise ValueError("음식 기록 배분은 하루 최대 6개입니다.")
        if self.food_days > min(self.days, self.food_records):
            raise ValueError("식생활 기록일수는 전체 기간 및 음식 기록 수를 넘을 수 없습니다.")
        if self.food_days and self.food_records > self.food_days * 6:
            raise ValueError("지정한 식생활 기록일수에는 하루 6개를 넘게 배분할 수 없습니다.")
        if self.balanced_meals + self.fast_food_meals + self.unknown_foods > self.food_records:
            raise ValueError("균형식·패스트푸드·알 수 없는 음식은 겹치지 않는 기록 수로 입력하며 합은 전체 기록 이하여야 합니다.")
        eligible = self.food_records - self.fast_food_meals - self.unknown_foods
        if self.new_foods > eligible or self.new_food_groups > eligible:
            raise ValueError("새 음식·새 음식군 수는 패스트푸드와 미확인 음식을 제외한 음식 기록 수 이하여야 합니다.")
        if self.food_streak > min(self.days, self.food_days or self.days, self.food_records):
            raise ValueError("연속 식사 기록일수는 전체 기간·식사 기록일수·음식 기록 수를 넘을 수 없습니다.")
        if not self.food_records and any((self.food_days, self.new_foods, self.new_food_groups, self.balanced_meals,
                                          self.fast_food_meals, self.unknown_foods, self.food_streak)):
            raise ValueError("음식 기록이 0이면 관련 횟수와 기록일수도 0이어야 합니다.")
        if self.food_diversity == "low" and self.new_food_groups > 1:
            raise ValueError("낮은 음식 다양성은 1개 음식군입니다. 새 음식군이 여러 개라면 다양성을 높이세요.")
        if self.food_diversity == "medium" and (self.new_food_groups > 3 or eligible < 2):
            raise ValueError("보통 음식 다양성에는 검증 가능한 음식 기록 2개 이상과 최대 3개 음식군이 필요합니다.")
        if self.food_diversity == "high" and eligible < 4:
            raise ValueError("높은 음식 다양성에는 검증 가능한 음식 기록 4개 이상이 필요합니다.")
        if self.quest_successes > self.exercise_sessions:
            raise ValueError("운동 퀘스트 성공 수가 운동 기록 수보다 많습니다. 음식 기록은 운동 완료 증거가 아닙니다.")
        if self.quest_failures > self.days * 4:
            raise ValueError("실패 퀘스트는 하루 최대 4개까지 배분합니다.")
        if self.duplicate_events and not self.exercise_sessions + self.food_records + self.quest_failures:
            raise ValueError("중복 시험을 추가하려면 복제할 운동·음식·퀘스트 기록이 필요합니다.")
        return self


def _letters(index: int) -> str:
    """Alphabetic suffix survives the engine's digit-stripping normalization."""
    result = ""
    while True:
        result = chr(ord("a") + index % 26) + result
        index = index // 26 - 1
        if index < 0:
            return result


def _max_streak(days: list[int]) -> int:
    previous, current, longest = None, 0, 0
    for day in sorted(set(days)):
        current = current + 1 if previous is not None and day == previous + 1 else 1
        longest, previous = max(longest, current), day
    return longest


def _select_days(count: int, span: int, streak: int, capacity: int, exact_days: int = 0) -> list[int]:
    if not count:
        return []
    if not span:
        raise ValueError("기록을 배분할 날짜가 없습니다.")
    eligible = list(range(span))
    forced = []
    if streak:
        # Work backwards from the final active date: s occupied dates, one gap.
        eligible = [day for day in eligible if (span - 1 - day) % (streak + 1) != streak]
        forced = list(range(span - streak, span))
    target = exact_days or min(count, len(eligible))
    if target < len(forced) or target > len(eligible) or target * capacity < count:
        raise ValueError("전체 횟수·기록일수·최장 연속일수·하루 상한을 동시에 만족하는 날짜 배분이 없습니다.")
    if forced:
        other = [day for day in eligible if day not in forced]
        needed = target - len(forced)
        selected = forced + ([other[round(i * (len(other) - 1) / (needed - 1))] for i in range(needed)]
                             if needed > 1 else other[:needed])
    else:
        selected = [eligible[round(i * (len(eligible) - 1) / (target - 1))] for i in range(target)] if target > 1 else [eligible[-1]]
    return sorted(selected)


def _counts_on_days(total: int, days: list[int]) -> dict[int, int]:
    return {day: total // len(days) + (index < total % len(days)) for index, day in enumerate(days)} if days else {}


def compile_lifestyle(body: LifestyleInput | dict, start: datetime) -> dict:
    """Return a stable synthetic full-stream fixture; callers use replay_events."""
    body = body if isinstance(body, LifestyleInput) else LifestyleInput.model_validate(body)
    # Pydantic keeps declared numeric default types but coerces explicit floats:
    # omitted intensity=3 and explicit intensity=3.0 must yield identical event
    # IDs and prompt payloads. Preserve established default serialization without
    # mutating the caller or changing nondefault values such as 280.0 minutes.
    defaults = {name: deepcopy(field.default) for name, field in LifestyleInput.model_fields.items()
                if not field.is_required() and getattr(body, name) == field.default}
    body = body.model_copy(update=defaults)
    if not isinstance(start, datetime) or start.tzinfo is None or start.utcoffset() is None:
        raise ValueError("생활 기록 시뮬레이션 시작 시각에는 시간대가 필요합니다.")
    requested = body.model_dump()
    digest = hashlib.sha256(json.dumps({"input": requested, "start": start.isoformat()}, sort_keys=True).encode()).hexdigest()[:12]
    prefix = f"lifestyle:{digest}"
    assumptions = [
        "이 입력은 실제 사용자 기록을 복원하지 않습니다. 합계만으로 날짜를 알 수 없어 결정론적으로 배분한 합성 시뮬레이션입니다.",
        "연속일수는 기간 내 최장 연속 기록일수이며 0은 지정하지 않음입니다. 운동은 하루 최대 4회, 음식은 하루 최대 6개로 배분합니다.",
        "운동 시간은 전체 기간의 총분입니다. 각 세션에 균등 배분하며 강도·시간·부위에 임의 성격 계수를 추가하지 않습니다.",
        "음식 이름과 음식군은 실물을 주장하지 않는 가상 식별자입니다. 제공되지 않은 칼로리·영양소·섭취량은 unknown으로 유지합니다.",
        "성격 변화·상한·연속 보너스는 기존 persona_rules.json 및 replay_events만 계산합니다. 이 함수는 성격값을 수정하지 않습니다.",
    ]
    events: list[dict] = []

    def make(identifier: str, kind: str, at: datetime, payload: dict, verified: bool = True) -> dict:
        result = {"event_id": f"{prefix}:{identifier}", "idempotency_key": f"{prefix}:{identifier}",
                  "user_id": "persona-lab", "character_id": "lab-preview", "event_type": kind,
                  "occurred_at": at.isoformat(), "source": "simulation", "verification_status": "verified" if verified else "unverified",
                  "confidence": 1.0 if verified else 0.0, "payload": dict(payload, synthetic=True)}
        events.append(result)
        return result

    exercise_days = _select_days(body.exercise_sessions, body.days - body.last_exercise_gap_days, body.exercise_streak, 4)
    food_days = _select_days(body.food_records, body.days, body.food_streak, 6, body.food_days)
    exercise_distribution = _counts_on_days(body.exercise_sessions, exercise_days)
    food_distribution = _counts_on_days(body.food_records, food_days)
    known_food_count = body.food_records - body.fast_food_meals - body.unknown_foods
    if not body.exercise_sessions:
        assumptions.append("운동 기록이 없으면 마지막 운동 날짜는 알 수 없습니다. 표시된 공백은 전체 시뮬레이션 기간만큼의 최소 공백입니다.")

    # A type is a declared synthetic representative of its aggregate category.
    categories = [("upper", body.upper_sessions, "upper_body"), ("lower", body.lower_sessions, "lower_body"),
                  ("cardio", body.cardio_sessions, "cycle"), ("flexibility", body.flexibility_sessions, "stretch")]
    remaining = body.exercise_sessions - sum(item[1] for item in categories)
    if remaining:
        categories.append(("unspecified", remaining, "stretch" if body.quest_successes and not body.flexibility_sessions else "general_activity"))
    populated = [item for item in categories if item[1]]
    type_counts = {category: 1 for category, _, _ in populated}
    extra_types = max(0, body.exercise_types - len(populated))
    for category, count, _ in populated:
        take = min(extra_types, count - 1)
        type_counts[category] += take
        extra_types -= take
    sessions = []
    for category, count, representative in populated:
        variants = type_counts[category]
        for index in range(count):
            suffix = index % variants
            # Distinct variants remain specific to their synthetic category.
            exercise_type = representative if suffix == 0 else f"{representative}_{_letters(suffix)}"
            sessions.append({"exercise_type": exercise_type, "category": category})
    if sessions:
        assumptions.append("운동 종류 이름은 가상 대표 유형입니다: 상체 upper_body, 하체 lower_body, 유산소 cycle, 유연성 stretch. 실제 운동 종류로 확정하지 않습니다.")
        if body.exercise_types:
            assumptions.append(f"운동 종류 {body.exercise_types}개는 이 가상 캐릭터가 이번 기간에 처음 접한 유형으로 가정합니다.")
        else:
            assumptions.append("운동 종류 수 0은 종류 미지정입니다. 대표 유형을 기간 이전에 알려진 것으로 두어 첫 운동 종류 보너스를 만들지 않습니다.")
        if remaining and body.quest_successes and not body.flexibility_sessions:
            assumptions.append("종류 미지정 운동은 성공 검증을 위해 가상 스트레칭으로 배정합니다. 입력된 실제 총분만 쓰며 걸음 수는 생성하지 않습니다.")

    eligible_groups = (1 if body.food_diversity == "low" else min(3, known_food_count) if body.food_diversity == "medium"
                       else min(known_food_count, max(4, body.new_food_groups))) if known_food_count else 0
    groups = [f"가상 음식군 {_letters(index)}" for index in range(eligible_groups)]
    foods = []
    for index in range(known_food_count):
        new_name = index < body.new_foods
        name = f"가상 새 음식 {_letters(index)}" if new_name else f"가상 기존 음식 {_letters(index % max(1, eligible_groups))}"
        foods.append({"food_name": name, "food_group": groups[index % len(groups)], "confirmed": True,
                      "balanced": index < body.balanced_meals, "novelty_requested": new_name,
                      "calories": "unknown", "nutrients": "unknown", "amount_description": "unknown"})
    foods += [{"food_name": "가상 패스트푸드", "food_group": "unknown", "confirmed": True, "fast_food": True,
               "calories": "unknown", "nutrients": "unknown", "amount_description": "unknown"} for _ in range(body.fast_food_meals)]
    foods += [{"food_name": "unknown", "food_group": "unknown", "confirmed": False,
               "calories": "unknown", "nutrients": "unknown", "amount_description": "unknown"} for _ in range(body.unknown_foods)]
    baseline = {"exercise": [] if body.exercise_types else sorted({item["exercise_type"] for item in sessions}),
                "food": sorted({item["food_name"] for item in foods[:known_food_count] if not item.get("novelty_requested")}),
                "food_group": groups[body.new_food_groups:]}
    make("anchor", "inactivity_period", start, {"anchor_only": True, "baseline_known": baseline,
                                                  "baseline_reason": "Explicit synthetic pre-period novelty assumptions; no past events or growth."})
    if baseline["food"] or baseline["food_group"]:
        assumptions.append("새 음식·음식군으로 지정하지 않은 가상 이름은 Day 0의 알려진 목록에만 넣습니다. 과거 기록이나 과거 성격 변화는 만들지 않습니다.")

    exercise_records = []
    index = 0
    durations = [round(body.exercise_minutes / body.exercise_sessions, 6)] * body.exercise_sessions if body.exercise_sessions else []
    if durations:
        durations[-1] = round(body.exercise_minutes - sum(durations[:-1]), 6)
    for day, count in exercise_distribution.items():
        for local_index in range(count):
            payload = dict(sessions[index], duration_minutes=durations[index], exercise_intensity=body.exercise_intensity,
                           source_summary="aggregate exercise totals", actual_exercise_type="unknown")
            exercise_records.append(make(f"exercise:{index}", "exercise_recorded", start + timedelta(days=day, hours=8, minutes=local_index * 5), payload))
            index += 1

    # Put one eligible food on each possible date first, including the forced
    # streak at the end. Then fill the other records without inventing nutrition.
    slots = [(day, local_index) for day, count in food_distribution.items() for local_index in range(count)]
    slots.sort(key=lambda item: (item[1] != 0, -item[0] if item[1] == 0 else item[0], item[1]))
    food_records = []
    for index, ((day, local_index), payload) in enumerate(zip(slots, foods)):
        food_records.append(make(f"food:{index}", "food_recorded", start + timedelta(days=day, hours=12, minutes=local_index * 5),
                                 payload, verified=payload["confirmed"]))
    if body.unknown_foods:
        assumptions.append("알 수 없는 음식은 미검증 음식 이벤트로 남기며 성격·novelty·연속 기록 보너스를 지급하지 않습니다.")
    if body.fast_food_meals:
        assumptions.append("패스트푸드는 기존 규칙대로 장기 성격 보너스와 음식 연속 보너스에서 제외됩니다. 반복 기록의 단기 상태만 반영될 수 있습니다.")

    candidates = []
    for record in exercise_records:
        payload = record["payload"]
        if payload["exercise_type"] == "stretch" and payload["duration_minutes"] >= 2:
            candidates.append((record, "stretch_5" if payload["duration_minutes"] >= 5 else "stretch_2", "exercise"))
        elif payload["exercise_type"] == "cycle" and payload["duration_minutes"] >= 5:
            candidates.append((record, "cycle_5", "exercise"))
    candidates.sort(key=lambda item: (item[0]["occurred_at"], item[0]["event_id"]))
    if len(candidates) < body.quest_successes:
        raise ValueError(f"운동 퀘스트 성공 {body.quest_successes}회를 뒷받침할 카탈로그 증거는 {len(candidates)}개입니다. 스트레칭 2분 또는 자전거 5분의 운동 기록이 필요합니다.")
    for index, (record, quest_id, category) in enumerate(candidates[:body.quest_successes]):
        at = datetime.fromisoformat(record["occurred_at"])
        payload = {"quest_id": quest_id, "quest_instance_id": f"{prefix}:attempt:success:{index}", "quest_type": category}
        make(f"accepted:success:{index}", "quest_accepted", at - timedelta(minutes=1), payload)
        make(f"completed:{index}", "quest_completed", at + timedelta(minutes=1), dict(payload, evidence_event_ids=[record["event_id"]]))
    for index in range(body.quest_failures):
        day = index % body.days
        slot = index // body.days
        at = start + timedelta(days=day, hours=17, minutes=slot * 5)
        payload = {"quest_id": "stretch_2", "quest_instance_id": f"{prefix}:attempt:failure:{index}", "quest_type": "exercise"}
        make(f"accepted:failure:{index}", "quest_accepted", at, payload)
        make(f"failed:{index}", "quest_failed", at + timedelta(minutes=1), payload)
    if body.quest_successes or body.quest_failures:
        assumptions.append("운동 퀘스트 성공은 카탈로그 수락→고유 운동 시간 증거→완료로 연결합니다. 음식은 운동 증거로 쓰지 않습니다. 실패는 별도로 수락한 가상 시도이며 보상 지급이나 실제 완료를 주장하지 않습니다.")

    originals = [row for row in events if row["event_type"] != "inactivity_period"]
    for index in range(body.duplicate_events):
        events.append(deepcopy(originals[index % len(originals)]))
    for index in range(body.unverified_events):
        at = start + timedelta(days=index % body.days, hours=20, minutes=index // body.days)
        make(f"unverified:{index}", "exercise_recorded", at,
             {"exercise_type": "unverified_claim", "duration_minutes": 1, "diagnostic_only": True}, verified=False)
    if body.duplicate_events or body.unverified_events:
        assumptions.append("중복·미검증 추가 이벤트는 차단 기능을 확인하는 합성 진단 기록입니다. 입력 운동 총횟수와 시간에는 포함하지 않습니다.")
    events.sort(key=lambda row: (datetime.fromisoformat(row["occurred_at"]), row["event_id"]))
    eligible_food_days = sorted({int((datetime.fromisoformat(row["occurred_at"]) - start).total_seconds() // 86400)
                                 for row in food_records if row["verification_status"] == "verified"
                                 and not row["payload"].get("fast_food")})
    if _max_streak(food_days) != _max_streak(eligible_food_days):
        assumptions.append(f"입력한 식사 연속일수는 전체 기록 달력 기준입니다. 생성된 전체 기록은 최장 {_max_streak(food_days)}일 연속이지만, "
                           f"패스트푸드와 미확인 기록을 제외한 성장 보너스 유효 기록은 최장 {_max_streak(eligible_food_days)}일입니다. "
                           "전체 기록의 연속성을 성장 보너스로 간주하지 않습니다.")
    generated = {
        "days": body.days, "exercise_sessions": len(exercise_records),
        "exercise_minutes": round(sum(row["payload"]["duration_minutes"] for row in exercise_records), 6),
        "exercise_active_days": len(exercise_days), "max_exercise_streak": _max_streak(exercise_days),
        "last_exercise_gap_days": body.days - 1 - max(exercise_days) if exercise_days else body.days,
        "last_exercise_gap_is_lower_bound": not bool(exercise_days),
        "exercise_types": len({row["payload"]["exercise_type"] for row in exercise_records}),
        "exercise_categories": dict(Counter(row["payload"]["category"] for row in exercise_records)),
        "food_records": len(food_records), "food_active_days": len(food_days),
        "eligible_food_active_days": len(eligible_food_days), "max_food_streak": _max_streak(eligible_food_days),
        "max_food_record_calendar_streak": _max_streak(food_days),
        "new_foods": body.new_foods, "new_food_groups": body.new_food_groups,
        "known_food_groups": len(groups), "balanced_meals": body.balanced_meals, "fast_food_meals": body.fast_food_meals,
        "unknown_foods": body.unknown_foods, "quest_successes": body.quest_successes, "quest_failures": body.quest_failures,
        "duplicate_events": body.duplicate_events, "unverified_events": body.unverified_events,
        "event_count": len(events), "baseline_known": baseline,
        "date_allocation": {"exercise": exercise_distribution, "food": food_distribution},
        "excluded_counts": {"unknown_food_identity": body.unknown_foods, "diagnostic_unverified": body.unverified_events,
                            "duplicate_event": body.duplicate_events},
    }
    return {"events": events, "assumptions": assumptions, "requested": requested, "generated_summary": generated,
            "synthetic": True, "training_data": False, "nutrition": {"calories": "unknown", "nutrients": "unknown"},
            "compiler_version": COMPILER_VERSION, "start": start.isoformat(),
            "end": (start + timedelta(days=body.days) - timedelta(microseconds=1)).isoformat(),
            "excluded_records": [{"event_id": row["event_id"], "reason_code": "unknown_food_identity",
                                  "reason": "음식 이름을 알 수 없어 검증되지 않은 기록입니다. 성격·novelty·연속 기록을 변경하지 않습니다."}
                                 for row in food_records if not row["payload"]["confirmed"]]}


LIFESTYLE_PRESETS = {
    "none": {"label": "기록 없음", "input": {"days": 7}},
    "exercise_3_in_7": {"label": "7일 동안 운동 3회", "input": {"days": 7, "exercise_sessions": 3, "exercise_minutes": 90, "exercise_streak": 1, "exercise_types": 1, "cardio_sessions": 3}},
    "steady_14": {"label": "14일 꾸준히 운동", "input": {"days": 14, "exercise_sessions": 14, "exercise_minutes": 280, "exercise_streak": 14, "exercise_types": 1, "flexibility_sessions": 14}},
    "steady_30": {"label": "30일 꾸준히 운동", "input": {"days": 30, "exercise_sessions": 30, "exercise_minutes": 600, "exercise_streak": 30, "exercise_types": 1, "cardio_sessions": 30}},
    "stopped_14": {"label": "초반 운동 후 최근 14일 중단", "input": {"days": 30, "exercise_sessions": 16, "exercise_minutes": 320, "exercise_streak": 16, "exercise_types": 1, "cardio_sessions": 16, "last_exercise_gap_days": 14}},
    "varied": {"label": "다양한 운동과 식생활", "input": {"days": 30, "exercise_sessions": 15, "exercise_minutes": 300, "exercise_streak": 1, "exercise_types": 5, "cardio_sessions": 5, "flexibility_sessions": 5, "upper_sessions": 5, "food_days": 30, "food_records": 30, "new_foods": 12, "new_food_groups": 6, "food_diversity": "high", "balanced_meals": 20, "food_streak": 30}},
    "repetitive_food": {"label": "같은 음식 기록 반복", "input": {"days": 30, "food_days": 30, "food_records": 30, "food_streak": 30}},
    "quest_success": {"label": "운동 퀘스트 반복 성공", "input": {"days": 14, "exercise_sessions": 14, "exercise_minutes": 70, "exercise_streak": 14, "exercise_types": 1, "flexibility_sessions": 14, "quest_successes": 7}},
    "quest_failure": {"label": "수락한 퀘스트 반복 실패", "input": {"days": 7, "quest_failures": 6}},
}
