"""Deterministic expression controls; numeric traits never come from the LLM."""
from __future__ import annotations

import json
import math
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "persona_styles.json"
AXES = ("curiosity", "affection", "activity", "confidence")


def load_style_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _bounded(value, default=50.0):
    result = float(value if value is not None else default)
    if not math.isfinite(result):
        raise ValueError("Persona values must be finite")
    return min(100.0, max(0.0, result))


def build_style(personality: dict, short_term: dict, stages: dict | None = None) -> dict:
    """Build continuous controls plus concrete structural Korean instructions.

    With persisted stages, the growth engine's hysteresis is retained. A fresh
    preview has no preceding stage and therefore uses the initial thresholds.
    This function is pure: it does not mutate the supplied character or database.
    """
    from .persona_engine import personality_stages, validate_short_term

    cfg = load_style_config()
    short_term = validate_short_term(short_term)
    values = {axis: _bounded(personality.get(axis), cfg["default"]) for axis in AXES}
    applied_stages = personality_stages(values, stages)
    controls = {}
    for field, weights in cfg["field_weights"].items():
        controls[field] = round(sum(
            weight * (cfg["stage_weight"] * cfg["stage_values"][applied_stages[axis]]
                      + cfg["continuous_weight"] * values[axis] / 100)
            for axis, weight in weights.items()) / sum(weights.values()), 4)
    mood = short_term["mood"]
    energy = short_term["energy"]
    stress = short_term["recent_stress"]
    motivation = short_term["recent_motivation"]
    tired = (energy <= cfg["short_term"]["low_energy"]
             or stress >= cfg["short_term"]["high_stress"]
             or mood in {"tired", "low", "sad", "stressed"})
    if tired or motivation <= cfg["short_term"]["low_motivation"]:
        controls["initiative"] = round(controls["initiative"] * cfg["short_term"]["initiative_multiplier"], 4)
        controls["encouragement_strength"] = round(
            controls["encouragement_strength"] * cfg["short_term"]["encouragement_multiplier"], 4)

    def band(score):
        return ("low" if score < cfg["low_threshold"] else
                "high" if score >= cfg["high_threshold"] else "medium")

    guidance = [cfg["axis_guidance"][axis][applied_stages[axis]] for axis in AXES]
    question_budget = cfg["question_budgets"][band(controls["question_frequency"])]
    sentence_budget = cfg["sentence_budgets"][band(controls["sentence_length"])]
    if controls["assertiveness"] >= cfg["high_threshold"]:
        structure = ["답 또는 추천의 결론", "이유 또는 짧은 실행 순서"]
    elif controls["warmth"] >= cfg["high_threshold"]:
        structure = ["사용자의 구체적인 말에 감정 반응", "질문에 대한 답", "함께할 선택 또는 지지"]
    elif controls["novelty_interest"] >= cfg["high_threshold"]:
        structure = ["핵심 답", "새 관점 또는 대안 비교", "선호에 관한 구체적 질문"]
    else:
        structure = ["핵심 답", "필요하면 선택 사항 한 가지"]
    if tired:
        guidance.append("현재는 기운이 낮거나 스트레스가 있는 상태다. 친근함을 낮추지 말고 속도를 늦춰 짧게 답한다. 새 활동보다 쉬거나 부담을 줄이는 선택을 우선한다.")
        sentence_budget = min(sentence_budget, cfg["sentence_budgets"]["medium"])
    if mood == "proud":
        guidance.append("뿌듯한 기분을 한 문장에 담을 수 있지만 어떤 행동이 완료됐는지는 검증된 기록이 있을 때만 말한다.")
    guidance.append(f"문장 구조: {' → '.join(structure)}. 기본 {sentence_budget}문장 이내, 불필요한 반복 인사 없이 작성한다.")
    guidance.append(f"응답당 질문 상한은 {question_budget}개다. 0개일 때도 안전이나 요청 수행에 꼭 필요한 확인 질문은 허용한다.")
    return {
        **controls,
        "question_budget": question_budget,
        "sentence_budget": sentence_budget,
        "response_structure": structure,
        "guidance": guidance,
        "constraints": list(cfg["constraints"]),
        "stages": applied_stages,
        "short_term": {"mood": mood, "energy": energy, "recent_stress": stress, "recent_motivation": motivation},
        "version": cfg["version"],
    }


def style_prompt(profile: dict) -> str:
    """Serialize the real controls and instructions for a model prompt."""
    cfg = load_style_config()
    controls = {field: profile[field] for field in cfg["field_weights"]}
    return ("[계산된 말투 profile]\n" + json.dumps(controls, ensure_ascii=False)
            + "\n" + "\n".join("- " + line for line in profile["guidance"])
            + "\n[고정 사실·안전 규칙]\n"
            + "\n".join("- " + line for line in profile["constraints"]))
