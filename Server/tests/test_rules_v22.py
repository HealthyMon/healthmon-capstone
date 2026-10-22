"""Boundary and replay tests for the supplied HEALTHMON v2.2 policy."""
from datetime import datetime, timedelta, timezone
import random

import pytest

from healthmon import rules as r


def at(day=19, hour=12, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=r.KST)


def workout(actual=30, **extra):
    return {"exercise_type": "running", "actual": actual, "target": 30,
            "unit": "minutes", "body_part": "lower", **extra}


def meal(meal_type="breakfast", **extra):
    return {"confirmed": True, "quantity_confirmed": True, "food_name": "meal",
            "meal_type": meal_type, "carbohydrate_g": 55, "protein_g": 20,
            "fat_g": 15, "vegetable_fruit_g": 80, "kcal": 435, **extra}


def chat(**classification):
    return {"normal": True, "text": "hello", "classification": {
        "target": "other", "sentiment": "neutral", "motivation": "neutral",
        "character_affection": "neutral", "acceptance": "none", "confidence": .6,
        **classification}}


def event(ident, kind="workout", payload=None, when=None, received=None, **extra):
    when = when or at()
    return {"event_id": ident, "kind": kind, "payload": payload if payload is not None else workout(),
            "occurred_at": when, "received_at": received or when, "valid": True, **extra}


def project(events, now=None, proposals=None):
    return r.replay(events, now or at(22, 23), proposals=proposals)


def test_initial_values_are_v22_and_fresh():
    state = r.initial_state()
    assert (state["level"], state["current_exp"], state["required_exp"], state["total_exp"], state["coin"]) == (1, 0, 100, 0, 0)
    assert all(state[k] == 50 for k in ("upper_body", "lower_body", "nutrition", "activity", "affinity", "initiative"))
    assert state["energy_balance"] == state["evolution_target_stage"] == 0
    assert "mood" not in state and "affection" not in state
    state["activity"] = 99
    assert r.initial_state()["activity"] == 50


@pytest.mark.parametrize("level,expected", [(1, 100), (2, 110), (3, 120), (4, 140), (10, 270), (20, 650), (30, 1230)])
def test_exp_formula_rounding(level, expected):
    assert r.required_exp(level) == expected


@pytest.mark.parametrize("bad", [0, -1, 1.5, True, None])
def test_invalid_level(bad):
    with pytest.raises(ValueError):
        r.required_exp(bad)


def test_exp_carries_across_multiple_levels_and_stage_thresholds():
    total = sum(r.required_exp(level) for level in range(1, 31)) + 23
    state = r.exp_progress(total)
    assert state == {"total_exp": total, "level": 31, "current_exp": 23,
                     "required_exp": r.required_exp(31), "evolution_target_stage": 3}


@pytest.mark.parametrize("delay,status", [(timedelta(0), "eligible"), (timedelta(hours=24), "eligible"),
    (timedelta(hours=24, microseconds=1), "archive_only"), (timedelta(microseconds=-1), "future")])
def test_exact_24h_and_future_boundary(delay, status):
    assert r.eligibility(at(), at() + delay) == status


def test_naive_timestamp_rejected_and_iso_offset_supported():
    with pytest.raises(ValueError):
        r.eligibility(datetime(2026, 10, 19), at())
    assert r.eligibility("2026-10-19T03:00:00Z", "2026-10-20T03:00:00+00:00") == "eligible"


@pytest.mark.parametrize("actual,score", [(36, 3), (35.999, 2), (30, 2), (29.999, 1),
    (21, 1), (20.999, 0), (12, 0), (11.999, -1), (.00001, -1), (0, 0)])
def test_workout_thresholds(actual, score):
    result = r.workout_delta(workout(actual))
    assert result["evaluation_status"] == "evaluated"
    assert result["lower_body"] == score
    assert result["upper_body"] == 0
    assert result["actual_workout"] == (actual > 0)


@pytest.mark.parametrize("field,value", [("actual", None), ("actual", float("nan")), ("actual", float("inf")),
    ("actual", -1), ("actual", False), ("target", None), ("target", 0), ("target", -1),
    ("target", float("inf")), ("unit", "steps")])
def test_workout_missing_invalid_or_wrong_unit_is_preserved_unscored(field, value):
    result = r.workout_delta(workout(**{field: value}))
    assert result["evaluation_status"] == "recorded_unscored"
    assert result["actual_workout"] is False and result["achievement_rate"] is None


def test_squat_time_does_not_become_repetitions_and_unknown_goal_is_not_guessed():
    assert r.workout_delta(workout(exercise_type="squat", unit="minutes"))["reason"] == "unit_mismatch"
    assert r.workout_delta(workout(exercise_type="cycling"))["reason"] == "unsupported_goal"
    result = r.workout_delta(workout(exercise_type="custom", goal_confirmed_before_start=True))
    assert result["evaluation_status"] == "evaluated"


def test_no_synthetic_actual_from_distance_calories_or_heart_rate():
    payload = workout(actual=None, duration_seconds=1800, calories=200, distance=3, heart_rate=120)
    assert r.workout_delta(payload)["evaluation_status"] == "recorded_unscored"


@pytest.mark.parametrize("score,upper,lower,expected", [(3, 50, 50, (2, 1)), (3, 60, 40, (1, 2)),
    (2, 50, 50, (1, 1)), (1, 50, 50, (1, 0)), (1, 60, 40, (0, 1)),
    (0, 50, 50, (0, 0)), (-1, 50, 50, (-1, 0)), (-1, 40, 60, (0, -1)),
    (-2, 50, 50, (-1, -1))])
def test_full_body_integer_distribution(score, upper, lower, expected):
    amount = {3: 36, 2: 30, 1: 21, 0: 12, -1: 1, -2: 0}[score]
    payload = workout(amount, body_part="full", confirmed_nonperformance=score == -2)
    result = r.workout_delta(payload, upper, lower)
    assert (result["upper_body"], result["lower_body"]) == expected


def test_zero_requires_explicit_nonperformance_and_same_body_actual_suppresses_it():
    assert r.workout_delta(workout(0))["lower_body"] == 0
    assert r.workout_delta(workout(0, confirmed_nonperformance=True))["lower_body"] == -2
    events = [event("missed", payload=workout(0, confirmed_nonperformance=True), when=at(hour=8)),
              event("actual", payload=workout(12), when=at(hour=10))]
    result = project(events)
    assert result["state"]["lower_body"] == 50
    assert result["evaluations"]["missed"]["lower_body"] == 0
    assert result["daily"][0]["confirmed_nonperformance_day"] is False


def test_full_body_missed_only_suppresses_body_with_actual_performance():
    events = [event("missed", payload=workout(0, body_part="full", confirmed_nonperformance=True)),
              event("actual", payload=workout(12), when=at(hour=13))]
    result = project(events)
    assert result["state"]["upper_body"] == 49
    assert result["state"]["lower_body"] == 50


def test_daily_net_cap_sums_before_clamping_not_independent_signed_budgets():
    events = [event("a", payload=workout(36), when=at(hour=8)),
              event("b", payload=workout(36), when=at(hour=9)),
              event("c", payload=workout(1), when=at(hour=10))]
    result = project(events)
    assert result["daily"][0]["raw_deltas"]["lower_body"] == 5
    assert result["daily"][0]["capped_deltas"]["lower_body"] == 3
    assert result["state"]["lower_body"] == 53


def test_replay_orders_before_full_body_distribution_and_uses_preceding_state():
    events = [event("b", payload=workout(21, body_part="full")),
              event("a", payload=workout(21, body_part="full"))]
    result = project(events)
    assert result["evaluations"]["a"]["upper_body"] == 1
    assert result["evaluations"]["b"]["lower_body"] == 1
    assert result["state"]["upper_body"] == result["state"]["lower_body"] == 51
    assert project(list(reversed(events))) == result


def test_day_and_exp_reward_change_at_kst_midnight():
    events = [event("a", when=at(hour=23, minute=59)), event("b", when=at(20, 0))]
    result = project(events)
    assert result["state"]["lower_body"] == 54
    assert [item["date"] for item in result["daily"] if item["workout_day"]] == ["2026-10-19", "2026-10-20"]
    assert sum(candidate["exp"] for candidate in result["reward_candidates"]) == 70


@pytest.mark.parametrize("extra", [{"confirmed": False}, {"quantity_confirmed": False}, {"food_name": ""},
    {"food_name": "water"}, {"water_only": True}])
def test_unconfirmed_empty_water_meals_get_no_reward_or_score(extra):
    result = r.meal_delta(meal(**extra))
    assert result["reward_eligible"] is False
    assert result["nutrition"] == result["energy_balance"] == 0


def test_unknown_nutrients_stay_unknown_and_energy_can_evaluate_independently():
    result = r.meal_delta(meal(protein_g=None, vegetable_fruit_g=None))
    assert result["macro_energy"] is None
    assert result["nutrition_status"] == "unknown"
    assert result["energy_balance_status"] == "evaluated"
    assert result["nutrition"] == result["energy_balance"] == 0


@pytest.mark.parametrize("bad", [None, -1, True, float("nan"), float("inf")])
def test_invalid_macronutrient_is_not_invented(bad):
    result = r.meal_delta(meal(carbohydrate_g=bad))
    assert result["nutrition_status"] == "unknown"


def test_four_nutrition_conditions_and_e_minimum():
    assert r.meal_delta(meal())["nutrition"] == 2
    assert r.meal_delta(meal(vegetable_fruit_g=79.999))["nutrition"] == 1
    low = meal(carbohydrate_g=5.5, protein_g=2, fat_g=1.5, kcal=None)
    assert r.meal_delta(low)["macro_energy"] == 43.5
    assert r.meal_delta(low)["nutrition_status"] == "unknown"
    assert r.meal_delta(meal(carbohydrate_g=0, protein_g=0, fat_g=0, kcal=None))["energy_balance_status"] == "unknown"


@pytest.mark.parametrize("carbs,protein,fat,produce,count", [(45, 20, 140 / 9, 80, 4),
    (65, 10, 100 / 9, 80, 4), (0, 100, 0, 0, 0), (0, 100, 0, 80, 1), (100, 0, 0, 80, 1)])
def test_nutrition_ratios_are_inclusive_and_counted_separately(carbs, protein, fat, produce, count):
    result = r.meal_delta(meal(carbohydrate_g=carbs, protein_g=protein, fat_g=fat, vegetable_fruit_g=produce, kcal=None))
    assert result["conditions_met"] == count
    assert result["nutrition"] == count - 2


@pytest.mark.parametrize("ratio,expected", [(.699999, -3), (.7, -2), (.899999, -2), (.9, 0),
    (1.1, 0), (1.100001, 2), (1.3, 2), (1.300001, 3)])
def test_energy_balance_ratio_boundaries(ratio, expected):
    result = r.meal_delta(meal(carbohydrate_g=None, kcal=450 * ratio))
    assert result["energy_balance_status"] == "evaluated"
    assert result["energy_balance"] == expected


@pytest.mark.parametrize("kcal,status", [(49.99, "unknown"), (50, "evaluated"), (3000, "evaluated"), (3000.01, "unknown"),
    (float("nan"), "unknown"), (-1, "unknown")])
def test_kcal_validity_range(kcal, status):
    assert r.meal_delta(meal(carbohydrate_g=None, kcal=kcal))["energy_balance_status"] == status


def test_kcal_discrepancy_over_twenty_percent_requires_reconfirmation():
    base = meal(carbohydrate_g=50, protein_g=25, fat_g=0)  # E = 300
    assert r.meal_delta({**base, "kcal": 360})["energy_balance_status"] == "evaluated"
    discrepant = {**base, "kcal": 360.00001}
    assert r.meal_delta(discrepant)["energy_balance_status"] == "reconfirmation_required"
    assert r.meal_delta({**discrepant, "kcal_reconfirmed": True})["energy_balance_status"] == "evaluated"


def test_missing_kcal_uses_macro_energy_but_explicit_invalid_kcal_does_not():
    assert r.meal_delta(meal(kcal=None))["confirmed_kcal"] == 435
    assert r.meal_delta(meal(kcal=float("nan")))["confirmed_kcal"] is None


def test_meal_items_sum_into_one_bundle_before_scoring_and_reward():
    half = meal(carbohydrate_g=None, protein_g=None, fat_g=None, kcal=225)
    events = [event("a", "meal", half, at(hour=8)), event("b", "meal", half, at(hour=9))]
    result = project(events)
    assert result["state"]["energy_balance"] == 0
    assert result["daily"][0]["meal_bundles"]["breakfast"]["confirmed_kcal"] == 450
    assert sum(item["exp"] for item in result["reward_candidates"]) == 20


def test_bundle_does_not_hide_missing_nutrients_or_unconfirmed_discrepancy():
    events = [event("a", "meal", meal(kcal=1000), at(hour=8)),
              event("b", "meal", meal(carbohydrate_g=None, kcal=100), at(hour=9))]
    result = project(events)
    bundle = result["daily"][0]["meal_bundles"]["breakfast"]
    assert bundle["nutrition_status"] == "unknown"
    # The first constituent still requires review even though bundle macros are unknown.
    assert bundle["energy_balance_status"] == "reconfirmation_required"


def test_daily_nutrition_and_energy_net_caps_and_maximum_base_exp():
    events = [event("workout", payload=workout(36)), event("chat", "chat", chat())]
    for index, meal_type in enumerate(("breakfast", "lunch", "dinner")):
        events.append(event(f"meal{index}", "meal", meal(meal_type, kcal=1000, kcal_reconfirmed=True)))
    events.append(event("snack", "meal", meal("snack", kcal=100)))
    result = project(events)
    assert result["state"]["nutrition"] == 53
    assert result["state"]["energy_balance"] == 4
    assert sum(item["exp"] for item in result["reward_candidates"]) == 90
    assert len({item["reward_key"] for item in result["reward_candidates"]}) == 7
    assert result["state"]["coin"] == 0


def test_snack_only_gets_record_exp_with_no_lifestyle_stat_score():
    result = project([event("s", "meal", meal("snack"))])
    assert result["state"]["nutrition"] == 50 and result["state"]["energy_balance"] == 0
    assert sum(item["exp"] for item in result["reward_candidates"]) == 20


def test_reward_keys_survive_reordering_and_new_earlier_event():
    initial = project([event("later", when=at(hour=13))])
    replay = project([event("later", when=at(hour=13)), event("earlier", when=at(hour=10))])
    assert {c["reward_key"] for c in initial["reward_candidates"]} == {c["reward_key"] for c in replay["reward_candidates"]}


def test_duplicate_replay_events_once_and_conflicting_content_rejected():
    item = event("x")
    assert project([item, item]) == project([item])
    with pytest.raises(ValueError, match="Conflicting"):
        project([item, {**item, "payload": workout(21)}])


def test_archive_invalid_and_future_events_never_score_or_award():
    events = [event("archive", received=at() + timedelta(hours=24, microseconds=1)),
              event("invalid", valid=False), event("deleted", deleted=True),
              event("future", when=at(23)), event("clock", received=at() - timedelta(seconds=1))]
    result = project(events, now=at(22))
    assert result["state"] == r.initial_state()
    assert result["reward_candidates"] == []
    assert result["evaluations"]["archive"]["evaluation_status"] == "archive_only"


@pytest.mark.parametrize("summary,expected", [
    ({"workout_days": 5, "workout_average": 100, "high_motivation_days": 2}, 3),
    ({"workout_days": 5, "workout_average": 100, "high_motivation_days": 1}, 2),
    ({"workout_days": 4, "workout_average": 70}, 2), ({"workout_days": 4, "workout_average": 69.99}, 1),
    ({"workout_days": 3}, 1), ({"workout_days": 2}, 0),
    ({"workout_days": 1, "confirmed_nonperformance_days": 2, "low_motivation_days": 2, "valid_rejections": 2}, -2),
    ({"workout_days": 1, "confirmed_nonperformance_days": 2}, -1),
    ({"workout_days": 0, "low_motivation_days": 5, "valid_rejections": 5}, 0), ({}, 0)])
def test_activity_first_matching_condition(summary, expected):
    assert r.personality_delta(summary)["activity"] == expected


@pytest.mark.parametrize("summary,expected", [
    ({"character_negative_count": 3, "character_negative_days": 2, "conversation_days": 6}, -2),
    ({"character_negative_count": 3, "character_negative_days": 1, "conversation_days": 6}, 0),
    ({"character_negative_count": 1, "conversation_days": 6}, 0),
    ({"conversation_days": 6, "character_positive_count": 3, "actual_memory_mentions": 1}, 3),
    ({"conversation_days": 6, "character_positive_count": 3}, 2),
    ({"conversation_days": 4}, 2), ({"conversation_days": 2}, 1),
    ({"conversation_days": 1, "life_record_days": 5}, -1), ({"conversation_days": 0}, 0)])
def test_affinity_first_matching_condition_and_no_fabricated_memory(summary, expected):
    assert r.personality_delta(summary)["affinity"] == expected


@pytest.mark.parametrize("o,a,c,expected", [(0, 0, 0, 0), (5, 4, 4, 3), (5, 3, 3, 2),
    (5, 4, 1, 0), (5, 3, 0, -1), (5, 2, 0, -2)])
def test_initiative_ratio_thresholds_and_zero_denominator(o, a, c, expected):
    assert r.personality_delta({"proposals": o, "accepted": a, "completed": c})["initiative"] == expected


def test_initiative_extra_and_maximum_and_invalid_denominator():
    summary = {"proposals": 5, "accepted": 5, "completed": 5, "meal_days": 5, "workout_days": 2}
    assert r.personality_delta(summary)["initiative"] == 3
    assert r.personality_delta({"meal_days": 5, "workout_days": 2})["initiative"] == 1
    with pytest.raises(ValueError):
        r.personality_delta({"proposals": 1, "accepted": 0, "completed": 1})


def test_low_confidence_chat_exp_still_earned_but_personality_excluded():
    records = [event("a", "chat", chat(confidence=.599), at(12)), event("b", "chat", chat(confidence=.599), at(13))]
    result = project(records, now=at(19))
    assert sum(item["exp"] for item in result["reward_candidates"]) == 30
    assert result["weekly"][-1]["summary"]["conversation_days"] == 0
    assert result["state"]["affinity"] == 50


def test_workout_complaints_are_not_character_negativity():
    records = [event(str(day), "chat", chat(target="workout", sentiment="negative", motivation="low"), at(day)) for day in (12, 13, 14)]
    result = project(records, now=at(19))
    summary = result["weekly"][-1]["summary"]
    assert summary["character_negative_count"] == 0 and summary["low_motivation_days"] == 3
    assert result["state"]["affinity"] == 51


def test_same_week_late_replay_replaces_weekly_result_and_daily_average_is_unweighted():
    records = [event("mon", when=at(12)), event("tue", when=at(13))]
    before = project(records, now=at(19, 0))
    late = event("sun", when=at(18, 23), received=at(19, 22))
    after = project(records + [late], now=at(19, 23))
    assert before["state"]["activity"] == 50
    assert after["state"]["activity"] == 51
    assert project(records + [late], now=at(20, 0))["state"]["activity"] == 51
    assert after["weekly"][-1]["finalized"] is False
    assert project(records + [late], now=at(20, 0))["weekly"][-1]["finalized"] is True


def test_workout_daily_rate_cap_and_mean_of_days():
    records = [event("a", payload=workout(300), when=at(12)),
              event("b", payload=workout(3), when=at(12, 13)), event("c", payload=workout(30), when=at(13))]
    result = project(records, now=at(19))
    # Monday's (150+10)/2=80; Tuesday=100; weekly average=(80+100)/2=90.
    assert result["weekly"][-1]["summary"]["workout_average"] == 90


def test_monday_eb_decay_precedes_meals_and_downtime_recovers_each_monday():
    records = [event("sunday", "meal", meal(carbohydrate_g=None, kcal=1000), at(18)),
              event("monday", "meal", meal(carbohydrate_g=None, kcal=1000), at(19))]
    result = project(records, now=at(19))
    assert result["daily"][1]["before"]["energy_balance"] == 1
    assert result["state"]["energy_balance"] == 4
    assert project(records, now=at(26))["state"]["energy_balance"] == 2
    assert project(records, now=datetime(2026, 11, 2, 12, tzinfo=r.KST))["state"]["energy_balance"] == 0


def test_negative_monday_eb_decay_never_crosses_zero():
    records = [event("sunday", "meal", meal(carbohydrate_g=None, kcal=100), at(18))]
    assert project(records, now=at(19))["state"]["energy_balance"] == -1
    assert project(records, now=at(26))["state"]["energy_balance"] == 0


def test_proposals_use_shown_valid_24h_deadline_week_and_verified_completion():
    def proposal(ident, **extra):
        return {"proposal_id": ident, "shown": True, "created_at": at(16), "deadline": at(17),
                "accepted_at": at(16, 13), "completed_at": at(17, 10), "completion_verified": True, **extra}
    proposals = [proposal("good"), proposal("duplicate"), proposal("duplicate"),
                 proposal("hidden", shown=False), proposal("cancel", cancelled=True), proposal("rest", rest=True),
                 proposal("basic", acceptance_supported=False), proposal("fake", completion_verified=False),
                 proposal("next_week", created_at=at(18), deadline=at(19))]
    result = project([event("some_record", when=at(12))], now=at(19), proposals=proposals)
    summary = result["weekly"][-1]["summary"]
    assert (summary["proposals"], summary["accepted"], summary["completed"]) == (3, 3, 2)
    assert result["weekly"][-1]["deltas"]["initiative"] == 2


def test_14_day_workout_trend_requires_two_valid_dates_each_window():
    records = [event("a", payload=workout(21), when=at(9)), event("b", payload=workout(21), when=at(10)),
              event("c", payload=workout(36), when=at(16)), event("d", payload=workout(36), when=at(17))]
    result = project(records, now=at(22))
    assert result["trend"] == {"status": "improved", "recent_average": 1.5, "previous_average": .5, "difference": 1.0}
    assert project(records[:3], now=at(22))["trend"]["status"] == "unknown"


def test_stats_stay_within_global_range_after_many_days():
    start = at(1)
    records = [event(str(index), payload=workout(36), when=start + timedelta(days=index)) for index in range(100)]
    result = project(records, now=start + timedelta(days=100))
    assert result["state"]["lower_body"] == 100
    assert result["state"]["upper_body"] == 50


@pytest.mark.parametrize("upper,lower,nutrition,eb,appearance", [
    (44, 44, 50, 30, "adipose"), (65, 65, 50, -30, "lean_athletic"), (64, 64, 50, -30, "lean"),
    (65, 65, 50, 30, "bulky_athletic"), (45, 45, 50, 30, "rounded_general"),
    (80, 50, 50, 0, "upper_developed"), (50, 80, 50, 0, "lower_developed"),
    (65, 65, 60, 0, "balanced_athletic"), (65, 65, 59.99, 0, "developed_general"),
    (45, 45, 50, 0, "ordinary"), (44.99, 44.99, 50, 0, "undertrained")])
def test_evolution_appearance_precedence(upper, lower, nutrition, eb, appearance):
    state = {**r.initial_state(), "level": 10, "upper_body": upper, "lower_body": lower,
             "nutrition": nutrition, "energy_balance": eb}
    assert r.evolution_profile(state)["appearance"] == appearance


def test_evolution_thresholds_profile_change_recovery_and_same_stage_no_regeneration():
    state = {**r.initial_state(), "level": 30, "upper_body": 80, "lower_body": 50, "published_model_stage": 3}
    result = r.evolution_profile(state, {"strength": 50, "appearance": "adipose"})
    assert result["stage"] == 3 and result["generation_required"] is False
    assert result["strength_change"] == 15 and result["progress"] == "improved"
    assert result["recovery"] is True
    assert r.evolution_profile(state)["strength_change"] is None
    assert r.evolution_profile(state)["progress"] is None
    assert r.evolution_profile({**state, "published_model_stage": 1})["generation_required"] is True


@pytest.mark.parametrize("level,stage", [(9, 0), (10, 1), (19, 1), (20, 2), (29, 2), (30, 3), (100, 3)])
def test_evolution_level_stages(level, stage):
    assert r.evolution_profile({**r.initial_state(), "level": level})["stage"] == stage


@pytest.mark.parametrize("score,display,expression", [(0, "low", 0), (24, "low", 0), (25, "low", 1),
    (34, "low", 1), (35, "middle", 1), (40, "middle", 2), (59, "middle", 2),
    (60, "middle", 3), (65, "middle", 3), (66, "high", 3), (75, "high", 4), (100, "high", 4)])
def test_personality_display_and_llm_bands(score, display, expression):
    assert r.personality_bands(score) == {"display": display, "expression": expression}


@pytest.mark.parametrize("score,period,limit,hours", [(0, "week", 3, 24), (39, "week", 3, 24),
    (40, "day", 1, 8), (69, "day", 1, 8), (70, "day", 2, 4), (100, "day", 2, 4)])
def test_initiative_proposal_frequency_policy(score, period, limit, hours):
    assert r.proposal_policy(score) == {"period": period, "limit": limit, "minimum_hours": hours}


def test_replay_is_deterministic_across_transport_order():
    records = [event(f"w{day}", payload=workout(30), when=at(day)) for day in range(12, 19)]
    records += [event(f"m{day}", "meal", meal(), at(day, 8)) for day in range(12, 19)]
    records += [event(f"c{day}", "chat", chat(), at(day, 20)) for day in range(12, 19)]
    expected = project(records, now=at(19))
    random.Random(2200).shuffle(records)
    assert project(records, now=at(19)) == expected
