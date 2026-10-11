"""Read-only A/B observations, explicitly not a semantic grading model.

Counts and phrase matches are lexical proxies. They neither establish that a
personality was expressed sufficiently nor certify factual correctness. The
original speech, fixed catalog context, and provenance accompany review cues.
"""
from __future__ import annotations

import copy
import json
import re
from collections import Counter
from difflib import SequenceMatcher


VERSION = "persona-comparison.v1"
STYLE_FIELDS = (
    "question_frequency", "warmth", "initiative", "assertiveness", "sentence_length",
    "emotional_expression", "novelty_interest", "encouragement_strength",
    "question_budget", "sentence_budget", "response_structure",
)
PATTERNS = {
    "question": r"[^.!?\n]*(?:\?|궁금(?:해|하|한)|알려\s*줘|어떤|어떻게|무엇|왜)[^.!?\n]*[.!?]?",
    "warmth": r"함께|같이|고마[워운]|반가[워운]|기쁘|좋았|소중|곁|챙겨|응원|네\s*편",
    "initiative": r"해\s*보자|시작|추천|제안|첫\s*단계|먼저|움직|도전",
    "assertiveness": r"추천해|선택하자|시작하자|하면\s*돼|하는\s*게\s*좋|먼저.*?[.!?]|분명|확실",
    "tentativeness": r"괜찮다면|원하면|혹시|아마|같아|해도\s*돼|해\s*볼까|어떨까|모르|몰라|확인.*?필요",
    "emotional_expression": r"기쁘|즐거|속상|뿌듯|신나|마음|좋아|무거워|지쳤|짜증",
    "recurrent_phrase": r"그랬구나|괜찮아|천천히|편하게|수용해|검증된|흥|쳇",
}
NUMERIC_CUE = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>걸음|분|시간|개|회|점|kcal|칼로리)")
UNITS = {"steps": "걸음", "minutes": "분", "records": "개", "groups": "개", "foods": "개"}


def _matches(pattern: str, speech: str) -> list[str]:
    return list(dict.fromkeys(match.group(0).strip() for match in re.finditer(pattern, speech)))[:8]


def _features(speech: str) -> dict:
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s*|\n+", speech) if x.strip()]
    normalized = [re.sub(r"\s+", " ", s).strip(" .!?") for s in sentences]
    return {
        "question_marks": speech.count("?"),
        "characters": len(speech),
        "lexical_cues": {key: _matches(pattern, speech) for key, pattern in PATTERNS.items()},
        "sentence_structure": {
            "sentence_count": len(sentences),
            "sentence_lengths": [len(s) for s in sentences],
            "opening": sentences[0][:70] if sentences else "",
            "sentences": sentences[:6],
        },
        "repetition": {"repeated_sentences": [s for s, count in Counter(normalized).items() if count > 1]},
        "numeric_unit_mentions": [{"text": m.group(0), "value": m.group("value"), "unit": m.group("unit")}
                                  for m in NUMERIC_CUE.finditer(speech)],
    }


def _changes(before: dict, after: dict, fields=None) -> list:
    return [{"field": key, "before": copy.deepcopy(before.get(key)), "after": copy.deepcopy(after.get(key))}
            for key in (fields or sorted(set(before) | set(after))) if before.get(key) != after.get(key)]


def _candidate_summary(context: dict) -> list:
    return [{"quest_id": q.get("quest_id", q.get("id")), "title": q.get("title"),
             "difficulty": q.get("difficulty"), "goal": copy.deepcopy(q.get("goal", {}))}
            for q in context.get("candidates", [])]


def _voice(context: dict) -> str:
    metadata = context.get("style_profile", {}).get("character_voice", {})
    return context.get("character_voice", metadata.get("id", "default") if isinstance(metadata, dict) else "default")


def _provenance(context: dict) -> dict:
    activities = context.get("activities", [])
    memories = context.get("memories", [])
    return {
        "activity_event_ids": [x["event_id"] for x in activities if x.get("event_id")],
        "verified_activity_records": sum(x.get("verification_status") == "verified" for x in activities),
        "synthetic_activity_records": sum(x.get("source") == "simulation" for x in activities),
        "memory_ids": [x["id"] for x in memories if x.get("id")],
        "memory_sources": [{"id": x.get("id"), "source_id": x.get("source_id"),
                            "verification_status": x.get("verification_status", "unknown")} for x in memories],
        "unverified_report_count": len(context.get("unverified_reports", [])),
        "note": "활동 event_id와 memory id는 서로 다른 참조입니다. simulation의 verified는 실제 운동 인증을 뜻하지 않습니다.",
    }


def _prompt_input(messages) -> str | None:
    for message in messages or []:
        if message.get("role") != "user":
            continue
        try:
            parsed = json.loads(message.get("content", ""))
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("user_text"), str):
            return parsed["user_text"]
    return None


def _output(result: dict) -> dict:
    output = result.get("output", {})
    if hasattr(output, "model_dump"):
        output = output.model_dump()
    return output


def _origin(result: dict) -> str:
    if result.get("metrics", {}).get("fallback"):
        return "fallback"
    return result.get("output_origin", "dummy" if result.get("mode") == "dummy" else "unknown")


def _review_cues(side: str, output: dict, features: dict, context: dict) -> list:
    speech = str(output.get("speech", ""))
    cues = []

    def add(kind, reason, **evidence):
        cues.append({"side": side, "type": kind, "status": "human_review_needed", "reason_ko": reason,
                     "speech": speech, **evidence})

    action = output.get("action") or {}
    target = action.get("target_id")
    candidates = context.get("candidates", [])
    if action.get("type") == "offer_quest":
        quest = next((q for q in candidates if target in (q.get("id"), q.get("quest_id"))), None)
        if quest is None:
            add("unlisted_action_target", "제안 action ID가 제공된 후보 목록에 없습니다. 원문과 검증 결과를 확인하세요.", target_id=target,
                candidate_ids=[q.get("id", q.get("quest_id")) for q in candidates])
        elif features["numeric_unit_mentions"]:
            goal = quest.get("goal", {})
            unit = UNITS.get(goal.get("unit"))
            # Numeric differences are review evidence, not an assertion that the
            # goal was altered: speech can describe a first step or another fact.
            different = [m for m in features["numeric_unit_mentions"]
                         if m["unit"] != unit or float(m["value"]) != goal.get("target")]
            if different:
                add("goal_wording_to_review", "대사의 수량·단위와 후보 목표를 함께 확인하세요. 부분 단계나 다른 사실일 수 있어 목표 변형으로 확정하지 않습니다.",
                    mentions=different, catalog_goal=copy.deepcopy(goal), quest_id=quest.get("quest_id", quest.get("id")))
    cited = output.get("memory_ids", [])
    known_memories = {m.get("id") for m in context.get("memories", [])}
    activity_ids = {e.get("event_id") for e in context.get("activities", [])}
    unknown = [identifier for identifier in cited if identifier not in known_memories]
    if unknown:
        add("memory_reference_membership", "출력 memory_ids에 memory 목록에 없는 ID가 있습니다. 활동 event_id를 기억 ID로 사용했는지 구분해 확인하세요.",
            unlisted_memory_ids=unknown, also_activity_event_ids=[identifier for identifier in unknown if identifier in activity_ids])
    claims = _matches(r"[^.!?]*(?:완료|보상|기억하고\s*있|기억해|오늘|매일)[^.!?]*[.!?]?", speech)
    if claims:
        add("fact_or_time_wording", "완료·보상·기억·오늘·매일 표현이 있습니다. 부정문, 과거 인용, 검증된 요약일 수 있으므로 실제 날짜와 근거를 읽어야 합니다.",
            excerpts=claims, as_of=context.get("as_of"),
            activity_dates=[x.get("occurred_at") for x in context.get("activities", [])],
            recent_dates=[x.get("occurred_at") for x in context.get("recent", [])],
            completed_quests=copy.deepcopy(context.get("completed_quests", [])[-3:]))
    implementation = _matches(r"검증된|시뮬레이션|카탈로그|프롬프트|서버\s*규칙|confidence|affection", speech)
    if implementation:
        add("implementation_wording", "내부 처리와 관련된 표현이 보입니다. 사용자 질문상 필요한 설명인지 검토하세요. 정보 유출로 자동 판정하지 않습니다.", excerpts=implementation)
    return cues


def build_comparison_observations(response: dict) -> dict:
    """Summarize a PersonaRuntime.compare response without writes or inference."""
    contexts = response.get("contexts", {})
    a, b = contexts.get("a", {}), contexts.get("b", {})
    prompts = response.get("prompts", {})
    prompt_inputs = {side: _prompt_input(prompts.get(side)) for side in ("a", "b")}
    available_inputs = all(value is not None for value in prompt_inputs.values())
    generation = response.get("generation")
    side_settings = [result[side]["generation"] for result in response.get("results", [])
                     for side in ("a", "b") if isinstance(result.get(side, {}).get("generation"), dict)]
    settings_match = (all(settings == generation for settings in side_settings)
                      if isinstance(generation, dict) and side_settings else None)
    controls = {
        "declared_shared_user_input": response.get("user_text"),
        "prompt_user_input_match": (prompt_inputs["a"] == prompt_inputs["b"] == response.get("user_text")) if available_inputs else None,
        "shared_generation_parameters": copy.deepcopy(generation),
        "side_generation_parameters_match": settings_match,
        "generation_scope": "응답의 공통 생성 설정; 측별 별도 설정이 없으면 실제 실행 파라미터까지 독립 검증한 것은 아닙니다.",
        "memories_equal": a.get("memories", []) == b.get("memories", []),
        "reference_times_equal": a.get("as_of") == b.get("as_of"),
    }
    candidates_a, candidates_b = _candidate_summary(a), _candidate_summary(b)
    changes = {
        "personality": _changes(a.get("personality", {}), b.get("personality", {})),
        "short_term": _changes(a.get("short_term", {}), b.get("short_term", {})),
        "style_profile": _changes(a.get("style_profile", {}), b.get("style_profile", {}), STYLE_FIELDS),
        "character_voice": {"before": _voice(a), "after": _voice(b), "changed": _voice(a) != _voice(b)},
        "candidates": {"changed": candidates_a != candidates_b, "before": candidates_a, "after": candidates_b},
        "activity_context_changed": a.get("activities", []) != b.get("activities", []),
        "recent_conversation_changed": a.get("recent", []) != b.get("recent", []),
    }
    pairs, initial_seeds, openings = [], [], {"a": [], "b": []}
    for row in response.get("results", []):
        item = {"index": row.get("index"), "seed": row.get("seed"), "review_cues": []}
        seed_pair = []
        for side in ("a", "b"):
            result = row.get(side, {})
            output = _output(result)
            speech = str(output.get("speech", ""))
            features = _features(speech)
            origin = _origin(result)
            traces = result.get("raw_attempts", [])
            seed_pair.append(traces[0].get("seed") if traces else None)
            item[side] = {"speech": speech, "output_origin": origin,
                          "exclude_from_model_style_analysis": origin != "qwen",
                          "features": features, "action": copy.deepcopy(output.get("action")),
                          "emotion": output.get("emotion"), "animation": output.get("animation"),
                          "repaired": bool(result.get("metrics", {}).get("repaired")),
                          "final_attempt_seed": traces[-1].get("seed") if traces else None}
            if origin == "qwen":
                item["review_cues"].extend(_review_cues(side, output, features, contexts.get(side, {})))
                openings[side].append(features["sentence_structure"]["opening"])
        match = seed_pair[0] == seed_pair[1] == row.get("seed") if all(s is not None for s in seed_pair) else None
        initial_seeds.append(match)
        item["initial_seed_match"] = match
        item["same_speech"] = item["a"]["speech"] == item["b"]["speech"]
        item["speech_string_similarity"] = round(SequenceMatcher(None, item["a"]["speech"], item["b"]["speech"]).ratio(), 4)
        item["changed_expression_cues"] = _changes(item["a"]["features"]["lexical_cues"], item["b"]["features"]["lexical_cues"])
        pairs.append(item)
    controls["initial_seed_match"] = all(initial_seeds) if initial_seeds and all(s is not None for s in initial_seeds) else None
    warnings = ["자동 수치는 단어·문장 형태의 관측값입니다. 충분한 말투 차이와 사실 정확성은 사람의 맥락 검토가 필요합니다."]
    if controls["prompt_user_input_match"] is not True:
        warnings.append("A/B Prompt의 사용자 입력이 동일한지 확인하지 못했거나 서로 다릅니다.")
    if controls["initial_seed_match"] is not True:
        warnings.append("모든 쌍의 실제 첫 생성 seed 일치를 확인하지 못했거나 서로 다릅니다.")
    if settings_match is False:
        warnings.append("측별 생성 설정이 공통 설정과 다릅니다. 동일 파라미터 대조로 해석하지 마세요.")
    if any(item[side]["repaired"] for item in pairs for side in ("a", "b")):
        warnings.append("수정 생성이 포함되어 최종 대사는 양쪽의 첫 시도와 다른 seed·수정 맥락에서 나왔을 수 있습니다.")
    if any(item[side]["exclude_from_model_style_analysis"] for item in pairs for side in ("a", "b")):
        warnings.append("dummy·fallback·출처 미확인 대사는 실제 모델 말투 분석에서 제외합니다.")
    if changes["candidates"]["changed"]:
        warnings.append("추천 퀘스트도 달라졌습니다. 대사의 내용 변화 전체를 말투 변화로 해석하지 마세요.")
    if changes["activity_context_changed"] or changes["recent_conversation_changed"] or not controls["memories_equal"]:
        warnings.append("활동·대화·기억 맥락도 달라진 비교입니다. 성격만 바꾼 독립 대조가 아닙니다.")
    if not controls["reference_times_equal"]:
        warnings.append("전후 기준 날짜가 다릅니다. 오늘·최근 기록 표현은 각 날짜에 맞게 확인해야 합니다.")
    changed_count = sum(not item["same_speech"] for item in pairs)
    return {
        "version": VERSION, "interpretation": "lexical_proxy_not_semantic_grade", "requires_human_review": True,
        "controls": controls, "context_changes": changes,
        "provenance": {"a": _provenance(a), "b": _provenance(b)}, "pairs": pairs,
        "repeated_openings": {side: [{"opening": start, "count": count} for start, count in Counter(values).items()
                                    if count > 1 and start] for side, values in openings.items()},
        "summary_ko": [f"{len(pairs)}개 쌍 중 {changed_count}개에서 대사 문자열이 달랐습니다. 의미 있는 성격 차이의 성공률은 아닙니다.",
                       f"계산된 style profile의 {len(changes['style_profile'])}개 항목이 달라졌습니다. 실제 대사의 준수 여부는 별도 검토가 필요합니다.",
                       "추천 퀘스트가 달라졌습니다." if changes["candidates"]["changed"] else "추천 퀘스트 목록과 목표는 동일합니다."],
        "warnings": warnings,
    }
