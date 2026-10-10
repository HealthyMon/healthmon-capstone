from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from src.persona_engine import replay_events
from src.persona_quests import catalog_by_id, explain_selection, select_quests, validate_quest_evidence
from src.persona_style import build_style, style_prompt
from src.persona_scenarios import SCENARIOS, scenario_events


NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
DEFAULT = {axis: 50.0 for axis in ("curiosity", "affection", "activity", "confidence")}


def state(**values):
    return {"personality": dict(DEFAULT, **values), "short_term": {"mood": "neutral", "energy": 70, "recent_stress": 0, "recent_motivation": 50}}


def event(key, kind, at, **payload):
    return {"event_id": key, "idempotency_key": key, "user_id": "lab", "character_id": "test-pet",
            "event_type": kind, "occurred_at": at.isoformat(), "source": "simulation",
            "verification_status": "verified", "confidence": 1.0, "payload": payload}


def success(index, at, quest_id="walk_100"):
    instance = f"attempt-{index}"
    return [event(f"accept-{index}", "quest_accepted", at, quest_id=quest_id, quest_instance_id=instance),
            event(f"record-{index}", "exercise_recorded", at + timedelta(minutes=1), exercise_type="walk", steps=1000),
            event(f"done-{index}", "quest_completed", at + timedelta(minutes=2), quest_id=quest_id,
                  quest_instance_id=instance, evidence_event_ids=[f"record-{index}"])]


def test_each_axis_has_distinct_structural_controls():
    for axis, field in [("curiosity", "question_frequency"), ("affection", "warmth"),
                        ("activity", "initiative"), ("confidence", "assertiveness")]:
        low = build_style(dict(DEFAULT, **{axis: 20}), {})
        high = build_style(dict(DEFAULT, **{axis: 80}), {})
        assert high[field] > low[field]
        assert high["guidance"] != low["guidance"]
    low = build_style(dict.fromkeys(DEFAULT, 20), {})
    high = build_style(dict.fromkeys(DEFAULT, 80), {})
    assert low["question_budget"] == 0 < high["question_budget"]
    assert low["sentence_budget"] < high["sentence_budget"]
    assert low["response_structure"] != high["response_structure"]
    assert "사실의 확실성" in style_prompt(high)


def test_mood_changes_pace_but_not_warmth_or_traits():
    p = dict(DEFAULT, affection=80, activity=80)
    original = deepcopy(p)
    normal = build_style(p, {"mood": "neutral", "energy": 70})
    low = build_style(p, {"mood": "low", "energy": 20})
    assert low["warmth"] == normal["warmth"]
    assert low["initiative"] < normal["initiative"]
    assert low["stages"] == normal["stages"]
    assert p == original


def test_style_uses_hysteresis_and_rejects_nan():
    assert build_style(dict(DEFAULT, activity=58), {}, {"activity": "high"})["stages"]["activity"] == "high"
    assert build_style(dict(DEFAULT, activity=56), {}, {"activity": "high"})["stages"]["activity"] == "medium"
    with pytest.raises(ValueError):
        build_style(dict(DEFAULT, curiosity=float("nan")), {})


def test_catalog_goals_and_rewards_are_fixed_and_detached():
    selected = select_quests(state(), [], NOW)
    catalog = catalog_by_id()
    assert selected
    for quest in selected:
        assert all(quest[field] == catalog[quest["quest_id"]][field] for field in ("goal", "reward_id", "verification_method"))
    selected[0]["goal"]["target"] = 999999
    assert catalog_by_id()[selected[0]["quest_id"]]["goal"]["target"] != 999999
    assert not validate_quest_evidence(selected[0], [])


def test_high_confidence_alone_does_not_unlock_challenges():
    high = state(activity=90, confidence=90)
    assert explain_selection(high, [], NOW)["max_difficulty"] == 1
    rows = [row for i in range(4) for row in success(i, NOW - timedelta(days=5-i))]
    # Use different catalog IDs for the last two attempts, avoiding repetition cap.
    for row in rows[6:]:
        if row["event_type"].startswith("quest_"):
            row["payload"]["quest_id"] = "walk_500"
    assert explain_selection(high, rows, NOW)["max_difficulty"] == 3
    high["short_term"]["energy"] = 20
    assert explain_selection(high, rows, NOW)["max_difficulty"] == 1


def test_forged_or_unaccepted_completion_cannot_raise_difficulty():
    rows = [row for i in range(4) for row in success(i, NOW - timedelta(days=5-i))]
    high = state(activity=90, confidence=90)
    for row in rows:
        if row["event_type"] == "exercise_recorded":
            row["source"] = "user"
    assert explain_selection(high, rows, NOW)["recent_verified_successes"] == 0
    only_completions = [row for row in rows if row["event_type"] == "quest_completed"]
    assert explain_selection(high, only_completions, NOW)["max_difficulty"] == 1


def test_same_evidence_cannot_complete_two_attempts():
    rows = success(1, NOW - timedelta(days=2))
    rows.insert(0, event("accept-2", "quest_accepted", NOW - timedelta(days=3), quest_id="walk_100", quest_instance_id="attempt-2"))
    rows.append(event("done-2", "quest_completed", NOW - timedelta(days=1), quest_id="walk_100", quest_instance_id="attempt-2", evidence_event_ids=["record-1"]))
    assert explain_selection(state(), rows, NOW)["recent_verified_successes"] == 1


def test_recent_rejection_excludes_all_goals_for_same_activity():
    rows = [event("no", "quest_proposed", NOW - timedelta(hours=2), quest_id="walk_100", quest_instance_id="declined", outcome="declined")]
    result = explain_selection(state(), rows, NOW, limit=20)
    assert all(q["activity"] != "walk" for q in result["selected"])
    assert any("거절" in q["reason"] for q in result["excluded"] if q["quest_id"] == "walk_100")
    assert any(q["activity"] == "walk" for q in select_quests(state(), rows, NOW + timedelta(days=4), limit=20))


def test_active_and_weekly_repeated_quests_are_excluded():
    accepted = [event("active", "quest_accepted", NOW - timedelta(hours=1), quest_id="walk_100", quest_instance_id="a")]
    assert all(q["activity"] != "walk" for q in select_quests(state(), accepted, NOW, limit=20))
    rows = [row for i in range(3) for row in success(i, NOW - timedelta(days=i+2))]
    result = explain_selection(state(), rows, NOW, limit=20)
    assert "walk_100" not in [q["quest_id"] for q in result["selected"]]
    assert any("반복 한도" in q["reason"] for q in result["excluded"])


def test_unaccepted_proposals_count_toward_repeat_limit_without_double_counting():
    rows = [event(f"proposal-{i}", "quest_proposed", NOW - timedelta(days=i+1), quest_id="food_record_1", quest_instance_id=f"offer-{i}") for i in range(3)]
    result = explain_selection(state(), rows, NOW, limit=20)
    assert "food_record_1" not in [q["quest_id"] for q in result["selected"]]
    rows = [event("proposal", "quest_proposed", NOW - timedelta(days=2), quest_id="walk_100", quest_instance_id="attempt-1")] + success(1, NOW - timedelta(days=1))
    candidate = next(q for q in select_quests(state(), rows, NOW, limit=20) if q["quest_id"] == "walk_100")
    assert "제안·수락 1회" in candidate["selection_reason"]


def test_recent_food_context_and_curiosity_change_ranking():
    rows = [event("food", "food_recorded", NOW - timedelta(days=1), food_name="보리밥", food_group="grain")]
    assert select_quests(state(curiosity=90), rows, NOW, limit=1)[0]["quest_id"] == "new_food_1"
    familiar = [event("walk", "exercise_recorded", NOW - timedelta(days=1), exercise_type="walk", steps=300)]
    assert select_quests(state(curiosity=20, activity=80), familiar, NOW, limit=1)[0]["quest_id"] == "walk_100"
    assert select_quests(state(curiosity=90, activity=80), familiar, NOW, limit=1)[0]["quest_id"] == "stretch_2"


def test_evidence_targets_food_novelty_and_partial_progress():
    catalog = catalog_by_id()
    walk = event("walk", "exercise_recorded", NOW, exercise_type="walk", steps=50)
    assert not validate_quest_evidence(catalog["walk_100"], [walk])
    assert validate_quest_evidence(catalog["walk_100"], [walk], progress=0.5)
    food = event("food", "food_recorded", NOW, food_name="두부", food_group="legume")
    assert not validate_quest_evidence(catalog["new_food_1"], [food])
    assert validate_quest_evidence(catalog["new_food_1"], [food], [])
    old = deepcopy(food)
    old["event_id"] = "old-food"
    assert not validate_quest_evidence(catalog["new_food_1"], [food], [old])
    food["payload"]["food_group"] = "unknown"
    assert not validate_quest_evidence(catalog["food_groups_2"], [food], [])


def test_engine_audit_excludes_invalid_and_conflicting_evidence():
    rows = success(1, NOW - timedelta(days=2))
    conflict = deepcopy(rows[1])
    conflict["payload"]["steps"] = 10000
    rows.append(conflict)
    replay = replay_events(rows, NOW)
    replay["personality"] = dict(DEFAULT, activity=90, confidence=90)
    assert explain_selection(replay, rows, NOW)["recent_verified_successes"] == 0


def test_selection_is_reproducible_and_capability_respected():
    current = state(curiosity=90)
    current["capability"] = {"allowed_activities": ["food_record"], "verification_methods": ["records"]}
    result = select_quests(current, [], NOW, limit=20)
    assert [q["quest_id"] for q in result] == ["food_record_1"]
    assert select_quests(current, [], NOW) == result
    assert all(q["goal"]["metric"] != "calories" for q in result)


def test_repeated_accepted_failures_reduce_difficulty_and_unverified_food_is_ignored():
    high = state(activity=90, confidence=90)
    rows = [row for i in range(4) for row in success(i, NOW - timedelta(days=6-i))]
    for i in range(2):
        at = NOW - timedelta(days=2-i)
        rows.extend([event(f"fail-accept-{i}", "quest_accepted", at, quest_id="stretch_2", quest_instance_id=f"fail-{i}"),
                     event(f"fail-{i}", "quest_failed", at + timedelta(minutes=1), quest_id="stretch_2", quest_instance_id=f"fail-{i}")])
    assert explain_selection(high, rows, NOW)["max_difficulty"] == 2
    food = event("claim", "food_recorded", NOW, food_name="두부", food_group="legume")
    food["verification_status"] = "unverified"
    with_claim = select_quests(state(), [food], NOW)
    without_claim = select_quests(state(), [], NOW)
    assert [(q["quest_id"], q["score"]) for q in with_claim] == [(q["quest_id"], q["score"]) for q in without_claim]
    assert all(q["persona_context"]["recent_food_records"] == 0 for q in with_claim)


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_thirty_day_recommendations_respect_history_with_proposal_feedback(scenario):
    """An issued recommendation enters history; preview-only reads do not."""
    from collections import Counter
    from zoneinfo import ZoneInfo

    start = datetime(2026, 10, 1, tzinfo=ZoneInfo("Asia/Seoul"))
    rows = scenario_events(scenario, start=start)
    choices = []
    for day in range(30):
        now = start + timedelta(days=day, hours=23)
        visible = [e for e in rows if datetime.fromisoformat(e["occurred_at"]) <= now]
        current = replay_events(visible, now)
        selected = select_quests(current, visible, now, limit=1)
        assert selected
        quest = selected[0]
        assert quest["quest_id"] in catalog_by_id()
        choices.append(quest["quest_id"])
        # No catalog quest appears more than three times in seven recommendations.
        assert max(Counter(choices[-7:]).values()) <= 3
        suggestion = event(f"offer-{scenario}-{day}", "quest_proposed", now,
                           quest_id=quest["quest_id"], quest_instance_id=f"offer-{day}")
        suggestion.update(user_id="test-persona-lab", character_id=f"test-{scenario}")
        rows.append(suggestion)
    assert len(set(choices)) >= 3
