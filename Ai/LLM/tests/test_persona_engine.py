from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta
import json
import random
from zoneinfo import ZoneInfo

import pytest

from src.persona_engine import AXES, GrowthEvent, RULES, personality_stages, replay_events, stage_for
from src.persona_scenarios import SCENARIOS, scenario_events

START = datetime(2026, 10, 1, tzinfo=ZoneInfo("Asia/Seoul"))


def event(identifier, kind="exercise_recorded", day=0, hour=9, payload=None, **kwargs):
    item = {"event_id": str(identifier), "user_id": "test-user", "character_id": "test-character",
            "event_type": kind, "occurred_at": START + timedelta(days=day, hours=hour),
            "source": "simulation", "verification_status": "verified", "confidence": 1.0,
            "payload": payload if payload is not None else {"exercise_type": "walk", "steps": 500},
            "idempotency_key": f"idem:{identifier}"}
    item.update(kwargs)
    return item


def run(events, days=1, **kwargs):
    return replay_events(events, START + timedelta(days=days) - timedelta(microseconds=1), **kwargs)


def delta(state, axis):
    return round(sum(row["final_delta"] for row in state["ledger"] if row["axis"] == axis), 8)


def accepted(identifier="a", day=0, hour=8, quest="walk_100"):
    return event(identifier, "quest_accepted", day, hour,
                 {"quest_id": quest, "quest_instance_id": f"attempt:{identifier}", "quest_type": "exercise"})


def outcome(acceptance, identifier, kind, day=0, evidence=None, **extra):
    p = dict(acceptance["payload"], **extra)
    if evidence is not None:
        p["evidence_event_ids"] = evidence
    return event(identifier, kind, day, 19, p)


def test_defaults_and_empty_history_do_not_mutate_input():
    initial = {axis: 35.5 for axis in AXES}
    before = dict(initial)
    state = run([], initial=initial)
    assert state["personality"] == before == initial
    assert state["ledger"] == []
    assert state["short_term"]["mood"] == "neutral"


def test_duplicate_event_id_and_idempotency_key_have_one_effect():
    original = event("one")
    same_key = dict(original, event_id="two")
    state = run([original, deepcopy(original), same_key])
    assert state["personality"] == run([original])["personality"]
    assert sum(row["status"] == "duplicate" for row in state["event_audit"]) == 2


def test_conflicting_idempotency_group_fails_closed_and_is_order_independent():
    original = event("same")
    conflict = deepcopy(original)
    conflict["payload"]["exercise_type"] = "cycle"
    alias = dict(original, event_id="alias")
    a, b = run([original, conflict, alias]), run([alias, conflict, original])
    assert a == b
    assert a["personality"] == RULES["initial"]
    assert {row["status"] for row in a["event_audit"]} == {"idempotency_conflict"}


@pytest.mark.parametrize("kind,payload", [
    ("exercise_recorded", {"exercise_type": "walk"}),
    ("food_recorded", {"food_name": "apple", "food_group": "fruit"}),
    ("positive_interaction", {"text": "몽글아 오늘 어때?", "meaningful": True}),
    ("quest_completed", {"quest_id": "walk_100", "quest_instance_id": "fake"}),
])
def test_unverified_events_do_not_grow_or_seed_novelty_streak_or_inactivity(kind, payload):
    blocked = event("u", kind, payload=payload, verification_status="unverified")
    state = run([blocked], days=30)
    assert state["personality"] == RULES["initial"]
    assert state["streaks"] == {"exercise": 0, "interaction": 0, "food": 0}
    assert not state["ledger"]
    assert state["event_audit"][0]["status"] == "blocked_unverified"


@pytest.mark.parametrize("patch", [{"source": "user"}, {"source": "llm"}, {"confidence": 0.79}])
def test_claimed_verification_without_eligible_provenance_is_blocked(patch):
    assert run([event("u", **patch)])["personality"] == RULES["initial"]


def test_conversation_does_not_establish_exercise_food_or_quest_completion():
    row = event("said", "conversation", payload={"text": "운동했고 퀘스트도 완료했어", "meaningful": True})
    state = run([row])
    assert state["personality"]["activity"] == 50
    assert state["personality"]["confidence"] == 50
    assert state["streaks"]["exercise"] == 0


def test_novelty_exact_rules_and_ledger_accounting():
    state = run([event("e")])
    assert state["personality"] == {"curiosity": 50.5, "affection": 50.0, "activity": 50.4, "confidence": 50.2}
    required = {"event_id", "occurred_at", "axis", "before", "raw_delta", "streak_bonus", "cap_adjustment",
                "final_delta", "after", "reason_code", "reason", "source", "verification_status"}
    for row in state["ledger"]:
        assert required <= row.keys()
        assert row["raw_delta"] + row["streak_bonus"] + row["cap_adjustment"] == pytest.approx(row["final_delta"])
        assert row["before"] + row["final_delta"] == pytest.approx(row["after"])


@pytest.mark.parametrize("payload", [{"exercise_type": "walk"}, {"exercise_type": "walk", "steps": 0},
                                    {"exercise_type": "walk", "amount": 10, "unit": "unknown"}])
def test_verified_label_without_positive_measured_exercise_is_not_activity_evidence(payload):
    state = run([event("invalid", payload=payload)])
    assert state["personality"] == RULES["initial"]
    assert state["event_audit"][0]["status"] == "invalid_payload"


def test_verified_measured_alias_duration_and_amount_are_supported():
    duration = run([event("minutes", payload={"exercise_type": "stretch", "duration_minutes": 2})])
    amount = run([event("amount", payload={"exercise_type": "walk", "amount": 100, "unit": "steps"})])
    assert duration["personality"]["activity"] == amount["personality"]["activity"] == 50.4


def test_daily_cap_and_bounds():
    events = [event(str(i), hour=9 + i) for i in range(10)]
    state = run(events)
    assert delta(state, "activity") == 1.0
    assert delta(state, "confidence") == 1.0
    near_maximum = run(events, initial={axis: 99.9 for axis in AXES})
    assert all(0 <= value <= 100 for value in near_maximum["personality"].values())
    assert near_maximum["personality"]["activity"] == 100


def test_rolling_week_does_not_reset_on_monday():
    events = [event(f"e{day}-{i}", day=day, hour=8 + i) for day in range(12) for i in range(8)]
    state = run(events, days=12)
    for day in range(12):
        end = (START + timedelta(days=day)).date()
        beginning = end - timedelta(days=6)
        for axis in AXES:
            window = [row for row in state["ledger"] if row["axis"] == axis
                      and beginning.isoformat() <= row["local_date"] <= end.isoformat()]
            assert sum(max(0, row["final_delta"]) for row in window) <= 3.0 + 1e-8
            assert -sum(min(0, row["final_delta"]) for row in window) <= 1.0 + 1e-8


def test_streak_no_duplicate_award_and_aggregate_weekly_cap():
    events = scenario_events("steady_exercise_success")
    state = run(events, days=30)
    claims = [(row["event_id"], row["axis"], row["reason_code"]) for row in state["ledger"] if row["streak_bonus"]]
    assert len(claims) == len(set(claims))
    for day in range(30):
        start, end = (START + timedelta(days=day - 6)).date().isoformat(), (START + timedelta(days=day)).date().isoformat()
        total = sum(max(0, row["final_delta"]) for row in state["ledger"]
                    if start <= row["local_date"] <= end and row["streak_bonus"])
        assert total <= 1.5 + 1e-8


def test_no_affection_decay_and_inactivity_starts_on_eighth_missed_date():
    original = event("exercise")
    before = run([original])["personality"]
    assert run([original], days=2)["personality"] == before
    assert run([original], days=8)["personality"] == before
    day_eight = run([original], days=9)
    assert day_eight["personality"]["activity"] == pytest.approx(before["activity"] - 0.2)
    assert day_eight["personality"]["affection"] == before["affection"]
    long = run([original], days=30)
    assert long["personality"]["activity"] >= 0
    assert long["personality"]["affection"] == 50
    assert run([original], days=30, initial={"activity": 0})["personality"]["activity"] == 0


def test_unverified_exercise_does_not_break_inactivity():
    rows = [event("one"), event("false", day=10, verification_status="unverified")]
    assert run(rows, days=15)["personality"] == run(rows[:1], days=15)["personality"]


def test_fast_food_once_has_no_long_term_effect_even_if_novel():
    fast = event("fast", "food_recorded", payload={"food_name": "burger", "food_group": "fast", "fast_food": True})
    assert run([fast])["personality"] == RULES["initial"]
    repeated = [dict(fast, event_id=f"f{i}", idempotency_key=f"f{i}", occurred_at=START + timedelta(hours=i + 9)) for i in range(3)]
    state = run(repeated)
    assert state["personality"] == RULES["initial"]
    assert state["short_term"]["energy"] < 60
    assert "calories" not in fast["payload"]
    assert "unknown" in state["nutrition_policy"]


@pytest.mark.parametrize("group", ["unknown", "미상", ""])
def test_unknown_food_group_is_not_novel_or_inferred(group):
    row = event("food", "food_recorded", payload={"food_name": "사과", "food_group": group})
    state = run([row])
    assert state["personality"]["curiosity"] == 50.2
    assert state["streaks"]["food"] == 1
    assert not any(item["reason_code"] == "new_food_group" for item in state["ledger"])


def test_repeated_interaction_and_greeting_variants_do_not_farm_growth():
    rows = [event(f"c{i}", "positive_interaction", hour=8 + i,
                  payload={"text": f"오늘 너와 산책 이야기를 하고 싶어!!! {i}", "meaningful": True}) for i in range(10)]
    assert delta(run(rows), "affection") == 0.2
    greetings = [event(f"g{i}", "conversation", hour=8 + i, payload={"text": text})
                 for i, text in enumerate(("안녕", "안녕!!!", "안녕하세요", "하이", "hello"))]
    assert delta(run(greetings), "affection") == 0.05
    distinct = [event(f"d{i}", "positive_interaction", hour=8 + i, payload={"text": text, "meaningful": True})
                for i, text in enumerate(("책을 읽으니 재미있어", "구름이 뭉게뭉게 피었네", "우리 가족이 보고 싶었어", "너는 좀 어때"))]
    assert delta(run(distinct), "affection") == 0.4


def test_negative_conversation_affects_transient_and_decays():
    row = event("bad", "conversation", payload={"text": "지금 정말 짜증이 나", "negative": True})
    immediate = replay_events([row], row["occurred_at"])
    later = replay_events([row], row["occurred_at"] + timedelta(hours=24))
    assert immediate["personality"] == later["personality"] == RULES["initial"]
    assert immediate["short_term"]["mood"] == "low"
    assert later["short_term"]["mood"] == "neutral"
    assert later["short_term"]["recent_stress"] == pytest.approx(immediate["short_term"]["recent_stress"] / 2)


def test_quest_single_failure_only_mood_three_recent_accepted_failures_penalty():
    rows = []
    for day in range(3):
        accept = accepted(f"a{day}", day=day)
        rows.extend([accept, outcome(accept, f"fail{day}", "quest_failed", day=day)])
    one = run(rows[:2])
    assert one["personality"] == RULES["initial"]
    assert one["short_term"]["mood"] == "low"
    assert run(rows, days=3)["personality"]["confidence"] == 49.5
    # Failing an already-ended attempt cannot form a second group.
    rows.append(outcome(rows[0], "again", "quest_failed", day=2))
    assert run(rows, days=3)["personality"]["confidence"] == 49.5


def test_failures_without_acceptance_or_accepted_outside_window_have_no_penalty():
    missing = [event(str(i), "quest_failed", day=i, payload={"quest_id": "walk_100", "quest_instance_id": str(i)}) for i in range(3)]
    assert run(missing, days=3)["personality"]["confidence"] == 50
    old = []
    for i in range(3):
        a = accepted(str(i))
        old.extend([a, outcome(a, f"failed{i}", "quest_failed", day=8)])
    assert run(old, days=9)["personality"]["confidence"] == 50


def test_completion_requires_catalog_accepted_timing_evidence_and_goal():
    a, record = accepted(), event("record")
    good = outcome(a, "complete", "quest_completed", evidence=["record"])
    state = run([a, record, good])
    completed_rows = [row for row in state["ledger"] if row["reason_code"] == "verified_quest_completed"]
    assert len(completed_rows) == 1
    assert completed_rows[0]["raw_delta"] == 0.6
    assert completed_rows[0]["final_delta"] == 0.5
    assert completed_rows[0]["cap_adjustment"] == -0.1
    assert delta(state, "confidence") == 0.7  # Exercise +.2 and quest +.5, never double +.6.
    assert not any(row["reason_code"] == "verified_quest_completed" for row in run([record, good])["ledger"])
    missing = deepcopy(good); missing["payload"]["evidence_event_ids"] = ["missing"]
    assert run([a, record, missing])["personality"]["confidence"] == 50.2
    short = deepcopy(record); short["payload"]["steps"] = 1
    assert run([a, short, good])["personality"]["confidence"] == 50.2
    old = deepcopy(record); old["occurred_at"] = START + timedelta(hours=7)
    assert run([a, old, good])["personality"]["confidence"] == 50.2
    unknown = deepcopy(a); unknown["payload"]["quest_id"] = "llm-free-quest"
    assert run([unknown])["event_audit"][0]["status"] == "unknown_quest"


def test_evidence_cannot_be_reused_across_attempts_or_progress_farmed():
    first, second, record = accepted("first"), accepted("second"), event("record")
    progress = outcome(first, "p1", "quest_progressed", evidence=["record"], progress=0.2)
    progress["occurred_at"] = START + timedelta(hours=10)
    farm = outcome(first, "p2", "quest_progressed", evidence=["record"], progress=0.8)
    complete = outcome(second, "done", "quest_completed", evidence=["record"])
    state = run([first, second, record, progress, farm, complete])
    statuses = {row["event_id"]: row["status"] for row in state["event_audit"]}
    assert statuses["p1"] == "progressed"
    assert statuses["p2"] == "reused_progress_evidence"
    assert statuses["done"] == "invalid_quest_evidence"


def test_rejected_or_cancelled_quest_has_no_penalty():
    a = accepted()
    cancel = outcome(a, "cancel", "quest_failed", outcome="cancelled")
    assert run([a, cancel])["personality"] == RULES["initial"]


def test_hysteresis_thresholds_large_jumps_and_independent_axes():
    assert stage_for(60, "medium") == "high"
    assert stage_for(57, "high") == "high"
    assert stage_for(56, "high") == "medium"
    assert stage_for(100, "very_low") == "very_high"
    assert stage_for(0, "very_high") == "very_low"
    assert stage_for(74.9) == "high"
    assert personality_stages({"curiosity": 80, "affection": 20}) == {
        "curiosity": "very_high", "affection": "very_low", "activity": "medium", "confidence": "medium"}


def test_timezone_calendar_caps_and_future_events():
    a = event("a", hour=23)
    b = event("b", day=1, hour=0)
    state = run([a, b], days=2)
    assert len({row["local_date"] for row in state["ledger"]}) == 2
    earlier = run([a, b])
    assert any(row["status"] == "future_excluded" for row in earlier["event_audit"])
    assert delta(earlier, "activity") == 0.4


@pytest.mark.parametrize("bad", [{"activity": float("nan")}, {"confidence": float("inf")}, {"affection": -1}, {"curiosity": 101}, {"unknown": 50}, {"activity": True}])
def test_invalid_personality_fails_closed(bad):
    with pytest.raises(ValueError):
        run([], initial=bad)


def test_invalid_schema_and_mixed_streams_rejected():
    with pytest.raises(ValueError):
        GrowthEvent.model_validate(event("bad", occurred_at=datetime(2026, 10, 1)))
    with pytest.raises(ValueError):
        GrowthEvent.model_validate(event("bad", payload={"amount": float("inf")}))
    with pytest.raises(ValueError):
        run([event("a"), event("b", user_id="someone-else")])
    with pytest.raises(ValueError):
        run([], short_term={"energy": float("nan")})


@pytest.mark.parametrize("name", SCENARIOS)
def test_thirty_day_scenarios_reproducible_and_respect_all_caps(name):
    rows = scenario_events(name)
    original = json.dumps(rows, sort_keys=True)
    a = run(rows, days=30)
    shuffled = list(rows)
    random.Random(17).shuffle(shuffled)
    assert run(shuffled, days=30) == a
    assert original == json.dumps(rows, sort_keys=True)
    assert a["synthetic"] is True
    assert all(0 <= value <= 100 for value in a["personality"].values())
    ordinary, daily = defaultdict(float), defaultdict(float)
    for row in a["ledger"]:
        sign = "positive" if row["final_delta"] >= 0 else "negative"
        if not row["streak_bonus"]:
            ordinary[(row["event_id"], row["axis"], sign)] += abs(row["final_delta"])
        daily[(row["local_date"], row["axis"], sign)] += abs(row["final_delta"])
    assert all(total <= 0.5 + 1e-8 for total in ordinary.values())
    assert all(total <= (1.0 if key[-1] == "positive" else 0.5) + 1e-8 for key, total in daily.items())
    for day in range(30):
        start, end = (START + timedelta(days=day - 6)).date().isoformat(), (START + timedelta(days=day)).date().isoformat()
        for axis in AXES:
            window = [row for row in a["ledger"] if row["axis"] == axis and start <= row["local_date"] <= end]
            assert sum(max(0, row["final_delta"]) for row in window) <= 3 + 1e-8
            assert -sum(min(0, row["final_delta"]) for row in window) <= 1 + 1e-8
