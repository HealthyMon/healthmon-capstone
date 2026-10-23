"""Pure deterministic growth replay; never reads or writes user databases.

All balance numbers live in config/persona_rules.json. A caller must authenticate
real backend/sensor producers before supplying events. ``simulation`` is an
explicit synthetic provenance for the isolated development lab, never evidence
that an activity really occurred. Replay requires the full stream from Day 0;
passing a previous final personality plus the same events would double count.

Payloads: exercise {exercise_type, steps?/minutes?/duration_minutes?}; food
{food_name (or name), food_group, fast_food?, balanced?}; conversation
{text, meaningful?, asks_character_state?, topic?, negative?, greeting?}.
Quest events require catalog quest_id and unique quest_instance_id. Accepted
must precede progress/completion/failure. Progress/completion additionally need
evidence_event_ids referencing earlier verified, accepted-after records; catalog
goals are checked independently of caller supplied progress. Cancel/decline is
represented by outcome='cancelled'/'declined', never failure. Inactivity is
derived from actual local dates; inactivity_period {anchor_only:true} establishes
an empty simulation's Day 0 and cannot request arbitrary negative deltas.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from difflib import SequenceMatcher
import json
import math
from pathlib import Path
import re
from typing import Any, Literal
import unicodedata
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

AXES = ("curiosity", "affection", "activity", "confidence")
RULES_PATH = Path(__file__).resolve().parents[1] / "config" / "persona_rules.json"
RULES = json.loads(RULES_PATH.read_text(encoding="utf-8"))
EventType = Literal["conversation", "positive_interaction", "exercise_recorded", "food_recorded",
                    "quest_proposed", "quest_accepted", "quest_progressed", "quest_completed",
                    "quest_failed", "inactivity_period"]


def _finite_tree(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Nonfinite payload values are forbidden")
    if isinstance(value, dict):
        for item in value.values():
            _finite_tree(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _finite_tree(item)
    return value


class GrowthEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=200)
    user_id: str = Field(min_length=1, max_length=200)
    character_id: str = Field(min_length=1, max_length=200)
    event_type: EventType
    occurred_at: datetime
    source: str = Field(min_length=1, max_length=80)
    verification_status: Literal["verified", "unverified", "rejected", "pending"]
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    payload: dict[str, Any]
    idempotency_key: str = Field(min_length=1, max_length=240)

    @field_validator("occurred_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must have a timezone")
        return value

    @field_validator("payload")
    @classmethod
    def finite_payload(cls, value: dict) -> dict:
        _finite_tree(value)
        for key in ("negative", "meaningful", "asks_character_state", "greeting", "fast_food", "balanced", "confirmed", "anchor_only", "together", "synthetic"):
            if key in value and not isinstance(value[key], bool):
                raise ValueError(f"payload.{key} must be a boolean")
        for key in ("text", "topic", "exercise_type", "food_name", "name", "food_group", "quest_id", "quest_instance_id"):
            if key in value and not isinstance(value[key], str):
                raise ValueError(f"payload.{key} must be a string")
        if "baseline_known" in value:
            baseline = value["baseline_known"]
            if not isinstance(baseline, dict) or set(baseline) - {"exercise", "food", "food_group"}:
                raise ValueError("baseline_known supports exercise, food and food_group lists only")
            if any(not isinstance(items, list) or len(items) > 180
                   or any(not isinstance(item, str) or not item.strip() or len(item) > 100 for item in items)
                   for items in baseline.values()):
                raise ValueError("baseline_known must contain bounded nonempty string lists")
        return value


def validate_personality(personality: dict | None = None) -> dict[str, float]:
    if personality is not None and not isinstance(personality, dict):
        raise ValueError("personality must be an object")
    supplied = personality or {}
    if set(supplied) - set(AXES):
        raise ValueError("Unknown personality axis")
    result = dict(RULES["initial"])
    for axis, value in supplied.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{axis} must be a finite number")
        if not RULES["limits"]["minimum"] <= value <= RULES["limits"]["maximum"]:
            raise ValueError(f"{axis} outside configured range")
        result[axis] = float(value)
    return result


def validate_short_term(state: dict | None = None) -> dict:
    values = dict(RULES["short_term_initial"])
    if state is not None:
        if not isinstance(state, dict):
            raise ValueError("short_term must be an object")
        if set(state) - set(values):
            raise ValueError("Unknown short term field")
        values.update(state)
    if not isinstance(values["mood"], str) or not values["mood"].strip():
        raise ValueError("mood must be a nonempty string")
    for key in ("energy", "recent_motivation", "recent_stress"):
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{key} must be finite")
        if not RULES["limits"]["minimum"] <= value <= RULES["limits"]["maximum"]:
            raise ValueError(f"{key} outside configured range")
        values[key] = float(value)
    return values


def stage_for(value: float, previous: str | None = None) -> str:
    if not math.isfinite(value) or not RULES["limits"]["minimum"] <= value <= RULES["limits"]["maximum"]:
        raise ValueError("Stage value outside configured range")
    spec = RULES["stages"]
    names, lower = spec["names"], spec["lower_bounds"]
    if previous is None:
        return names[max(i for i, threshold in enumerate(lower) if value >= threshold)]
    if previous not in names:
        raise ValueError("Unknown previous stage")
    index = names.index(previous)
    while index < len(names) - 1 and value >= lower[index + 1]:
        index += 1
    while index > 0 and value <= lower[index] - spec["hysteresis"] - spec["boundary_step"]:
        index -= 1
    return names[index]


def personality_stages(personality: dict, previous: dict | None = None) -> dict[str, str]:
    values = validate_personality(personality)
    return {axis: stage_for(values[axis], (previous or {}).get(axis)) for axis in AXES}


def _norm(value: Any) -> str:
    return re.sub(r"[\W_\d]+", "", unicodedata.normalize("NFKC", str(value)).casefold())


def is_verified(event: GrowthEvent | dict) -> bool:
    event = event if isinstance(event, GrowthEvent) else GrowthEvent.model_validate(event)
    return (event.verification_status == "verified"
            and event.source in RULES["verification"]["sources"]
            and event.confidence >= RULES["verification"]["minimum_confidence"])


def _round(value: float) -> float:
    # Numerical stability is precision handling, not a game balance parameter.
    return round(float(value), 8)


def _streak(dates: set[date], at: date) -> int:
    count = 0
    while at in dates:
        count += 1
        at -= timedelta(days=1)
    return count


def _canonical(event: GrowthEvent) -> str:
    body = event.model_dump(mode="json", exclude={"event_id", "idempotency_key"})
    body["occurred_at"] = event.occurred_at.astimezone(timezone.utc).isoformat()
    return json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _deduplicate(events: list[GrowthEvent], audit: list) -> list[GrowthEvent]:
    """Conflicting aliases reject the whole connected group, independent of order."""
    buckets: dict[tuple, list[int]] = defaultdict(list)
    for i, event in enumerate(events):
        buckets[("event_id", event.event_id)].append(i)
        buckets[("idempotency_key", event.idempotency_key)].append(i)
    canonical = [_canonical(event) for event in events]
    rejected: set[int] = set()
    for indexes in buckets.values():
        if len({canonical[i] for i in indexes}) > 1:
            rejected.update(indexes)
    while True:
        enlarged = set(rejected)
        for indexes in buckets.values():
            if rejected.intersection(indexes):
                enlarged.update(indexes)
        if enlarged == rejected:
            break
        rejected = enlarged
    seen_ids, seen_keys, clean = set(), set(), []
    for index, event in enumerate(events):
        status = "idempotency_conflict" if index in rejected else None
        if status is None and (event.event_id in seen_ids or event.idempotency_key in seen_keys):
            status = "duplicate"
        seen_ids.add(event.event_id)
        seen_keys.add(event.idempotency_key)
        if status:
            audit.append({"event_id": event.event_id, "status": status, "reason": "No effect"})
        else:
            clean.append(event)
    return clean


def replay_events(events: list[dict | GrowthEvent], now: datetime,
                  initial: dict | None = None, short_term: dict | None = None,
                  tz: str = "Asia/Seoul") -> dict:
    """Replay one user's full character history with rolling seven local-date caps."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must have a timezone")
    zone = ZoneInfo(tz)
    now = now.astimezone(zone)
    personality = validate_personality(initial)
    transient = validate_short_term(short_term)
    stages = personality_stages(personality)
    audit: list[dict] = []
    parsed = [event if isinstance(event, GrowthEvent) else GrowthEvent.model_validate(event) for event in events]
    if len({(event.user_id, event.character_id) for event in parsed}) > 1:
        raise ValueError("Replay accepts a single user/character stream")
    parsed.sort(key=lambda e: (e.occurred_at, e.event_id, e.idempotency_key, _canonical(e)))
    usable = []
    for event in parsed:
        if event.occurred_at > now:
            audit.append({"event_id": event.event_id, "status": "future_excluded", "reason": "After as_of"})
        else:
            usable.append(event)
    usable = _deduplicate(usable, audit)
    synthetic_stream = any(event.source == "simulation" for event in usable)
    verified_anchors = [event for event in usable if is_verified(event)]
    anchor = usable[0].occurred_at.astimezone(zone) if usable else now
    ledger: list[dict] = []
    activity_dates: dict[str, set[date]] = {key: set() for key in ("exercise", "interaction", "food")}
    seen_types: dict[str, set[str]] = defaultdict(set)
    interaction_texts: list[tuple[date, str]] = []
    interaction_affection: dict[date, float] = defaultdict(float)
    streak_claims: set[tuple] = set()
    food_history: list[tuple[date, str, bool, bool]] = []
    diversity_claims: list[date] = []
    processed: dict[str, GrowthEvent] = {}
    accepted: dict[str, tuple[GrowthEvent, dict]] = {}
    ended: set[str] = set()
    quest_progress: dict[str, float] = defaultdict(float)
    evidence_owner: dict[str, str] = {}
    progressed_evidence: dict[str, set[str]] = defaultdict(set)
    failures: list[tuple[date, str]] = []
    penalized_failures: set[str] = set()
    last_activity = verified_anchors[0].occurred_at.astimezone(zone).date() if verified_anchors else now.date()
    transient_at = anchor
    mood_at = anchor
    limits = RULES["limits"]
    event_spent: dict[tuple[str, str, bool], float] = defaultdict(float)

    def audit_event(event: GrowthEvent, status: str, reason: str = "") -> None:
        audit.append({"event_id": event.event_id, "occurred_at": event.occurred_at.isoformat(),
                      "event_type": event.event_type, "status": status, "reason": reason,
                      "synthetic": event.source == "simulation"})

    def decay(at: datetime) -> None:
        nonlocal transient_at
        seconds = max(0.0, (at - transient_at).total_seconds())
        factor = 0.5 ** (seconds / timedelta(hours=RULES["short_term"]["half_life_hours"]).total_seconds())
        for key in ("energy", "recent_motivation", "recent_stress"):
            baseline = RULES["short_term_initial"][key]
            transient[key] = _round(baseline + (transient[key] - baseline) * factor)
        if (at - mood_at).total_seconds() >= timedelta(hours=RULES["short_term"]["mood_duration_hours"]).total_seconds():
            transient["mood"] = RULES["short_term_initial"]["mood"]
        transient_at = at

    def affect(name: str, at: datetime) -> None:
        nonlocal mood_at
        for key, value in RULES["short_term"][name].items():
            if key == "mood":
                transient[key], mood_at = value, at
            else:
                transient[key] = _round(min(limits["maximum"], max(limits["minimum"], transient[key] + value)))

    def award(event: GrowthEvent, amounts: dict, code: str, reason: str,
              streak: bool = False, interaction: bool = False) -> None:
        day = event.occurred_at.astimezone(zone).date()
        window_start = day - timedelta(days=limits["window_days"] - 1)
        for axis, requested in amounts.items():
            if not requested:
                continue
            positive = requested > 0
            sign = 1 if positive else -1
            absolute = abs(requested)
            before = personality[axis]
            key = (event.event_id, axis, positive)
            candidate = absolute
            if not streak:
                candidate = min(candidate, max(0, limits["ordinary_event_axis"] - event_spent[key]))
            # Streak bonuses are excepted only from the ordinary-event cap.
            relevant = [row for row in ledger if window_start <= date.fromisoformat(row["local_date"]) <= day]
            matching = [row for row in relevant if row["axis"] == axis and row["final_delta"] * sign > 0]
            daily = sum(abs(row["final_delta"]) for row in matching if row["local_date"] == day.isoformat())
            weekly = sum(abs(row["final_delta"]) for row in matching)
            candidate = min(candidate,
                            max(0, limits["daily_positive" if positive else "daily_negative"] - daily),
                            max(0, limits["weekly_positive" if positive else "weekly_negative"] - weekly))
            if streak:
                prior_streak = sum(max(0, row["final_delta"]) for row in relevant if row["streak_bonus"] > 0)
                candidate = min(candidate, max(0, limits["weekly_streak_total"] - prior_streak))
            if interaction and axis == "affection" and positive:
                candidate = min(candidate, max(0, RULES["interaction"]["daily_affection_cap"] - interaction_affection[day]))
            candidate = min(candidate, limits["maximum"] - before if positive else before - limits["minimum"])
            final = _round(sign * max(0, candidate))
            personality[axis] = _round(before + final)
            stages[axis] = stage_for(personality[axis], stages[axis])
            if not streak:
                event_spent[key] = _round(event_spent[key] + abs(final))
            if interaction and axis == "affection" and positive:
                interaction_affection[day] = _round(interaction_affection[day] + final)
            ledger.append({"event_id": event.event_id, "occurred_at": event.occurred_at.isoformat(),
                           "local_date": day.isoformat(), "axis": axis, "before": before,
                           "raw_delta": 0.0 if streak else requested, "streak_bonus": requested if streak else 0.0,
                           "cap_adjustment": _round(final - requested), "final_delta": final, "after": personality[axis],
                           "reason_code": code, "reason": reason, "source": event.source,
                           "verification_status": event.verification_status,
                           "synthetic": event.source == "simulation" or (event.source == "derived_rule" and synthetic_stream)})

    def record_day(kind: str, event: GrowthEvent) -> None:
        day = event.occurred_at.astimezone(zone).date()
        activity_dates[kind].add(day)
        count = _streak(activity_dates[kind], day)
        streak_rules = RULES[{"exercise": "exercise", "food": "food", "interaction": "interaction"}[kind]]["streaks"]
        beginning = day - timedelta(days=count - 1)
        for threshold, amounts in streak_rules.items():
            claim = (kind, beginning, int(threshold))
            if count == int(threshold) and claim not in streak_claims:
                streak_claims.add(claim)
                award(event, amounts, f"{kind}_streak_{threshold}", f"{threshold}일 연속 {kind} 기록", streak=True)

    def quest_catalog_entry(event: GrowthEvent) -> dict | None:
        # Lazy import permits the style layer to reuse our stage helper.
        from src.persona_quests import catalog_by_id
        return catalog_by_id().get(event.payload.get("quest_id"))

    def process(event: GrowthEvent) -> None:
        nonlocal last_activity
        p, kind = event.payload, event.event_type
        at = event.occurred_at.astimezone(zone)
        day = at.date()
        decay(at)
        if not is_verified(event):
            audit_event(event, "blocked_unverified", "Verified status, trusted producer and confidence threshold required")
            return
        if kind == "inactivity_period":
            if (event.source == "simulation" and p.get("anchor_only") is True
                    and event.occurred_at == anchor and isinstance(p.get("baseline_known"), dict)):
                # Aggregate-input simulations can mark known types at Day 0
                # without inventing historical events or historical growth.
                for category, values in p["baseline_known"].items():
                    seen_types[category].update(_norm(value) for value in values
                                                if _norm(value) not in RULES["normalization"]["unknown_values"])
            audit_event(event, "anchor_only", "Inactivity is derived from the verified event calendar")
            return
        if kind in ("conversation", "positive_interaction"):
            text = _norm(p.get("text", ""))
            if not text:
                audit_event(event, "invalid_payload", "A nonempty interaction text is required")
                return
            recent = [old for old_day, old in interaction_texts
                      if (day - old_day).days < RULES["interaction"]["duplicate_window_days"]]
            if any(SequenceMatcher(None, text, old).ratio() >= RULES["interaction"]["near_duplicate_ratio"] for old in recent):
                audit_event(event, "repeated_interaction", "Normalized or near duplicate: no growth, mood, or streak effect")
                return
            interaction_texts.append((day, text))
            negative = p.get("negative") is True or any(word in text for word in RULES["normalization"]["negative_markers"])
            if negative:
                affect("negative", at)
                audit_event(event, "transient_only", "Negative dialogue affects short term stress only")
                return
            greeting = p.get("greeting") is True or text in RULES["normalization"]["greetings"]
            if greeting:
                if "greeting" not in seen_types["interaction"]:
                    award(event, RULES["interaction"]["greeting"], "first_greeting", "최초 유효 인사", interaction=True)
                    seen_types["interaction"].add("greeting")
                else:
                    audit_event(event, "repeated_greeting", "Greeting variants cannot farm growth or streaks")
                    return
            elif p.get("meaningful") is True or kind == "positive_interaction":
                award(event, RULES["interaction"]["meaningful"], "meaningful_interaction", "의미 있는 상호작용", interaction=True)
            if p.get("asks_character_state") is True:
                award(event, RULES["interaction"]["asks_state"], "character_state_inquiry", "캐릭터 상태에 대한 관심", interaction=True)
            topic = _norm(p.get("topic", ""))
            if topic and topic not in RULES["normalization"]["unknown_values"] and topic not in seen_types["topic"]:
                seen_types["topic"].add(topic)
                award(event, RULES["interaction"]["new_topic"], "new_conversation_topic", "새 대화 주제")
            valid = greeting or p.get("meaningful") is True or kind == "positive_interaction" or p.get("asks_character_state") is True
            if valid:
                affect("interaction", at)
                record_day("interaction", event)
                processed[event.event_id] = event
            audit_event(event, "applied" if valid else "context_only")
            return
        if kind == "exercise_recorded":
            exercise_type = _norm(p.get("exercise_type", ""))
            if not exercise_type:
                audit_event(event, "invalid_payload", "exercise_type is required")
                return
            for field in ("steps", "minutes", "duration_minutes", "amount"):
                if field in p and (isinstance(p[field], bool) or not isinstance(p[field], (int, float)) or p[field] < 0):
                    audit_event(event, "invalid_payload", f"{field} must be a nonnegative number")
                    return
            quantities = [p[field] for field in ("steps", "minutes", "duration_minutes") if field in p]
            if p.get("unit") in ("steps", "minutes") and "amount" in p:
                quantities.append(p["amount"])
            if not quantities or not any(value > 0 for value in quantities):
                audit_event(event, "invalid_payload", "Verified exercise requires positive steps or duration evidence")
                return
            award(event, RULES["exercise"]["recorded"], "verified_exercise_completed", "검증된 운동 기록 1회")
            if exercise_type not in RULES["normalization"]["unknown_values"] and exercise_type not in seen_types["exercise"]:
                seen_types["exercise"].add(exercise_type)
                award(event, RULES["exercise"]["new_type"], "new_exercise_type", "처음 시도한 운동 종류")
            record_day("exercise", event)
            last_activity = day
            affect("exercise", at)
        elif kind == "food_recorded":
            name, group = _norm(p.get("food_name", p.get("name", ""))), _norm(p.get("food_group", ""))
            if group in RULES["normalization"]["unknown_values"]:
                group = ""
            if not name or name in RULES["normalization"]["unknown_values"] or p.get("confirmed") is False:
                audit_event(event, "invalid_payload", "A confirmed food name is required; its group may remain unknown")
                return
            if "amount" in p and (isinstance(p["amount"], bool) or not isinstance(p["amount"], (int, float)) or p["amount"] <= 0):
                audit_event(event, "invalid_payload", "Food amount, when provided, must be positive")
                return
            fast, balanced = p.get("fast_food") is True, p.get("balanced") is True
            food_history.append((day, group, fast, balanced))
            recent = [entry for entry in food_history if (day - entry[0]).days < limits["window_days"]]
            if fast:
                # Even novelty and streak rewards are excluded for one fast-food event.
                if sum(entry[2] for entry in recent) >= RULES["food"]["fast_food_repeat_count"]:
                    affect("fast_food_pattern", at)
            else:
                if name not in seen_types["food"]:
                    seen_types["food"].add(name)
                    award(event, RULES["food"]["new_food"], "new_food", "처음 기록한 음식")
                if group and group not in seen_types["food_group"]:
                    seen_types["food_group"].add(group)
                    award(event, RULES["food"]["new_group"], "new_food_group", "새로운 음식군")
                record_day("food", event)
                varied = [entry for entry in recent if not entry[2] and entry[1]]
                if (len({entry[1] for entry in varied}) >= RULES["food"]["diversity_groups"]
                        and len({entry[0] for entry in varied}) >= RULES["food"]["diversity_days"]
                        and not any((day - previous).days < limits["window_days"] for previous in diversity_claims)):
                    diversity_claims.append(day)
                    award(event, RULES["food"]["diversity"], "sustained_food_diversity", "일주일의 지속적인 음식 다양성")
                if balanced and len({entry[0] for entry in recent if entry[3] and not entry[2]}) >= RULES["food"]["balanced_pattern_days"]:
                    affect("balanced_food", at)
        elif kind.startswith("quest_"):
            instance = p.get("quest_instance_id")
            if not isinstance(instance, str) or not instance:
                audit_event(event, "invalid_payload", "quest_instance_id is required")
                return
            if p.get("outcome") in ("cancelled", "declined", "rejected"):
                if instance in accepted:
                    ended.add(instance)
                audit_event(event, "cancelled_or_declined", "No personality penalty")
                return
            quest = quest_catalog_entry(event)
            if quest is None:
                audit_event(event, "unknown_quest", "Quest Catalog membership required")
                return
            if kind == "quest_proposed":
                audit_event(event, "proposed")
                return
            if instance in ended:
                audit_event(event, "quest_already_ended", "An attempt can end only once")
                return
            if kind == "quest_accepted":
                if instance in accepted:
                    audit_event(event, "duplicate_acceptance")
                    return
                accepted[instance] = (event, quest)
                audit_event(event, "accepted")
                return
            if instance not in accepted:
                audit_event(event, "quest_not_accepted")
                return
            acceptance, quest = accepted[instance]
            if p.get("quest_id") != acceptance.payload.get("quest_id") or event.occurred_at <= acceptance.occurred_at:
                audit_event(event, "quest_lifecycle_mismatch")
                return
            quest_type = quest["category"]
            if kind == "quest_failed":
                ended.add(instance)
                affect("quest_failed", at)
                accepted_day = acceptance.occurred_at.astimezone(zone).date()
                if (day - accepted_day).days < RULES["quest"]["failure_window_days"]:
                    failures.append((day, instance))
                    eligible = [identifier for failed_day, identifier in failures
                                if (day - failed_day).days < RULES["quest"]["failure_window_days"] and identifier not in penalized_failures
                                and (day - accepted[identifier][0].occurred_at.astimezone(zone).date()).days < RULES["quest"]["failure_window_days"]]
                    if len(eligible) >= RULES["quest"]["failure_count"]:
                        batch = eligible[:RULES["quest"]["failure_count"]]
                        penalized_failures.update(batch)
                        award(event, RULES["quest"]["repeated_failure"], "repeated_accepted_quest_failures", "7일 이내 수락한 퀘스트 3회 실패")
                audit_event(event, "failed")
                return
            references = p.get("evidence_event_ids", [])
            if not isinstance(references, list) or not references or any(not isinstance(ref, str) for ref in references):
                audit_event(event, "missing_quest_evidence")
                return
            references = list(dict.fromkeys(references))
            evidence = [processed[ref] for ref in references if ref in processed]
            if (len(evidence) != len(references)
                    or any(item.occurred_at < acceptance.occurred_at or item.occurred_at > event.occurred_at for item in evidence)
                    or any(evidence_owner.get(ref, instance) != instance for ref in references)):
                audit_event(event, "invalid_quest_evidence", "Evidence must be verified, after acceptance, and owned by this attempt")
                return
            from src.persona_quests import validate_quest_evidence
            evidence_dicts = [item.model_dump(mode="json") for item in evidence]
            history = [item.model_dump(mode="json") for item in processed.values() if item.occurred_at < acceptance.occurred_at]
            if kind == "quest_progressed":
                progress = p.get("progress")
                if isinstance(progress, bool) or not isinstance(progress, (int, float)) or not 0 < progress <= 1 or progress <= quest_progress[instance]:
                    audit_event(event, "nonincreasing_quest_progress")
                    return
                if not set(references) - progressed_evidence[instance]:
                    audit_event(event, "reused_progress_evidence", "Progress requires an additional verified record")
                    return
                if not validate_quest_evidence(quest, evidence_dicts, history, progress=progress):
                    audit_event(event, "insufficient_quest_evidence")
                    return
                quest_progress[instance] = progress
                progressed_evidence[instance].update(references)
                for ref in references:
                    evidence_owner[ref] = instance
                award(event, RULES["quest"]["progress"][quest_type], "verified_quest_progress", "검증된 퀘스트 진행")
                audit_event(event, "progressed")
                return
            if not validate_quest_evidence(quest, evidence_dicts, history):
                audit_event(event, "insufficient_quest_evidence")
                return
            ended.add(instance)
            for ref in references:
                evidence_owner[ref] = instance
            award(event, RULES["quest"]["completed"], "verified_quest_completed", "검증된 퀘스트 완료 (+0.6 원칙, 일반 이벤트 상한 적용)")
            if quest_type == "exercise":
                award(event, RULES["quest"]["exercise_completed"], "exercise_quest_completed", "운동 퀘스트 완료")
            novelty = quest.get("activity", quest_type)
            if novelty not in seen_types["quest"]:
                seen_types["quest"].add(novelty)
                award(event, RULES["quest"]["new_type"], "new_quest_type_completed", "새로운 유형의 퀘스트 완료")
            if quest.get("together"):
                award(event, RULES["quest"]["together"], "together_quest_completed", "캐릭터와 함께하는 퀘스트 완료")
            affect("quest_completed", at)
            audit_event(event, "completed")
            return
        processed[event.event_id] = event
        audit_event(event, "applied")

    by_day: dict[date, list[GrowthEvent]] = defaultdict(list)
    for event in usable:
        by_day[event.occurred_at.astimezone(zone).date()].append(event)
    day = anchor.date()
    while day <= now.date():
        for event in by_day[day]:
            process(event)
        if (day - last_activity).days > RULES["inactivity"]["grace_days"]:
            at = min(now, datetime.combine(day, time.max, tzinfo=zone))
            tick = GrowthEvent(event_id=f"derived-inactivity:{day.isoformat()}",
                               user_id=usable[0].user_id if usable else "simulation",
                               character_id=usable[0].character_id if usable else "test-character",
                               event_type="inactivity_period", occurred_at=at,
                               source="derived_rule", verification_status="verified", confidence=1,
                               payload={}, idempotency_key=f"derived-inactivity:{day.isoformat()}")
            award(tick, RULES["inactivity"]["daily"], "inactivity_after_grace", "7일 유예 이후 활동 기록 없음")
        day += timedelta(days=1)
    decay(now)
    streaks = {}
    for kind, dates in activity_dates.items():
        # An ongoing streak remains visible until today's opportunity expires.
        end = now.date() if now.date() in dates else now.date() - timedelta(days=1)
        streaks[kind] = _streak(dates, end)
    return {"personality": personality, "short_term": transient, "ledger": ledger, "streaks": streaks,
            "event_audit": audit, "stages": stages, "as_of": now.isoformat(), "rules_version": RULES["version"],
            "synthetic": synthetic_stream,
            "window_semantics": "rolling seven local calendar dates, sign-separated actual deltas; all-axis streak total",
            "nutrition_policy": "Missing calories and nutrients remain unknown; no nutrition is inferred."}
