import copy
import json
from datetime import datetime, timezone

import pytest

from src.persona_comparison import build_comparison_observations
from src.persona_quests import explain_selection


def fixture_response(a="같이 해볼까?", b="먼저 시작하자."):
    context = {"personality": {"activity": 50}, "short_term": {"mood": "neutral"},
               "style_profile": {"initiative": .5}, "candidates": [], "memories": [],
               "activities": [], "as_of": "2026-10-01T00:00:00+09:00"}
    def result(speech):
        return {"output_origin": "qwen", "output": {"speech": speech, "action": {"type": "none", "target_id": None},
                "memory_ids": [], "emotion": "neutral", "animation": "idle"},
                "metrics": {"fallback": False, "repaired": False}, "raw_attempts": [{"seed": 123}]}
    prompt = [{"role": "user", "content": json.dumps({"user_text": "안녕"})}]
    return {"user_text": "안녕", "generation": {"seed": 123, "temperature": .7},
            "contexts": {"a": copy.deepcopy(context), "b": copy.deepcopy(context)},
            "prompts": {"a": copy.deepcopy(prompt), "b": copy.deepcopy(prompt)},
            "results": [{"index": 0, "seed": 123, "a": result(a), "b": result(b)}]}


def test_lexical_observations_are_not_semantic_success_scores():
    response = fixture_response("함께 이야기하자. 어떤 느낌인지 궁금해.", "그건 네가 골라도 돼.")
    original = copy.deepcopy(response)
    result = build_comparison_observations(response)
    assert result["requires_human_review"] is True
    assert "lexical_proxy" in result["interpretation"]
    a = result["pairs"][0]["a"]["features"]
    assert a["question_marks"] == 0 and a["lexical_cues"]["question"]
    assert a["lexical_cues"]["warmth"] == ["함께"]
    assert result["controls"]["prompt_user_input_match"] is True
    assert result["controls"]["initial_seed_match"] is True
    assert "성공률은 아닙니다" in result["summary_ko"][0]
    assert response == original
    assert not any(key in result for key in ("success", "passed", "sufficient_style", "factual_correctness"))


def test_context_changes_separate_style_from_candidate_content():
    response = fixture_response()
    response["contexts"]["b"]["style_profile"]["initiative"] = .9
    response["contexts"]["b"]["candidates"] = [{"quest_id": "walk_100", "goal": {"target": 100, "unit": "steps"}}]
    result = build_comparison_observations(response)
    assert result["context_changes"]["style_profile"][0]["field"] == "initiative"
    assert result["context_changes"]["candidates"]["changed"] is True
    assert any("말투 변화로 해석하지" in message for message in result["warnings"])


def test_numbers_are_review_cues_not_assertions_of_goal_change():
    response = fixture_response("처음엔 1분, 전체는 2분 스트레칭이야.")
    response["contexts"]["a"]["candidates"] = [{"quest_id": "stretch_2", "id": "stretch_2", "goal": {"target": 2, "unit": "minutes"}}]
    response["results"][0]["a"]["output"]["action"] = {"type": "offer_quest", "target_id": "stretch_2"}
    result = build_comparison_observations(response)
    cue = next(c for c in result["pairs"][0]["review_cues"] if c["type"] == "goal_wording_to_review")
    assert cue["status"] == "human_review_needed"
    assert "확정하지 않습니다" in cue["reason_ko"]
    assert cue["catalog_goal"] == {"target": 2, "unit": "minutes"}
    assert cue["speech"] == "처음엔 1분, 전체는 2분 스트레칭이야."


def test_memory_and_activity_references_stay_separate():
    response = fixture_response()
    response["contexts"]["a"]["activities"] = [{"event_id": "event-1", "source": "simulation", "verification_status": "verified"}]
    response["contexts"]["a"]["memories"] = [{"id": "memory-1", "source_id": "message-1", "verification_status": "user_reported"}]
    response["results"][0]["a"]["output"]["memory_ids"] = ["event-1"]
    result = build_comparison_observations(response)
    assert result["provenance"]["a"]["activity_event_ids"] == ["event-1"]
    assert result["provenance"]["a"]["memory_ids"] == ["memory-1"]
    assert result["provenance"]["a"]["synthetic_activity_records"] == 1
    cue = next(c for c in result["pairs"][0]["review_cues"] if c["type"] == "memory_reference_membership")
    assert cue["also_activity_event_ids"] == ["event-1"]


def test_mismatched_controls_missing_traces_and_fallback_are_visible():
    response = fixture_response()
    response["prompts"]["b"][0]["content"] = json.dumps({"user_text": "다른 질문"})
    response["results"][0]["b"]["raw_attempts"] = [{"seed": 999}]
    response["results"][0]["a"]["metrics"]["fallback"] = True
    result = build_comparison_observations(response)
    assert result["controls"]["prompt_user_input_match"] is False
    assert result["controls"]["initial_seed_match"] is False
    assert result["pairs"][0]["a"]["exclude_from_model_style_analysis"] is True
    assert result["pairs"][0]["a"]["output_origin"] == "fallback"
    response["results"][0]["b"]["raw_attempts"] = []
    assert build_comparison_observations(response)["controls"]["initial_seed_match"] is None


def test_generation_metadata_is_not_mistaken_for_independent_execution_proof():
    response = fixture_response()
    assert build_comparison_observations(response)["controls"]["side_generation_parameters_match"] is None
    response["results"][0]["b"]["generation"] = {"seed": 123, "temperature": 1.2}
    result = build_comparison_observations(response)
    assert result["controls"]["side_generation_parameters_match"] is False
    assert any("동일 파라미터" in message for message in result["warnings"])


def test_repeated_openings_and_sentence_repetition_are_observations():
    response = fixture_response("수용해. 수용해.")
    response["results"].append(copy.deepcopy(response["results"][0]))
    result = build_comparison_observations(response)
    assert result["pairs"][0]["a"]["features"]["repetition"]["repeated_sentences"] == ["수용해"]
    assert result["repeated_openings"]["a"] == [{"opening": "수용해.", "count": 2}]


@pytest.mark.parametrize("text", ["오늘 운동하기 싫어.", "오늘은 운동 말고 쉬고 싶어.", "오늘 운동 안 해.", "운동 추천하지 마."])
def test_current_turn_refusal_excludes_exercise_without_changing_personality(text):
    state = {"personality": dict(curiosity=50, affection=50, activity=80, confidence=50),
             "short_term": {"mood": "neutral", "energy": 60, "recent_motivation": 50, "recent_stress": 0}}
    original = copy.deepcopy(state)
    at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    result = explain_selection(state, [], at, limit=20, user_text=text)
    assert result["current_turn_exercise_refusal"] is True
    assert all(q["category"] != "exercise" for q in result["selected"])
    assert state == original
    next_turn = explain_selection(state, [], at, limit=20, user_text="운동 추천해 줘.")
    assert any(q["category"] == "exercise" for q in next_turn["selected"])


@pytest.mark.parametrize("text", ["운동 싫은 건 아니야.", "운동하기 싫지 않아.", "운동 안 할 건 아니야.", "운동을 싫어하는 건 아니야."])
def test_negated_refusal_does_not_block_exercise(text):
    state = {"personality": {"activity": 80}, "short_term": {"energy": 60}}
    result = explain_selection(state, [], datetime(2026, 10, 1, tzinfo=timezone.utc), user_text=text)
    assert result["current_turn_exercise_refusal"] is False
    assert any(q["category"] == "exercise" for q in result["selected"])


def test_negated_refusal_plus_explicit_rest_still_respects_rest():
    result = explain_selection({"personality": {"activity": 80}}, [], datetime(2026, 10, 1, tzinfo=timezone.utc),
                               user_text="운동 싫은 건 아니지만 오늘은 쉬고 싶어.")
    assert result["current_turn_exercise_refusal"] is True
    assert all(q["category"] != "exercise" for q in result["selected"])
