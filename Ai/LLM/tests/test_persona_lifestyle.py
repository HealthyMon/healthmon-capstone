"""Synthetic lifestyle compiler checks; never loads Qwen or opens any database."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta
import json
from zoneinfo import ZoneInfo

import pytest

from src.persona_engine import GrowthEvent, RULES, replay_events
from src.persona_lifestyle import LIFESTYLE_PRESETS, LifestyleInput, compile_lifestyle


START = datetime(2026, 10, 1, tzinfo=ZoneInfo("Asia/Seoul"))


def compiled(values):
    return compile_lifestyle(values, START)


def replay(result):
    return replay_events(result["events"], datetime.fromisoformat(result["end"]))


def records(result, kind):
    return [event for event in result["events"] if event["event_type"] == kind]


def positive(state, axis):
    return sum(max(0, row["final_delta"]) for row in state["ledger"] if row["axis"] == axis)


def test_empty_default_and_metadata_are_explicitly_synthetic():
    result = compiled({})
    assert result["requested"]["days"] == 7
    assert len(result["events"]) == 1
    assert result["synthetic"] is True and result["training_data"] is False
    assert result["nutrition"] == {"calories": "unknown", "nutrients": "unknown"}
    assert result["assumptions"]
    assert replay(result)["personality"] == RULES["initial"]
    assert result["events"][0]["payload"]["anchor_only"] is True


@pytest.mark.parametrize("name", LIFESTYLE_PRESETS)
def test_partial_preset_and_explicit_full_input_have_byte_identical_compiler_json(name):
    partial = deepcopy(LIFESTYLE_PRESETS[name]["input"])
    first = compiled(partial)
    full = deepcopy(first["requested"])
    full_before = json.dumps(full, ensure_ascii=False)
    second = compiled(full)
    assert json.dumps(first, ensure_ascii=False) == json.dumps(second, ensure_ascii=False)
    assert json.dumps(full, ensure_ascii=False) == full_before
    explicit = LifestyleInput.model_validate(full)
    explicit_before = explicit.model_dump_json()
    assert json.dumps(first, ensure_ascii=False) == json.dumps(compiled(explicit), ensure_ascii=False)
    assert explicit.model_dump_json() == explicit_before


def test_numeric_defaults_keep_original_types_without_mutating_explicit_model():
    body = LifestyleInput(exercise_minutes=0.0, exercise_intensity=3.0)
    assert type(body.exercise_minutes) is float and type(body.exercise_intensity) is float
    result = compiled(body)
    assert type(result["requested"]["exercise_minutes"]) is int
    assert type(result["requested"]["exercise_intensity"]) is int
    assert type(body.exercise_minutes) is float and type(body.exercise_intensity) is float
    assert json.dumps(result, ensure_ascii=False) == json.dumps(compiled({}), ensure_ascii=False)
    nondefault = compiled({"days": 14, "exercise_sessions": 14, "exercise_minutes": 280.0, "exercise_intensity": 4.0})
    assert type(nondefault["requested"]["exercise_minutes"]) is float
    assert type(nondefault["requested"]["exercise_intensity"]) is float
    assert nondefault["requested"]["exercise_minutes"] == 280.0


def test_explicit_default_intensity_preserves_payload_json_not_just_numeric_equality():
    values = {"days": 7, "exercise_sessions": 3, "exercise_minutes": 30}
    omitted = compiled(values)
    explicit = compiled(dict(values, exercise_intensity=3.0))
    assert json.dumps(omitted["events"], ensure_ascii=False) == json.dumps(explicit["events"], ensure_ascii=False)
    assert all(type(row["payload"]["exercise_intensity"]) is int for row in records(explicit, "exercise_recorded"))


@pytest.mark.parametrize("name", LIFESTYLE_PRESETS)
def test_nine_presets_reproducible_and_valid_under_existing_engine(name):
    values = deepcopy(LIFESTYLE_PRESETS[name]["input"])
    before = deepcopy(values)
    first, second = compiled(values), compiled(values)
    assert first == second and values == before
    for event in first["events"]:
        GrowthEvent.model_validate(event)
        assert event["source"] == "simulation"
        assert START <= datetime.fromisoformat(event["occurred_at"]) < START + timedelta(days=first["requested"]["days"])
    state = replay(first)
    assert state == replay(second)
    assert all(0 <= value <= 100 for value in state["personality"].values())
    completed = sum(item["status"] == "completed" for item in state["event_audit"])
    failed = sum(item["status"] == "failed" for item in state["event_audit"])
    assert completed == first["requested"]["quest_successes"]
    assert failed == first["requested"]["quest_failures"]


def test_counts_minutes_intensity_categories_and_distinct_types_preserved():
    result = compiled({"days": 7, "exercise_sessions": 8, "exercise_minutes": 123.456,
                       "exercise_intensity": 4, "exercise_streak": 2, "exercise_types": 5,
                       "upper_sessions": 3, "lower_sessions": 2, "cardio_sessions": 2, "flexibility_sessions": 1})
    exercises = records(result, "exercise_recorded")
    assert len(exercises) == 8
    assert sum(row["payload"]["duration_minutes"] for row in exercises) == pytest.approx(123.456)
    assert {row["payload"]["exercise_intensity"] for row in exercises} == {4}
    assert Counter(row["payload"]["category"] for row in exercises) == {"upper": 3, "lower": 2, "cardio": 2, "flexibility": 1}
    assert len({row["payload"]["exercise_type"] for row in exercises}) == 5
    assert result["generated_summary"]["max_exercise_streak"] == 2
    assert not any("steps" in row["payload"] for row in exercises)


@pytest.mark.parametrize("field,value", [("exercise_intensity", 1), ("exercise_intensity", 5), ("exercise_minutes", 120)])
def test_duration_intensity_do_not_add_unconfigured_growth_coefficients(field, value):
    base = {"days": 7, "exercise_sessions": 3, "exercise_minutes": 30, "exercise_streak": 1}
    assert replay(compiled(base))["personality"] == replay(compiled(dict(base, **{field: value})))["personality"]


def test_repeated_known_food_zero_novelty_without_invented_prior_growth():
    result = compiled({"days": 7, "food_days": 7, "food_records": 7, "food_streak": 7})
    state = replay(result)
    assert state["personality"]["curiosity"] == 50
    assert state["personality"]["confidence"] == 50.4
    assert not any(row["reason_code"] in ("new_food", "new_food_group") for row in state["ledger"])
    assert len(result["events"]) == 8  # Anchor plus actual requested records only.
    assert result["generated_summary"]["baseline_known"]["food"]


def test_requested_food_novelty_is_exact_at_raw_rule_level():
    result = compiled({"days": 7, "food_records": 7, "food_days": 7, "new_foods": 3,
                       "new_food_groups": 2, "food_diversity": "medium", "food_streak": 7})
    state = replay(result)
    assert sum(row["reason_code"] == "new_food" for row in state["ledger"]) == 3
    assert sum(row["reason_code"] == "new_food_group" for row in state["ledger"]) == 2
    assert sum(row["raw_delta"] for row in state["ledger"] if row["reason_code"] == "new_food") == pytest.approx(0.6)


def test_unknown_foods_remain_unverified_unknown_and_have_no_long_term_effect():
    result = compiled({"days": 7, "food_records": 3, "food_days": 3, "unknown_foods": 3})
    state = replay(result)
    assert state["personality"] == RULES["initial"]
    assert state["streaks"]["food"] == 0
    assert result["generated_summary"]["max_food_streak"] == 0
    assert result["generated_summary"]["excluded_counts"]["unknown_food_identity"] == 3
    assert len(result["excluded_records"]) == 3
    for row in records(result, "food_recorded"):
        assert row["verification_status"] == "unverified"
        assert row["payload"]["food_name"] == "unknown"
        assert row["payload"]["calories"] == row["payload"]["nutrients"] == "unknown"


def test_fast_food_single_no_novelty_even_with_first_period():
    result = compiled({"days": 1, "food_records": 1, "food_days": 1, "fast_food_meals": 1})
    assert replay(result)["personality"] == RULES["initial"]


def test_verified_food_streak_survives_other_unknown_and_fast_food_days():
    result = compiled({"days": 7, "food_records": 12, "food_days": 5, "food_streak": 3,
                       "unknown_foods": 3, "fast_food_meals": 3})
    assert result["generated_summary"]["max_food_streak"] == 3
    assert replay(result)["streaks"]["food"] == 3


@pytest.mark.parametrize("fast,unknown", [(7, 0), (0, 7), (3, 4)])
def test_food_calendar_streak_accepts_excluded_food_without_awarding_growth_bonus(fast, unknown):
    result = compiled({"days": 7, "food_records": 7, "food_days": 7, "food_streak": 7,
                       "fast_food_meals": fast, "unknown_foods": unknown})
    summary = result["generated_summary"]
    assert result["requested"]["food_streak"] == 7
    assert summary["max_food_record_calendar_streak"] == 7
    assert summary["max_food_streak"] == 0
    assert summary["food_active_days"] == 7 and summary["eligible_food_active_days"] == 0
    assert any("전체 기록 달력 기준" in line and "최장 0일" in line for line in result["assumptions"])
    state = replay(result)
    assert state["personality"] == RULES["initial"]
    assert state["streaks"]["food"] == 0
    assert not any(row["reason_code"].startswith("food_streak") for row in state["ledger"])


def test_calendar_streak_can_exceed_eligible_food_count_without_rejecting_input():
    result = compiled({"days": 7, "food_records": 7, "food_days": 7, "food_streak": 7, "fast_food_meals": 4})
    assert result["generated_summary"]["max_food_record_calendar_streak"] == 7
    assert result["generated_summary"]["max_food_streak"] == 3
    assert replay(result)["streaks"]["food"] == 3
    assert any("최장 7일" in line and "최장 3일" in line for line in result["assumptions"])


def test_unknown_food_calendar_streak_with_unspecified_record_days_is_valid():
    result = compiled({"days": 7, "food_records": 3, "unknown_foods": 3, "food_streak": 1})
    assert result["generated_summary"]["max_food_record_calendar_streak"] == 1
    assert result["generated_summary"]["max_food_streak"] == 0


def test_stopped_preset_keeps_final_fourteen_dates_empty():
    result = compiled(LIFESTYLE_PRESETS["stopped_14"]["input"])
    dates = [datetime.fromisoformat(row["occurred_at"]).date() for row in records(result, "exercise_recorded")]
    assert len(set(dates)) == 16
    assert max(dates) == (START + timedelta(days=15)).date()
    assert result["generated_summary"]["last_exercise_gap_days"] == 14
    state = replay(result)
    assert state["streaks"]["exercise"] == 0
    assert any(row["reason_code"] == "inactivity_after_grace" for row in state["ledger"])


def test_quest_success_has_accepted_chain_unique_evidence_and_no_invented_steps():
    result = compiled({"days": 7, "exercise_sessions": 3, "exercise_minutes": 6,
                       "flexibility_sessions": 3, "quest_successes": 3})
    state = replay(result)
    assert sum(row["status"] == "completed" for row in state["event_audit"]) == 3
    evidence = [ref for row in records(result, "quest_completed") for ref in row["payload"]["evidence_event_ids"]]
    assert len(evidence) == len(set(evidence)) == 3
    assert {row["payload"]["quest_id"] for row in records(result, "quest_completed")} == {"stretch_2"}
    assert not any("steps" in row["payload"] for row in result["events"])


def test_food_records_cannot_verify_exercise_quest():
    with pytest.raises(ValueError, match="음식 기록은 운동 완료 증거"):
        compiled({"days": 7, "food_records": 3, "quest_successes": 3})
    result = compiled({"days": 7, "food_records": 3})
    assert not any("amount" in row["payload"] for row in records(result, "food_recorded"))


@pytest.mark.parametrize("values", [
    {"days": 7, "exercise_sessions": 3, "exercise_minutes": 3, "flexibility_sessions": 3, "quest_successes": 3},
    {"days": 7, "exercise_sessions": 3, "exercise_minutes": 9, "cardio_sessions": 3, "quest_successes": 1},
    {"days": 7, "exercise_sessions": 3, "exercise_minutes": 30, "upper_sessions": 3, "quest_successes": 1},
    {"days": 7, "quest_successes": 1},
])
def test_insufficient_catalog_goal_evidence_is_rejected(values):
    with pytest.raises(ValueError, match="퀘스트|카탈로그"):
        compiled(values)


def test_duplicate_and_unverified_diagnostics_do_not_change_growth():
    values = {"days": 7, "exercise_sessions": 3, "exercise_minutes": 30, "exercise_streak": 1}
    plain, diagnostics = compiled(values), compiled(dict(values, duplicate_events=10, unverified_events=10))
    assert replay(plain)["personality"] == replay(diagnostics)["personality"]
    counts = Counter(row["status"] for row in replay(diagnostics)["event_audit"])
    assert counts["duplicate"] == 10 and counts["blocked_unverified"] == 10


def test_baseline_seed_is_restricted_to_verified_simulation_day_zero_anchor():
    original = compiled({"days": 7, "food_records": 1})
    assert replay(original)["personality"]["curiosity"] == 50
    for change in ({"source": "backend"}, {"verification_status": "unverified"}, {"payload": {"baseline_known": original["events"][0]["payload"]["baseline_known"]}}):
        result = deepcopy(original)
        result["events"][0].update(change)
        assert replay(result)["personality"]["curiosity"] == 50.5
    result = deepcopy(original)
    result["events"][0]["occurred_at"] = (START + timedelta(days=1)).isoformat()
    result["events"].append(dict(original["events"][0], event_id="actual-anchor", idempotency_key="actual-anchor",
                                 payload={"anchor_only": True}))
    assert replay(result)["personality"]["curiosity"] == 50.5


@pytest.mark.parametrize("baseline", [{"activity": ["walk"]}, {"food": "사과"}, {"food": [None]}, {"food": [""]}])
def test_baseline_cannot_set_axes_or_accept_malformed_types(baseline):
    row = compiled({})["events"][0]
    row["payload"]["baseline_known"] = baseline
    with pytest.raises(ValueError):
        GrowthEvent.model_validate(row)


@pytest.mark.parametrize("values", [
    {"days": 2}, {"days": True}, {"exercise_sessions": True}, {"exercise_intensity": True},
    {"exercise_sessions": 1}, {"exercise_minutes": 30}, {"exercise_sessions": 1.5},
    {"exercise_sessions": 121}, {"exercise_minutes": float("nan")}, {"exercise_intensity": 6},
    {"days": 1, "exercise_sessions": 5, "exercise_minutes": 5},
    {"exercise_sessions": 2, "exercise_minutes": 2, "upper_sessions": 3},
    {"exercise_sessions": 2, "exercise_minutes": 2, "exercise_streak": 3},
    {"exercise_sessions": 2, "exercise_minutes": 2, "exercise_types": 3},
    {"exercise_sessions": 2, "exercise_minutes": 2, "exercise_types": 1, "upper_sessions": 1, "lower_sessions": 1},
    {"food_days": 1}, {"food_records": 1, "food_days": 2}, {"food_records": 7, "food_days": 1},
    {"food_records": 1, "new_foods": 2}, {"food_records": 2, "new_food_groups": 2},
    {"food_records": 1, "food_diversity": "high"}, {"food_records": 1, "food_diversity": "medium"},
    {"food_records": 1, "balanced_meals": 1, "fast_food_meals": 1},
    {"food_records": 3, "food_days": 2, "food_streak": 3},
    {"food_records": 1, "fast_food_meals": 1, "new_foods": 1},
    {"exercise_sessions": 28, "exercise_minutes": 28, "exercise_streak": 1},
    {"food_records": 7, "food_days": 7, "food_streak": 1},
    {"last_exercise_gap_days": 8}, {"last_exercise_gap_days": 3}, {"duplicate_events": 1}, {"unknown_axis": 3},
])
def test_incompatible_totals_and_bounds_fail_with_explanation(values):
    with pytest.raises(ValueError):
        compiled(values)


def test_timezone_is_required_and_maximum_input_is_bounded():
    with pytest.raises(ValueError, match="시간대"):
        compile_lifestyle({}, datetime(2026, 10, 1))
    result = compiled({"days": 30, "exercise_sessions": 120, "exercise_minutes": 1200, "cardio_sessions": 120,
                       "food_records": 180, "food_days": 30, "quest_successes": 120, "quest_failures": 120,
                       "duplicate_events": 20, "unverified_events": 20})
    assert len(result["events"]) < 1000
    state = replay(result)
    assert sum(row["status"] == "completed" for row in state["event_audit"]) == 120
    assert all(0 <= value <= 100 for value in state["personality"].values())


def test_compiler_preserves_existing_balance_and_sign_separated_caps():
    result = compiled(LIFESTYLE_PRESETS["quest_success"]["input"])
    before = json.dumps(RULES, sort_keys=True)
    state = replay(result)
    assert json.dumps(RULES, sort_keys=True) == before
    for day in range(result["requested"]["days"]):
        date = (START + timedelta(days=day)).date()
        for axis in RULES["initial"]:
            rows = [row for row in state["ledger"] if row["axis"] == axis]
            current = [row for row in rows if row["local_date"] == date.isoformat()]
            window = [row for row in rows if (date - timedelta(days=6)).isoformat() <= row["local_date"] <= date.isoformat()]
            assert sum(max(0, row["final_delta"]) for row in current) <= RULES["limits"]["daily_positive"] + 1e-8
            assert -sum(min(0, row["final_delta"]) for row in current) <= RULES["limits"]["daily_negative"] + 1e-8
            assert sum(max(0, row["final_delta"]) for row in window) <= RULES["limits"]["weekly_positive"] + 1e-8
            assert -sum(min(0, row["final_delta"]) for row in window) <= RULES["limits"]["weekly_negative"] + 1e-8
