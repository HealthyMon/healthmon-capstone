"""Deterministic, CPU-only HEALTHMON v2.2 rules.

This module accepts validated domain events, never authenticates their source and
never writes rewards. ``reward_candidates`` must be inserted into a unique,
transactional ledger by the caller. Replaying edited events can change ordinary
stats; it must never replace the existing reward ledger or claw back a level.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    KST = ZoneInfo("Asia/Seoul")
except ZoneInfoNotFoundError:  # Windows without a system tz database; current KST.
    KST = timezone(timedelta(hours=9), "Asia/Seoul")

RULE_VERSION = "healthmon.v2.2"
DEFAULT_GOALS = {
    "walking": {"target": 6000, "unit": "steps", "body_part": "lower"},
    "running": {"target": 30, "unit": "minutes", "body_part": "lower"},
    "squat": {"target": 50, "unit": "repetitions", "body_part": "lower"},
    "lunge": {"target": 40, "unit": "repetitions", "body_part": "lower"},
    "pushup": {"target": 30, "unit": "repetitions", "body_part": "upper"},
    "dumbbell": {"target": 30, "unit": "repetitions", "body_part": "upper"},
}
_EXERCISE_ALIASES = {
    "walk": "walking", "걷기": "walking", "run": "running", "달리기": "running",
    "squats": "squat", "스쿼트": "squat", "lunges": "lunge", "런지": "lunge",
    "push_up": "pushup", "pushups": "pushup", "push-up": "pushup", "푸시업": "pushup",
    "dumbbells": "dumbbell", "덤벨": "dumbbell",
}
_UNIT_ALIASES = {
    "step": "steps", "보": "steps", "count": "repetitions", "reps": "repetitions",
    "rep": "repetitions", "회": "repetitions", "minute": "minutes", "min": "minutes", "분": "minutes",
}
_BODY_ALIASES = {"upper_body": "upper", "lower_body": "lower", "full_body": "full", "whole": "full"}
_MEAL_ALIASES = {"아침": "breakfast", "점심": "lunch", "저녁": "dinner", "간식": "snack"}
_REFERENCE_KCAL = {"breakfast": 450, "lunch": 650, "dinner": 650}
_AXES = ("upper_body", "lower_body", "nutrition", "energy_balance")


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _nonnegative(value: Any) -> float | None:
    value = _number(value)
    return value if value is not None and value >= 0 else None


def _field(payload: dict, *names: str):
    for name in names:
        if name in payload:
            return payload[name]
    return None


def _clamp(value, low, high):
    return min(high, max(low, value))


def _instant(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("A timezone-aware timestamp is required")
    return value.astimezone(timezone.utc)


def _day(value: datetime | str) -> date:
    return _instant(value).astimezone(KST).date()


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time.min, KST).astimezone(timezone.utc)


def required_exp(level: int) -> int:
    if isinstance(level, bool) or not isinstance(level, int) or level < 1:
        raise ValueError("level must be a positive integer")
    x = level - 1
    return 10 * ((100 + 10 * x + x * x + 5) // 10)


def initial_state() -> dict:
    return {
        "rule_version": RULE_VERSION, "level": 1, "current_exp": 0,
        "required_exp": 100, "total_exp": 0, "coin": 0,
        "upper_body": 50, "lower_body": 50, "nutrition": 50, "energy_balance": 0,
        "activity": 50, "affinity": 50, "initiative": 50,
        "evolution_target_stage": 0, "published_model_stage": 0,
        "asset_status": "none", "model_reference": None,
    }


def exp_progress(total_exp: int) -> dict:
    """Project a nonnegative *persisted ledger* total into level and carryover."""
    if isinstance(total_exp, bool) or not isinstance(total_exp, int) or total_exp < 0:
        raise ValueError("total_exp must be a nonnegative integer")
    remaining, level = total_exp, 1
    while remaining >= required_exp(level):
        remaining -= required_exp(level)
        level += 1
    return {"total_exp": total_exp, "level": level, "current_exp": remaining,
            "required_exp": required_exp(level), "evolution_target_stage": min(3, sum(level >= x for x in (10, 20, 30)))}


def eligibility(occurred_at: datetime | str, received_at: datetime | str) -> str:
    occurred, received = _instant(occurred_at), _instant(received_at)
    if occurred > received:
        return "future"
    return "eligible" if received - occurred <= timedelta(hours=24) else "archive_only"


def workout_delta(payload: dict, upper=50, lower=50) -> dict:
    """Evaluate one normalized workout; the caller applies *daily net* caps.

    Known exercise defaults describe units/body only; target is always a saved
    goal snapshot. No time-to-repetitions, calorie, heart-rate or distance guess.
    """
    result = {"upper_body": 0, "lower_body": 0, "achievement_rate": None,
              "actual_workout": False, "confirmed_nonperformance": False,
              "evaluation_status": "recorded_unscored", "reason": "insufficient_measurement"}
    exercise = _field(payload, "exercise_type", "workout_type", "type")
    exercise = _EXERCISE_ALIASES.get(exercise, exercise)
    unit = _field(payload, "unit", "representative_unit")
    unit = _UNIT_ALIASES.get(unit, unit)
    body = _field(payload, "body_part", "category")
    body = _BODY_ALIASES.get(body, body)
    actual, target = _nonnegative(payload.get("actual")), _number(payload.get("target"))
    if actual is None or target is None or target <= 0 or unit not in {"steps", "minutes", "repetitions"}:
        return result
    default = DEFAULT_GOALS.get(exercise)
    if default:
        if unit != default["unit"]:
            result["reason"] = "unit_mismatch"
            return result
        body = body or default["body_part"]
    elif not payload.get("goal_confirmed_before_start"):
        result["reason"] = "unsupported_goal"
        return result
    if body not in {"upper", "lower", "full"}:
        result["reason"] = "missing_body_part"
        return result
    rate = actual / target * 100
    if not math.isfinite(rate):
        return result
    missed = actual == 0 and payload.get("confirmed_nonperformance") is True
    score = (-2 if missed else 0) if actual == 0 else next(
        delta for threshold, delta in ((120, 3), (100, 2), (70, 1), (40, 0), (0, -1))
        if rate >= threshold or math.isclose(rate, threshold, rel_tol=1e-12, abs_tol=0))
    result.update(achievement_rate=rate, actual_workout=actual > 0,
                  confirmed_nonperformance=missed, body_part=body,
                  evaluation_status="evaluated", reason="confirmed_nonperformance" if missed else "achievement", score=score)
    result.update(_body_distribution(score, body, upper, lower))
    return result


def _body_distribution(score, body, upper, lower):
    """Distribute a game score, independent of any retained health measurement."""
    result = {"upper_body": 0, "lower_body": 0}
    if body in {"upper", "lower"}:
        result["upper_body" if body == "upper" else "lower_body"] = score
    elif body == "full":
        # The odd remainder goes to upper when the compared stats are equal.
        weak = "upper_body" if upper <= lower else "lower_body"
        strong = "upper_body" if upper >= lower else "lower_body"
        if score == 3:
            result.update(upper_body=1, lower_body=1)
            result[weak] += 1
        elif score == 2:
            result.update(upper_body=1, lower_body=1)
        elif score == 1:
            result[weak] = 1
        elif score == -1:
            result[strong] = -1
        elif score == -2:
            result.update(upper_body=-1, lower_body=-1)
    return result


def _ordered_day_events(records, anchors, anchor_identities):
    """Merge game contributions in the exact occurred_at,event_id order.

    Retained aggregates store random game keys, never source identifiers. The
    erased source's minimal anti-resurrection tombstone supplies its sort ID at
    replay time; even newly arriving equal-time events therefore sort exactly.
    """
    merged = list(records)
    for anchor in anchors:
        if anchor["key"] not in anchor_identities:
            raise ValueError("Retained game contribution is missing its erasure tombstone")
        merged.append({"kind": "retained_body", "anchor": anchor, "occurred_at": _instant(anchor["at"]),
                       "event_id": anchor_identities[anchor["key"]]})
    merged.sort(key=lambda event: (_instant(event["occurred_at"]), str(event["event_id"])))
    return [(event, rank) for rank, event in enumerate(merged)]


def _meal_identity(payload: dict) -> tuple[bool, str | None]:
    name = _field(payload, "food_name", "name")
    quantity = _nonnegative(_field(payload, "grams", "quantity_g", "portion_g"))
    confirmed = payload.get("confirmed") is True and (
        payload.get("quantity_confirmed") is True or (quantity is not None and quantity > 0))
    water = payload.get("water_only") is True or (isinstance(name, str) and name.strip().casefold() in {"water", "물", "생수"})
    meal = _field(payload, "meal_type", "meal_slot")
    return bool(confirmed and isinstance(name, str) and name.strip() and not water), _MEAL_ALIASES.get(meal, meal)


def meal_delta(payload: dict) -> dict:
    """Evaluate one confirmed breakfast/lunch/dinner bundle, with unknowns kept."""
    valid, meal = _meal_identity(payload)
    result = {"nutrition": 0, "energy_balance": 0, "evaluation_status": "recorded_unscored",
              "nutrition_status": "unknown", "energy_balance_status": "unknown",
              "reward_eligible": valid, "meal_type": meal, "macro_energy": None,
              "confirmed_kcal": None, "conditions_met": None, "reason": "unconfirmed_meal"}
    if not valid:
        return result
    if meal == "snack":
        result["reason"] = "snack_record_only"
        return result
    if meal not in _REFERENCE_KCAL:
        result["reason"] = "unknown_meal_slot"
        return result
    carbs = _nonnegative(_field(payload, "carbohydrate_g", "carbs_g", "carbohydrates_g"))
    protein = _nonnegative(payload.get("protein_g"))
    fat = _nonnegative(payload.get("fat_g"))
    produce = _nonnegative(_field(payload, "vegetable_fruit_g", "vegetables_fruit_g", "produce_g"))
    energy = None if any(x is None for x in (carbs, protein, fat)) else 4 * carbs + 4 * protein + 9 * fat
    if energy is not None and not math.isfinite(energy):
        energy = None
    result["macro_energy"] = energy
    if energy is not None and energy >= 50 and produce is not None:
        # Decimal avoids classifying an exact 45% input as 44.99999999999999%.
        c, p, f = (Decimal(str(x)) for x in (carbs, protein, fat))
        e = 4 * c + 4 * p + 9 * f
        epsilon = e * Decimal("1e-12")
        count = sum((Decimal(".45") * e - epsilon <= 4 * c <= Decimal(".65") * e + epsilon,
                     Decimal(".10") * e - epsilon <= 4 * p <= Decimal(".35") * e + epsilon,
                     Decimal(".15") * e - epsilon <= 9 * f <= Decimal(".35") * e + epsilon,
                     produce >= 80))
        result.update(nutrition=count - 2, conditions_met=count, nutrition_status="evaluated")
    kcal_raw = payload.get("kcal")
    kcal = _nonnegative(kcal_raw) if kcal_raw is not None else energy
    discrepancy = payload.get("kcal_requires_reconfirmation") is True or (
        kcal_raw is not None and kcal is not None and energy is not None and energy > 0
        and abs(Decimal(str(kcal)) - Decimal(str(energy))) > Decimal(".200000000001") * Decimal(str(energy)))
    if discrepancy and payload.get("kcal_reconfirmed") is not True:
        result.update(energy_balance_status="reconfirmation_required", reason="kcal_macro_discrepancy")
    elif kcal is not None and 50 <= kcal <= 3000:
        ratio = Decimal(str(kcal)) / Decimal(_REFERENCE_KCAL[meal])
        # Suppress binary floating-point residue at exact decimal boundaries.
        ratio = ratio.quantize(Decimal(".000000000001"))
        delta = (-3 if ratio < Decimal(".70") else -2 if ratio < Decimal(".90") else
                 0 if ratio <= Decimal("1.10") else 2 if ratio <= Decimal("1.30") else 3)
        result.update(energy_balance=delta, energy_balance_status="evaluated", confirmed_kcal=kcal)
    if result["nutrition_status"] == "evaluated" or result["energy_balance_status"] == "evaluated":
        result["evaluation_status"] = "evaluated"
        if result["reason"] != "kcal_macro_discrepancy":
            result["reason"] = "confirmed_bundle"
    elif result["reason"] != "kcal_macro_discrepancy":
        result["reason"] = "insufficient_nutrition"
    return result


def personality_delta(summary: dict) -> dict:
    """Apply the first matching weekly condition for each of the three axes."""
    days = summary.get("workout_days", 0)
    average = summary.get("workout_average")
    high = summary.get("high_motivation_days", 0)
    low = summary.get("low_motivation_days", 0)
    missed = summary.get("confirmed_nonperformance_days", 0)
    rejected = summary.get("valid_rejections", 0)
    if days >= 5 and average is not None and average >= 100 and high >= 2:
        activity = 3
    elif days >= 4 and average is not None and average >= 70:
        activity = 2
    elif days >= 3:
        activity = 1
    elif days == 2:
        activity = 0
    elif days <= 1 and missed >= 2 and low >= 2 and rejected >= 2:
        activity = -2
    elif days <= 1 and missed >= 2:
        activity = -1
    else:
        activity = 0
    negatives, negative_days = summary.get("character_negative_count", 0), summary.get("character_negative_days", 0)
    chat_days = summary.get("conversation_days", 0)
    if negatives >= 3 and negative_days >= 2:
        affinity = -2
    elif negatives >= 1:
        affinity = 0
    elif chat_days >= 6 and summary.get("character_positive_count", 0) >= 3 and summary.get("actual_memory_mentions", 0) >= 1:
        affinity = 3
    elif chat_days >= 4:
        affinity = 2
    elif chat_days >= 2:
        affinity = 1
    elif chat_days <= 1 and summary.get("life_record_days", 0) >= 5:
        affinity = -1
    else:
        affinity = 0
    opportunities, accepted, completed = (summary.get(key, 0) for key in ("proposals", "accepted", "completed"))
    if not 0 <= completed <= accepted <= opportunities:
        raise ValueError("Proposal summary must satisfy 0 <= C <= A <= O")
    ratio = (accepted + 2 * completed) / (3 * opportunities) if opportunities else None
    initiative = (3 if ratio >= .8 else 2 if ratio >= .6 else 0 if ratio >= .4 else
                  -1 if ratio >= .2 else -2) if ratio is not None else 0
    if summary.get("meal_days", 0) >= 5 and days >= 2:
        initiative += 1
    return {"activity": activity, "affinity": affinity, "initiative": _clamp(initiative, -3, 3),
            "proposal_ratio": ratio}


def personality_bands(value: float) -> dict:
    value = _number(value)
    if value is None or not 0 <= value <= 100:
        raise ValueError("A personality score in 0..100 is required")
    return {"display": "low" if value < 35 else "middle" if value < 66 else "high",
            "expression": 0 if value < 25 else 1 if value < 40 else 2 if value < 60 else 3 if value < 75 else 4}


def proposal_policy(initiative: float) -> dict:
    value = _number(initiative)
    if value is None or not 0 <= value <= 100:
        raise ValueError("initiative must be in 0..100")
    return ({"period": "week", "limit": 3, "minimum_hours": 24} if value < 40 else
            {"period": "day", "limit": 1, "minimum_hours": 8} if value < 70 else
            {"period": "day", "limit": 2, "minimum_hours": 4})


def evolution_profile(state: dict, previous: dict | None = None) -> dict:
    upper, lower, nutrition, eb = (state[key] for key in ("upper_body", "lower_body", "nutrition", "energy_balance"))
    strength, difference = (upper + lower) / 2, upper - lower
    if eb >= 30 and strength < 45:
        appearance = "adipose"
    elif eb <= -30 and strength >= 65:
        appearance = "lean_athletic"
    elif eb <= -30:
        appearance = "lean"
    elif eb >= 30 and strength >= 65:
        appearance = "bulky_athletic"
    elif eb >= 30:
        appearance = "rounded_general"
    elif strength >= 65 and difference >= 15:
        appearance = "upper_developed"
    elif strength >= 65 and difference <= -15:
        appearance = "lower_developed"
    elif strength >= 65 and nutrition >= 60:
        appearance = "balanced_athletic"
    elif strength >= 65:
        appearance = "developed_general"
    elif strength >= 45:
        appearance = "ordinary"
    else:
        appearance = "undertrained"
    previous_strength = None
    if previous:
        previous_strength = _number(_field(previous, "strength", "S"))
        if previous_strength is None and all(_number(previous.get(k)) is not None for k in ("upper_body", "lower_body")):
            previous_strength = (previous["upper_body"] + previous["lower_body"]) / 2
    change = None if previous_strength is None else strength - previous_strength
    old_appearance = _field(previous or {}, "appearance", "body_type", "final_body_type")
    stage = min(3, sum(state["level"] >= x for x in (10, 20, 30)))
    return {"rule_version": RULE_VERSION, "stage": stage, "strength": strength, "difference": difference,
            "strength_change": change, "progress": None if change is None else "improved" if change >= 15 else "declined" if change <= -15 else "maintained",
            "body_balance": "upper_dominant" if difference >= 15 else "lower_dominant" if difference <= -15 else "balanced",
            "nutrition_condition": "good" if nutrition >= 60 else "ordinary" if nutrition >= 40 else "insufficient",
            "energy_condition": "surplus" if eb >= 30 else "deficit" if eb <= -30 else "neutral",
            "appearance": appearance,
            "recovery": bool(old_appearance in {"adipose", "rounded_general"} and change is not None and change >= 15 and eb < 30),
            "generation_required": stage > state.get("published_model_stage", 0)}


def _classification(payload: dict) -> dict | None:
    value = payload.get("classification")
    if not isinstance(value, dict):
        return None
    confidence = _number(value.get("confidence"))
    if confidence is None or not .60 <= confidence <= 1:
        return None
    domains = {"target": {"character", "proposal", "workout", "exercise", "meal", "food", "other"},
               "sentiment": {"positive", "negative", "neutral"},
               "motivation": {"high", "low", "neutral", "unknown", "none"},
               "character_affection": {"positive", "negative", "neutral", "unknown", "none"},
               "acceptance": {"accepted", "rejected", "accept", "reject", "none", "unknown", "neutral"}}
    if any(value.get(key) not in allowed for key, allowed in domains.items()):
        return None
    return value


def _meal_bundle(events: list[dict]) -> dict:
    """Aggregate items without inventing unknown nutrient values."""
    payload = {"food_name": " + ".join(str(_field(e["payload"], "food_name", "name")) for e in events),
               "confirmed": True, "quantity_confirmed": True, "meal_type": _meal_identity(events[0]["payload"])[1]}
    aliases = {"carbohydrate_g": ("carbohydrate_g", "carbs_g", "carbohydrates_g"),
               "protein_g": ("protein_g",), "fat_g": ("fat_g",),
               "vegetable_fruit_g": ("vegetable_fruit_g", "vegetables_fruit_g", "produce_g")}
    for field, names in aliases.items():
        values = [_nonnegative(_field(event["payload"], *names)) for event in events]
        payload[field] = None if any(v is None for v in values) else sum(values)
    kcal_values, all_reconfirmed = [], True
    for event in events:
        item = event["payload"]
        item_kcal = _nonnegative(item.get("kcal"))
        if item.get("kcal") is None:
            macros = [_nonnegative(_field(item, *aliases[key])) for key in ("carbohydrate_g", "protein_g", "fat_g")]
            item_kcal = None if any(v is None for v in macros) else 4 * macros[0] + 4 * macros[1] + 9 * macros[2]
        kcal_values.append(item_kcal)
        # A discrepant item cannot be hidden by another item's opposite error.
        if meal_delta(item)["energy_balance_status"] == "reconfirmation_required":
            all_reconfirmed = False
    payload["kcal"] = None if any(v is None for v in kcal_values) else sum(kcal_values)
    payload["kcal_reconfirmed"] = all_reconfirmed
    payload["kcal_requires_reconfirmation"] = not all_reconfirmed
    if any(v is None for v in kcal_values) and any(e["payload"].get("kcal") is not None for e in events):
        payload["kcal"] = float("nan")  # Invalid explicit input may not fall back to macros.
    return payload


def _proposal_counts(proposals: list[dict], week_start: date, week_end: date) -> tuple[int, int, int, int]:
    opportunities = accepted = completed = rejected = 0
    seen = set()
    for proposal in proposals:
        ident = proposal.get("proposal_id")
        if ident is not None and ident in seen:
            continue
        seen.add(ident)
        if (proposal.get("valid", True) is not True or proposal.get("shown", proposal.get("visible", False)) is not True
                or proposal.get("cancelled") or proposal.get("rest") or proposal.get("unavailable")
                or proposal.get("acceptance_supported", True) is not True
                or proposal.get("status") in {"cancelled", "rest", "unavailable", "hidden"}):
            continue
        try:
            deadline = _instant(_field(proposal, "deadline", "expires_at", "due_at"))
            created = _instant(proposal["created_at"])
        except (ValueError, TypeError, KeyError):
            continue
        if not _midnight(week_start) <= deadline < _midnight(week_end) or deadline - created != timedelta(hours=24):
            continue
        opportunities += 1
        accept = proposal.get("accepted_at")
        if accept is not None:
            try:
                accept = _instant(accept)
                accepted_valid = created <= accept <= deadline
            except (ValueError, TypeError):
                accepted_valid = False
            if accepted_valid:
                accepted += 1
                complete = proposal.get("completed_at")
                if complete is not None and proposal.get("completion_verified") is True:
                    try:
                        completed += int(accept <= _instant(complete) <= deadline)
                    except (ValueError, TypeError):
                        pass
        if proposal.get("rejected_at") is not None:
            try:
                rejected += int(created <= _instant(proposal["rejected_at"]) <= deadline)
            except (ValueError, TypeError):
                pass
    return opportunities, accepted, completed, rejected


def replay(events: list[dict], now: datetime | str, proposals: list[dict] | None = None,
           retained: dict | None = None) -> dict:
    """Rebuild ordinary stats and base EXP candidates from immutable event times.

    The event store resolves revisions/deletions and preserves first received_at.
    Events whose first receipt is after ``now`` are omitted. Expired, invalid and
    future events retain an evaluation entry but contribute no score or reward.
    Completed weeks are rebuilt once, including qualifying Monday late arrivals;
    no mutation or repeated weekly addition occurs in this pure projection.
    """
    now = _instant(now)
    today, state = _day(now), initial_state()
    proposals = proposals or []
    retained = retained or {}
    retained_daily, retained_weekly = retained.get("daily", {}), retained.get("weekly", {})
    evaluations: dict[str, dict] = {}
    by_day: dict[date, list[dict]] = defaultdict(list)
    unique_events: dict[str, dict] = {}
    anchor_identities = {}
    for event in events:
        ident = str(event["event_id"])
        if ident in unique_events:
            if unique_events[ident] != event:
                raise ValueError("Conflicting event_id in replay input")
            continue
        unique_events[ident] = event
        if event.get("valid") is False and event.get("payload", {}).get("_game_anchor_key"):
            anchor_identities[event["payload"]["_game_anchor_key"]] = ident
        occurred, received = _instant(event["occurred_at"]), _instant(event["received_at"])
        status = eligibility(occurred, received)
        if received > now or occurred > now:
            status = "future"
        if event.get("valid", True) is not True or event.get("deleted"):
            status = "invalid"
        evaluations[ident] = {"evaluation_status": status}
        if status == "eligible":
            by_day[_day(occurred)].append(event)
    # Privacy offsets retain game scores without the erased health/chat inputs.
    for period in (*retained_daily, *retained_weekly):
        period_day = date.fromisoformat(period)
        if period_day <= today:
            by_day.setdefault(period_day, [])
    daily, weekly, candidates = [], [], []
    if not by_day:
        return {"state": state, "daily": daily, "weekly": weekly, "evaluations": evaluations,
                "reward_candidates": candidates, "trend": {"status": "unknown", "recent_average": None, "previous_average": None}}

    def reward(day, slot, amount, event, reason):
        candidates.append({"reward_key": f"base:{day.isoformat()}:{slot}", "exp": amount, "coin": 0,
                           "day": day.isoformat(), "event_id": str(event["event_id"]), "reason": reason})

    day = min(by_day)
    while day <= today:
        if day.weekday() == 0:
            eb = state["energy_balance"]
            state["energy_balance"] = max(0, eb - 2) if eb > 0 else min(0, eb + 2)
            start, end = day - timedelta(days=7), day
            week_days = [entry for entry in daily if start <= date.fromisoformat(entry["date"]) < end]
            week_events = [event for d, records in by_day.items() if start <= d < end for event in records
                           if _instant(event["received_at"]) < _midnight(end + timedelta(days=1))]
            classifications = [(event, _classification(event["payload"])) for event in week_events if event["kind"] == "chat"]
            classifications = [(event, cls) for event, cls in classifications if cls is not None
                               and event["payload"].get("normal", True) is True
                               and isinstance(event["payload"].get("text"), str) and event["payload"]["text"].strip()]
            negatives = [(e, c) for e, c in classifications if c["target"] == "character" and c["character_affection"] == "negative"]
            actual_days = [entry for entry in week_days if entry["workout_day"]]
            o, a, c, rejections = _proposal_counts(proposals, start, end)
            summary = {
                "workout_days": len(actual_days),
                "workout_average": sum(e["workout_average"] for e in actual_days) / len(actual_days) if actual_days else None,
                "high_motivation_days": len({_day(e["occurred_at"]) for e, cls in classifications if cls["target"] in {"workout", "exercise"} and cls["motivation"] == "high"}),
                "low_motivation_days": len({_day(e["occurred_at"]) for e, cls in classifications if cls["target"] in {"workout", "exercise"} and cls["motivation"] == "low"}),
                "confirmed_nonperformance_days": sum(e["confirmed_nonperformance_day"] for e in week_days),
                "valid_rejections": rejections,
                "character_negative_count": len(negatives),
                "character_negative_days": len({_day(e["occurred_at"]) for e, cls in negatives}),
                "character_positive_count": sum(cls["target"] == "character" and cls["character_affection"] == "positive" for e, cls in classifications),
                "conversation_days": len({_day(e["occurred_at"]) for e, cls in classifications}),
                "actual_memory_mentions": sum(e["payload"].get("actual_memory_reference") is True for e, cls in classifications),
                "life_record_days": sum(e["life_record_day"] for e in week_days),
                "meal_days": sum(e["meal_day"] for e in week_days), "proposals": o, "accepted": a, "completed": c,
            }
            deltas = personality_delta(summary)
            offsets = retained_weekly.get(start.isoformat(), {})
            for axis in ("activity", "affinity", "initiative"):
                deltas[axis] = _clamp(deltas[axis] + offsets.get(axis, 0), -3 if axis == "initiative" else -2, 3)
            before = {key: state[key] for key in ("activity", "affinity", "initiative")}
            for key in before:
                state[key] = _clamp(state[key] + deltas[key], 0, 100)
            weekly.append({"week_start": start.isoformat(), "week_end": end.isoformat(), "summary": summary,
                           "deltas": deltas, "before": before, "after": {key: state[key] for key in before},
                           "provisional_until": _midnight(end + timedelta(days=1)).isoformat(),
                           "finalized": now >= _midnight(end + timedelta(days=1))})
        records = sorted(by_day.get(day, []), key=lambda e: (_instant(e["occurred_at"]), str(e["event_id"])))
        body_anchors = retained_daily.get(day.isoformat(), {}).get("body_events", [])
        before = {axis: state[axis] for axis in _AXES}
        raw = {axis: 0 for axis in _AXES}
        preliminary = {str(e["event_id"]): workout_delta(e["payload"]) for e in records if e["kind"] == "workout"}
        performed_parts = set()
        for delta in preliminary.values():
            if delta["actual_workout"]:
                performed_parts.update(("upper", "lower") if delta["body_part"] == "full" else (delta["body_part"],))
        for anchor in body_anchors:
            if anchor.get("performed"):
                performed_parts.update(("upper", "lower") if anchor["body_part"] == "full" else (anchor["body_part"],))
        rates, actual, chats, meal_records = [], [], [], []
        nonperformance = False
        for event, rank in _ordered_day_events(records, body_anchors, anchor_identities):
            if event["kind"] == "retained_body":
                anchor = event["anchor"]
                upper = _clamp(before["upper_body"] + _clamp(raw["upper_body"], -2, 3), 0, 100)
                lower = _clamp(before["lower_body"] + _clamp(raw["lower_body"], -2, 3), 0, 100)
                delta = _body_distribution(anchor["score"], anchor["body_part"], upper, lower)
                if anchor.get("missed"):
                    if "upper" in performed_parts:
                        delta["upper_body"] = 0
                    if "lower" in performed_parts:
                        delta["lower_body"] = 0
                raw["upper_body"] += delta["upper_body"]
                raw["lower_body"] += delta["lower_body"]
                continue
            ident, payload = str(event["event_id"]), event["payload"]
            if event["kind"] == "workout":
                upper = _clamp(before["upper_body"] + _clamp(raw["upper_body"], -2, 3), 0, 100)
                lower = _clamp(before["lower_body"] + _clamp(raw["lower_body"], -2, 3), 0, 100)
                delta = workout_delta(payload, upper, lower)
                delta["game_order_rank"] = rank
                if delta["confirmed_nonperformance"]:
                    if "upper" in performed_parts:
                        delta["upper_body"] = 0
                    if "lower" in performed_parts:
                        delta["lower_body"] = 0
                    nonperformance |= bool(delta["upper_body"] or delta["lower_body"])
                raw["upper_body"] += delta["upper_body"]
                raw["lower_body"] += delta["lower_body"]
                if delta["actual_workout"]:
                    rates.append(min(150, delta["achievement_rate"]))
                    actual.append(event)
                evaluations[ident] = delta
            elif event["kind"] == "meal":
                delta = meal_delta(payload)
                evaluations[ident] = delta
                if delta["reward_eligible"]:
                    meal_records.append(event)
            elif event["kind"] == "chat":
                normal = payload.get("normal", True) is True and isinstance(payload.get("text"), str) and bool(payload["text"].strip())
                evaluations[ident] = {"evaluation_status": "evaluated" if normal else "recorded_unscored",
                                      "personality_eligible": _classification(payload) is not None,
                                      "reward_eligible": normal}
                if normal:
                    chats.append(event)
            else:
                evaluations[ident] = {"evaluation_status": "recorded_unscored", "reason": "unsupported_event_kind"}
        bundles = defaultdict(list)
        for event in meal_records:
            meal = _meal_identity(event["payload"])[1]
            if meal in _REFERENCE_KCAL:
                bundles[meal].append(event)
        bundle_evaluations = {}
        for meal, items in bundles.items():
            delta = meal_delta(_meal_bundle(items))
            raw["nutrition"] += delta["nutrition"]
            raw["energy_balance"] += delta["energy_balance"]
            bundle_evaluations[meal] = delta
            for item in items:
                evaluations[str(item["event_id"])]["bundle_evaluation"] = delta
        offsets = retained_daily.get(day.isoformat(), {})
        for axis in _AXES:
            raw[axis] += offsets.get(axis, 0)
        caps = {"upper_body": (-2, 3), "lower_body": (-2, 3), "nutrition": (-3, 3), "energy_balance": (-4, 4)}
        capped = {axis: _clamp(raw[axis], *caps[axis]) for axis in _AXES}
        for axis in _AXES:
            state[axis] = _clamp(before[axis] + capped[axis], -100 if axis == "energy_balance" else 0, 100)
        # Breakfast/lunch/dinner are one record bundle each. Snacks may fill the
        # remaining three meal EXP slots, never create extra daily rewards.
        meal_rewards = []
        seen_bundles = set()
        for event in meal_records:
            meal = _meal_identity(event["payload"])[1]
            if meal in _REFERENCE_KCAL and meal not in seen_bundles:
                meal_rewards.append(event)
                seen_bundles.add(meal)
            elif meal == "snack":
                meal_rewards.append(event)
        meal_rewards = meal_rewards[:3]
        if actual:
            reward(day, "workout", 20, actual[0], "first_actual_workout")
            achieved = [e for e in actual if preliminary[str(e["event_id"])]["achievement_rate"] >= 70]
            if achieved:
                reward(day, "workout70", 10, achieved[0], "first_workout_at_least_70")
        for index, event in enumerate(meal_rewards, 1):
            reward(day, f"meal:{index}", 15, event, "confirmed_meal_record")
        if chats:
            reward(day, "chat", 10, chats[0], "first_normal_conversation")
        life = sorted(actual + meal_rewards + chats, key=lambda e: (_instant(e["occurred_at"]), str(e["event_id"])))
        if life:
            reward(day, "life", 5, life[0], "first_valid_life_event")
        daily.append({"date": day.isoformat(), "before": before, "raw_deltas": raw, "capped_deltas": capped,
                      "retained_deltas": {axis: offsets.get(axis, 0) for axis in _AXES},
                      "retained_body_event_count": len(body_anchors),
                      "after": {axis: state[axis] for axis in _AXES},
                      "applied_deltas": {axis: state[axis] - before[axis] for axis in _AXES}, "workout_day": bool(actual),
                      "workout_average": sum(rates) / len(rates) if rates else None,
                      "confirmed_nonperformance_day": nonperformance, "meal_day": bool(bundles),
                      "life_record_day": bool(actual or meal_records), "meal_bundles": bundle_evaluations,
                      "valid_workouts": len(actual), "confirmed_meal_count": len(meal_rewards), "normal_chat_count": len(chats)})
        day += timedelta(days=1)
    state.update(exp_progress(sum(candidate["exp"] for candidate in candidates)))
    recent = [entry for entry in daily if today - timedelta(days=6) <= date.fromisoformat(entry["date"]) <= today and entry["workout_day"]]
    previous = [entry for entry in daily if today - timedelta(days=13) <= date.fromisoformat(entry["date"]) < today - timedelta(days=6) and entry["workout_day"]]
    def average_delta(entries):
        return sum((entry["applied_deltas"]["upper_body"] + entry["applied_deltas"]["lower_body"]) / 2 for entry in entries) / len(entries) if len(entries) >= 2 else None
    recent_avg, previous_avg = average_delta(recent), average_delta(previous)
    change = None if recent_avg is None or previous_avg is None else recent_avg - previous_avg
    trend = {"status": "unknown" if change is None else "improved" if change >= .5 else "declined" if change <= -.5 else "maintained",
             "recent_average": recent_avg, "previous_average": previous_avg, "difference": change}
    return {"state": state, "daily": daily, "weekly": weekly, "evaluations": evaluations,
            "reward_candidates": candidates, "trend": trend}
