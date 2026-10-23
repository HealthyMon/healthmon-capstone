"""Catalog-owned quest goals and deterministic, evidence-aware selection.

No function awards a reward or completes a quest. Selection uses replayed event
history only; the game backend is responsible for authenticating event sources.
Simulation sources are accepted only as explicitly synthetic local evidence.
"""
from __future__ import annotations

import copy
import json
import math
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path


CATALOG_PATH = Path(__file__).resolve().parents[1] / "config" / "quest_catalog.json"


def load_catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def catalog_by_id(catalog: dict | None = None) -> dict:
    return {q["quest_id"]: copy.deepcopy(q) for q in (catalog or load_catalog())["quests"]}


def _at(value) -> datetime:
    value = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("Timezone-aware occurred_at and now are required")
    return value


def _number(value, default=0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (ValueError, TypeError):
        return default


def _verified(event: dict, config: dict) -> bool:
    return (event.get("verification_status") == "verified"
            and event.get("source") in config["trusted_sources"]
            and _number(event.get("confidence")) >= config["minimum_confidence"]
            and event.get("valid", True) is not False)


def _exercise_type(event: dict) -> str:
    payload = event.get("payload", {})
    name = payload.get("exercise_type", payload.get("activity", payload.get("kind", "")))
    return {"walking": "walk", "걷기": "walk", "스트레칭": "stretch",
            "stretching": "stretch", "cycling": "cycle", "자전거": "cycle"}.get(name, name)


def _food_name(event: dict) -> str:
    payload = event.get("payload", {})
    return str(payload.get("food_name", payload.get("name", payload.get("label", "")))).strip().casefold()


def _food_groups(event: dict) -> set:
    payload = event.get("payload", {})
    values = payload.get("food_groups", [payload.get("food_group", "")])
    if isinstance(values, str):
        values = [values]
    return {str(value).strip().casefold() for value in values if str(value).strip()
            and str(value).strip().casefold() not in {"unknown", "none", "null", "미상"}}


def validate_quest_evidence(quest: dict, evidence: list, history: list | None = None,
                            progress: float = 1.0) -> bool:
    """Check trusted record values against the fixed catalog goal.

    The caller must additionally check ownership, accepted-before-record timing,
    source authenticity, and evidence reuse. Passing unknown/modified catalog
    goals fails closed. `history` is all earlier records for novelty verification.
    Nutrition values are never inferred from a food name or a group.
    """
    if isinstance(progress, bool) or not isinstance(progress, (int, float)) or not 0 < progress <= 1:
        return False
    catalog = load_catalog()
    known = catalog_by_id(catalog).get(quest.get("quest_id", quest.get("id")))
    if not known or any(quest.get(field) != known[field] for field in ("goal", "verification_method", "reward_id")):
        return False
    method, goal = known["verification_method"], known["goal"]
    unique, keys = {}, set()
    for event in evidence:
        if not _verified(event, catalog["selection"]) or event.get("event_type") != method["event_type"]:
            continue
        if event.get("source") != "simulation" and event["source"] not in method["sources"]:
            continue
        if method["activity"] and _exercise_type(event) != method["activity"]:
            continue
        if event.get("idempotency_key") in keys:
            continue
        if event.get("event_id"):
            unique.setdefault(event["event_id"], event)
            if event.get("idempotency_key"):
                keys.add(event["idempotency_key"])
    records = list(unique.values())
    metric = goal["metric"]
    if metric in {"steps", "minutes"}:
        total = 0.0
        for event in records:
            payload = event["payload"]
            amount = payload.get(metric, payload.get("duration_minutes") if metric == "minutes" else None)
            if amount is None and payload.get("unit") == goal["unit"]:
                amount = payload.get("amount")
            total += max(0, _number(amount))
    elif metric == "records":
        total = len([event for event in records if _food_name(event)])
    elif metric == "distinct_food_groups":
        total = len(set().union(*[_food_groups(event) for event in records])) if records else 0
    elif metric == "new_foods":
        if history is None:
            return False
        earlier = {_food_name(event) for event in history
                   if event.get("event_type") == "food_recorded"
                   and _verified(event, catalog["selection"]) and event.get("event_id") not in unique}
        total = len({_food_name(event) for event in records if _food_name(event)} - earlier)
    else:
        return False
    return total >= goal["target"] * progress


def _history(state: dict, events: list, now: datetime, config: dict) -> list:
    """Deterministically filter future, cross-character, invalid, duplicate rows."""
    prepared = []
    audited = state.get("event_audit")
    allowed_statuses = {"applied", "proposed", "accepted", "progressed", "completed", "failed", "cancelled_or_declined"}
    allowed_ids = {row["event_id"] for row in (audited or []) if row.get("status") in allowed_statuses}
    conflicts = {row["event_id"] for row in (audited or []) if row.get("status") == "idempotency_conflict"}
    for raw in events:
        event = raw.model_dump(mode="json") if hasattr(raw, "model_dump") else raw
        if not isinstance(event, dict) or not event.get("event_id"):
            continue
        if audited is not None and (event["event_id"] not in allowed_ids or event["event_id"] in conflicts):
            continue
        try:
            at = _at(event.get("occurred_at"))
        except (ValueError, TypeError):
            continue
        if at > now or event.get("valid", True) is False:
            continue
        if any(state.get(key) and event.get(key) != state[key] for key in ("user_id", "character_id")):
            continue
        prepared.append((at, str(event["event_id"]), event))
    ids, keys, result = set(), set(), []
    for _, event_id, event in sorted(prepared, key=lambda row: (row[0], row[1])):
        key = event.get("idempotency_key")
        if event_id in ids or (key and key in keys):
            continue
        ids.add(event_id)
        if key:
            keys.add(key)
        result.append(event)
    return result


def _context(state: dict, events: list, now: datetime, catalog: dict) -> dict:
    config = catalog["selection"]
    quests = catalog_by_id(catalog)
    history = _history(state, events, now, config)
    cutoff = now - timedelta(days=config["history_days"])
    recent, attempts, rejected, completed, failed, used_evidence = [], {}, {}, [], [], set()
    by_id = {}
    for event in history:
        at, payload, kind = _at(event["occurred_at"]), event.get("payload", {}), event.get("event_type")
        qid = payload.get("quest_id")
        quest = quests.get(qid)
        instance = payload.get("quest_instance_id")
        if _verified(event, config):
            by_id[event["event_id"]] = event
            if at >= cutoff:
                recent.append(event)
        # Declines express a preference, not a fitness/completion assertion.
        # Backend/simulation provenance is still required before policy changes.
        if not quest or not _verified(event, config):
            continue
        outcome = payload.get("outcome", "")
        if outcome in {"cancelled", "declined", "rejected"} or kind in {"quest_rejected", "quest_cancelled"}:
            rejected[quest["activity"]] = at
            if instance in attempts:
                attempts[instance]["closed"] = True
            continue
        if not instance:
            continue
        if kind == "quest_accepted" and instance not in attempts:
            attempts[instance] = {"quest_id": qid, "accepted_at": at, "closed": False}
        elif kind in {"quest_completed", "quest_failed"}:
            attempt = attempts.get(instance)
            if not attempt or attempt["closed"] or attempt["quest_id"] != qid or at <= attempt["accepted_at"]:
                continue
            if kind == "quest_failed":
                attempt["closed"] = True
                if at >= cutoff and attempt["accepted_at"] >= cutoff:
                    failed.append(event)
                continue
            refs = payload.get("evidence_event_ids", [])
            if not isinstance(refs, list) or not refs or any(ref in used_evidence or ref not in by_id for ref in refs):
                continue
            evidence = [by_id[ref] for ref in refs]
            if any(_at(e["occurred_at"]) < attempt["accepted_at"]
                   or _at(e["occurred_at"]) > at
                   or e.get("user_id") != event.get("user_id")
                   or e.get("character_id") != event.get("character_id") for e in evidence):
                continue
            earlier = [e for e in history if _at(e["occurred_at"]) < attempt["accepted_at"]]
            if validate_quest_evidence(quest, evidence, earlier):
                attempt["closed"] = True
                used_evidence.update(refs)
                if at >= cutoff:
                    completed.append(event)
    return {"history": history, "recent": recent, "attempts": attempts,
            "rejected": rejected, "completed": completed, "failed": failed,
            "active": {attempt["quest_id"] for attempt in attempts.values() if not attempt["closed"]}}


def _current_exercise_refusal(text: str, config: dict) -> bool:
    """Conservative explicit-turn preference, never a persisted growth event.

    Remove known negated refusals before matching positive refusal phrases.
    This small Korean rule is not claimed to understand every paraphrase.
    """
    rules = config.get("current_turn_exercise_refusal", {})
    remaining = text
    for pattern in rules.get("negated_patterns", []):
        remaining = re.sub(pattern, "", remaining)
    return any(re.search(pattern, remaining) for pattern in rules.get("refusal_patterns", []))


def explain_selection(state: dict, events: list, now: datetime, limit: int = 3,
                      user_text: str = "", catalog: dict | None = None) -> dict:
    """Return selected fixed quests and reasons for every excluded candidate."""
    now = _at(now)
    catalog = copy.deepcopy(catalog) if catalog is not None else load_catalog()
    config = catalog["selection"]
    weights = config["weights"]
    current_exercise_refusal = _current_exercise_refusal(user_text, config)
    context = _context(state, events, now, catalog)
    personality = state.get("personality", {})
    short = state.get("short_term", {})
    p = {key: min(100, max(0, _number(personality.get(key), 50)))
         for key in ("curiosity", "affection", "activity", "confidence")}
    energy = _number(short.get("energy"), 50)
    stress = _number(short.get("recent_stress"), 0)
    motivation = _number(short.get("recent_motivation"), 50)
    recovery = (energy <= config["low_energy"] or stress >= config["high_stress"]
                or motivation <= config["low_motivation"] or short.get("mood") in {"tired", "low", "sad", "stressed"})
    successes, failures = len(context["completed"]), len(context["failed"])
    max_difficulty = 1
    difficulty_reason = "검증된 성공 기록 전에는 짧은 기본 목표를 우선"
    if successes >= config["level2_successes"] and p["activity"] >= config["low_activity"] and p["confidence"] >= config["low_confidence"]:
        max_difficulty, difficulty_reason = 2, f"최근 검증된 성공 {config['level2_successes']}회 이상에 따른 단계적 목표 확대"
    if successes >= config["level3_successes"] and p["activity"] >= config["high_activity"] and p["confidence"] >= config["high_confidence"]:
        max_difficulty, difficulty_reason = 3, f"최근 검증된 성공 {config['level3_successes']}회 이상과 높은 활동성·자신감"
    if failures >= config["failure_reduction_count"]:
        max_difficulty, difficulty_reason = max(1, max_difficulty - 1), "최근 수락한 퀘스트의 반복 실패로 난이도 완화"
    if recovery or p["activity"] < config["low_activity"] or p["confidence"] < config["low_confidence"]:
        max_difficulty, difficulty_reason = 1, "현재 에너지·스트레스 또는 낮은 활동성·자신감에 맞춘 짧은 목표"
    capability = state.get("capability", {})
    if "max_difficulty" in capability:
        max_difficulty = min(max_difficulty, max(1, int(_number(capability["max_difficulty"], 1))))
    recent = context["recent"]
    exercise = [e for e in recent if e.get("event_type") == "exercise_recorded"]
    food = [e for e in recent if e.get("event_type") == "food_recorded"]
    seen_activities = {_exercise_type(e) for e in context["history"]
                       if e.get("event_type") == "exercise_recorded" and _verified(e, config)}
    groups = set().union(*[_food_groups(e) for e in food]) if food else set()
    # A proposal followed by acceptance is one presentation, while ignored
    # proposals still count: repeatedly offering an unaccepted quest is spam.
    presentations = {(e.get("payload", {}).get("quest_id"),
                      e.get("payload", {}).get("quest_instance_id", e["event_id"]))
                     for e in recent if e.get("event_type") in {"quest_proposed", "quest_accepted"}}
    repeats = Counter(qid for qid, _ in presentations)
    selected, excluded, ranked = [], [], []
    for quest in catalog["quests"]:
        qid, activity = quest["quest_id"], quest["activity"]
        reason = None
        if current_exercise_refusal and quest["category"] == "exercise":
            reason = "이번 대화에서 운동을 원하지 않거나 쉬고 싶다고 명시함"
        elif quest["difficulty"] > max_difficulty:
            reason = "현재 가능한 난이도 초과"
        elif qid in context["active"]:
            reason = "이미 수락하여 진행 중인 퀘스트"
        elif any(catalog_by_id(catalog)[qid2]["activity"] == activity for qid2 in context["active"]):
            reason = "같은 활동의 퀘스트가 이미 진행 중"
        elif activity in context["rejected"] and now - context["rejected"][activity] < timedelta(hours=config["rejection_cooldown_hours"]):
            reason = "최근 거절·취소한 활동의 재제안 대기 기간"
        elif repeats[qid] >= config["max_same_quest_per_week"]:
            reason = "최근 7일 동일 퀘스트 반복 한도"
        elif capability.get("allowed_activities") is not None and activity not in capability["allowed_activities"]:
            reason = "현재 가능한 활동 목록에 없음"
        elif capability.get("verification_methods") is not None and quest["verification_method"]["metric"] not in capability["verification_methods"]:
            reason = "현재 연결된 검증 수단이 없음"
        else:
            matching = [e for e in recent if e.get("payload", {}).get("quest_id") == qid]
            if any(e in context["completed"] and now - _at(e["occurred_at"]) < timedelta(hours=config["same_quest_cooldown_hours"]) for e in matching):
                reason = "같은 퀘스트 완료 후 대기 기간"
            elif any(e.get("event_type") == "quest_proposed"
                     and now - _at(e["occurred_at"]) < timedelta(hours=config["proposal_cooldown_hours"]) for e in matching):
                reason = "같은 퀘스트를 최근 이미 제안함"
        if reason:
            excluded.append({"quest_id": qid, "reason": reason})
            continue
        score, reasons = weights["base"], [difficulty_reason]
        score += weights["difficulty_match"] if quest["difficulty"] == max_difficulty else weights["easier_level"] * (max_difficulty - quest["difficulty"])
        score += weights["weekly_repeat"] * repeats[qid]
        if repeats[qid]:
            reasons.append(f"최근 7일 제안·수락 {repeats[qid]}회로 반복 가중치 감소")
        if quest["category"] == "exercise":
            if p["activity"] >= config["high_activity"] and not recovery:
                score += weights["exercise_preference"]
                reasons.append("활동성이 높아 실행 가능한 운동 선택 우선")
            if p["curiosity"] >= config["high_curiosity"]:
                score += weights["novel_activity"] if activity not in seen_activities else weights["repeated_activity"]
                reasons.append("아직 기록하지 않은 운동 탐색" if activity not in seen_activities else "이미 해 본 운동")
            elif exercise and activity == _exercise_type(exercise[-1]):
                score += weights["preferred_activity"]
                reasons.append("최근 검증된 익숙한 운동 종류")
        else:
            if food:
                score += weights["food_context"]
                reasons.append("최근 검증된 식생활 기록을 이어가는 선택")
            if activity in {"new_food", "food_groups"} and p["curiosity"] >= config["high_curiosity"]:
                score += weights["novel_activity"]
                reasons.append("높은 호기심에 맞춘 새로운 음식·음식군 탐색")
            if food and len(groups) <= 1 and activity in {"new_food", "food_groups"}:
                score += weights["food_variety"]
                reasons.append("최근 기록의 음식군이 적어 다양성을 탐색하되 영양 평가는 하지 않음")
            if recovery:
                score += weights["food_context"]
                reasons.append("에너지가 낮을 때 운동량 증가 없는 기록 목표")
        if quest.get("together") and p["affection"] >= config["high_activity"]:
            score += weights["together_affection"]
            reasons.append("친근한 동행 형태의 목표")
        requested = "food" if any(term in user_text for term in ("음식", "식사", "식단")) else "exercise" if any(term in user_text for term in ("운동", "산책", "걷기", "스트레칭")) else None
        if quest["category"] == requested:
            score += weights["requested_category"]
            reasons.append("현재 대화의 관심 주제")
        result = copy.deepcopy(quest)
        result.update({"selection_reason": "; ".join(reasons), "score": score,
                       "persona_context": {"personality": p, "stages": state.get("stages", {}),
                                           "short_term": copy.deepcopy(short), "max_difficulty": max_difficulty,
                                           "recent_verified_successes": successes, "recent_accepted_failures": failures,
                                           "recent_exercise_records": len(exercise), "recent_food_records": len(food),
                                           "synthetic_history": any(e.get("source") == "simulation" for e in context["history"])}})
        ranked.append(result)
    seen_selection_activities = set()
    for result in sorted(ranked, key=lambda q: (-q["score"], q["quest_id"])):
        if result["activity"] in seen_selection_activities:
            excluded.append({"quest_id": result["quest_id"], "reason": "이번 후보 묶음에서 같은 활동 중복 제외"})
        elif len(selected) < max(0, int(limit)):
            selected.append(result)
            seen_selection_activities.add(result["activity"])
    return {"selected": selected, "excluded": excluded, "max_difficulty": max_difficulty,
            "difficulty_reason": difficulty_reason, "catalog_version": catalog["version"],
            "recent_verified_successes": successes, "recent_accepted_failures": failures,
            "current_turn_exercise_refusal": current_exercise_refusal, "rewards_awarded": False}


def select_quests(state: dict, events: list, now: datetime, limit: int = 3,
                  user_text: str = "", catalog: dict | None = None) -> list:
    return explain_selection(state, events, now, limit, user_text, catalog)["selected"]
