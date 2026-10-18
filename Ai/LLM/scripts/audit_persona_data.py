"""Read-only audit of preserved Persona datasets; writes only new audit artifacts.

Run from Windows: .venv/Scripts/python.exe scripts/audit_persona_data.py --semantic
Semantic metrics use the already-installed BGE-M3 on CPU, local_files_only=True.
No training, data edits, generated examples, model download, DB, or paid API.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import itertools
import json
import math
import re
import statistics
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AXES = ("curiosity", "affection", "activity", "confidence")
LEGACY = ("sociability", "initiative", "playfulness", "courtesy", "bluntness", "roughness", "bond")
PHRASES = ("그랬구나", "괜찮아", "천천히", "흥", "젠장", "기록", "확인", "같이", "잠깐", "몽글이")
VERSION_NAMES = ("pilot_v1", "pilot_v2", "improvement_v1", "improvement_v2", "improvement_v3")


def stable(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize(text):
    return "".join(c for c in unicodedata.normalize("NFKC", text).lower() if c.isalnum())


def words(text):
    # Eojeol-like lexical tokens, NOT a Korean morphological analyzer or model tokenizer.
    return re.findall(r"[\w]+", unicodedata.normalize("NFKC", text).lower())


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?。！？])\s*|\n+", text) if s.strip()]


def stage(value):
    for boundary, label in ((25, "very_low"), (40, "low"), (60, "medium"), (75, "high")):
        if value < boundary:
            return label
    return "very_high"


def extract_rows(path):
    if path.suffix == ".jsonl":
        raw = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw = raw.get("cases", []) if isinstance(raw, dict) else raw
    if not isinstance(raw, list):
        return []
    result = []
    for i, row in enumerate(raw):
        if not isinstance(row, dict) or "user_text" not in row:
            continue
        answer = row.get("answer") or row.get("expect", {}).get("answer") or {}
        speech = answer.get("speech") or row.get("expect", {}).get("reference")
        result.append({
            "id": row.get("sample_id", row.get("id", str(i + 1))),
            "file": str(path.relative_to(ROOT)).replace("\\", "/"),
            "line_or_index": i + 1,
            "scenario_group": row.get("scenario_group", row.get("source_id", "unknown")),
            "user_text": row["user_text"], "context": row.get("context", {}),
            "speech": speech, "answer": answer, "expect": row.get("expect", {}),
            "review": row.get("review", {}), "stored_token_count": row.get("token_count"),
        })
    return result


def ref(row):
    return {k: row[k] for k in ("id", "file", "line_or_index", "user_text", "speech")}


def groups_for(rows, key):
    groups = collections.defaultdict(list)
    for row in rows:
        value = key(row)
        if value is not None:
            groups[value].append(row)
    repeated = [group for group in groups.values() if len(group) > 1]
    return {"groups": len(repeated), "records_in_groups": sum(map(len, repeated)),
            "extra_records": sum(len(g) - 1 for g in repeated),
            "pairs": sum(len(g) * (len(g) - 1) // 2 for g in repeated),
            "examples": [[ref(r) for r in g] for g in sorted(repeated, key=len, reverse=True)[:30]]}


def summary_stats(values):
    return {"count": len(values), "min": min(values), "max": max(values),
            "mean": statistics.mean(values), "median": statistics.median(values)} if values else {
                "count": 0, "min": None, "max": None, "mean": None, "median": None}


def structure(text):
    labels = []
    for s in sentences(text):
        if "?" in s or re.search(r"(할까|줄래|있니|어때)[.!]?$", s):
            labels.append("question")
        elif re.search(r"(어려|못 해|할 수 없|불가|않을게|없어|없어요)", s):
            labels.append("boundary_or_absence")
        elif re.search(r"(괜찮|해도 돼|해도 좋아|하지 않아도|쉬어)", s):
            labels.append("permission_or_rest")
        elif re.search(r"(해 보|해보|하자|보자|챙겨|멈춰|풀어)", s):
            labels.append("suggestion")
        elif re.search(r"(겠|구나|했네|졌네|였네)", s):
            labels.append("acknowledgment")
        else:
            labels.append("statement")
    return " > ".join(labels)


def category_flags(row):
    text = row["user_text"] + " " + row["scenario_group"]
    c = row["context"]
    flags = {
        "exercise": bool(re.search(r"운동|걸음|산책|스트레칭|달리|수영|요가|걷|walk|exercise|activity|steps", text)),
        "food": bool(re.search(r"음식|식사|먹|칼로리|영양|샐러드|치킨|밥|food|meal|nutrition|photo", text)),
        "quest": bool(re.search(r"퀘스트|보상|수락|quest|reward", text)) or bool(c.get("candidates") or c.get("active_quests")),
        "memory": bool(c.get("memories")) or bool(re.search(r"기억|내 취향|내 별명|정정|삭제|memory|mem_|pref_", text)),
        "refusal": bool(re.search(r"거절|싫|그만|하지 마|대신|대행|refus|declin|assignment|cheat|inject", text)),
    }
    flags["daily_other"] = not any(flags.values())
    return flags


def correlations(rows):
    result = []
    answered = [r for r in rows if r["speech"]]
    for axis in AXES + LEGACY:
        selected = [r for r in answered if isinstance(r["context"].get("traits", {}).get(axis), (int, float))]
        if len(selected) < 5:
            continue
        for phrase in PHRASES:
            a = sum(r["context"]["traits"][axis] >= 70 and phrase in r["speech"] for r in selected)
            b = sum(r["context"]["traits"][axis] >= 70 and phrase not in r["speech"] for r in selected)
            c = sum(r["context"]["traits"][axis] < 70 and phrase in r["speech"] for r in selected)
            d = len(selected) - a - b - c
            denominator = math.sqrt((a+b)*(c+d)*(a+c)*(b+d))
            if denominator and a+c >= 3:
                result.append({"axis": axis, "threshold": 70, "phrase": phrase,
                               "phi": (a*d-b*c)/denominator, "high_phrase": a,
                               "high_total": a+b, "other_phrase": c, "other_total": c+d})
    return sorted(result, key=lambda r: abs(r["phi"]), reverse=True)[:30]


def contrast_audit(rows):
    groups = collections.defaultdict(list)
    for r in rows:
        c = dict(r["context"])
        c.pop("traits", None)
        c.pop("personality", None)
        groups[stable([r["user_text"], c])].append(r)
    pairs = []
    current_counts = collections.Counter()
    for group in groups.values():
        for a, b in itertools.combinations(group, 2):
            ta, tb = a["context"].get("traits", {}), b["context"].get("traits", {})
            diff = sorted(axis for axis in set(ta) | set(tb) if ta.get(axis) != tb.get(axis))
            if not diff:
                continue
            if len(diff) == 1 and diff[0] in AXES and a["speech"] and b["speech"]:
                current_counts[diff[0]] += 1
            pairs.append({"a": ref(a), "b": ref(b), "changed_axes": diff,
                          "both_have_answers": bool(a["speech"] and b["speech"]),
                          "answers_differ": bool(a["speech"] and b["speech"] and a["speech"] != b["speech"])})
    same_user = collections.defaultdict(list)
    for r in rows:
        same_user[r["user_text"]].append(r)
    broad = sum(1 for g in same_user.values() if len({stable(r["context"].get("traits", {})) for r in g}) > 1)
    return {"same_user_groups_with_different_traits_including_confounds": broad,
            "controlled_trait_only_pairs": len(pairs),
            "controlled_pairs_with_answers": sum(p["both_have_answers"] for p in pairs),
            "controlled_pairs_with_changed_answers": sum(p["answers_differ"] for p in pairs),
            "current_single_axis_supervised_pairs": {a: current_counts[a] for a in AXES},
            "pairs": pairs}


def audit_corpus(rows, tokenizer):
    answered = [r for r in rows if r["speech"]]
    axis_stats = {}
    for axis in AXES + LEGACY:
        vals = [r["context"].get("traits", r["context"].get("personality", {})).get(axis) for r in rows]
        vals = [v for v in vals if isinstance(v, (int, float))]
        axis_stats[axis] = {**summary_stats(vals), "missing": len(rows)-len(vals),
                            "stages": dict(collections.Counter(stage(v) for v in vals)),
                            "values": dict(collections.Counter(vals))}
    tokens = [words(r["speech"]) for r in answered]
    unigrams = [t for row in tokens for t in row]
    bigrams = [pair for row in tokens for pair in zip(row, row[1:])]
    phrase_counts = {p: {"records": sum(p in r["speech"] for r in answered),
                          "occurrences": sum(r["speech"].count(p) for r in answered)} for p in PHRASES}
    category_count = collections.Counter(k for row in rows for k, active in category_flags(row).items() if active)
    return {
        "records": len(rows), "records_with_reference_speech": len(answered),
        "axis_statistics": axis_stats,
        "legacy_trait_combinations": dict(collections.Counter(stable(r["context"].get("traits", {})) for r in rows)),
        "stage_combinations": dict(collections.Counter(stable({a: stage(v) for a,v in r["context"].get("traits", {}).items()}) for r in rows)),
        "scenario_groups": dict(collections.Counter(r["scenario_group"] for r in rows)),
        "heuristic_multilabel_categories": {k: {"count": category_count[k], "fraction": category_count[k]/len(rows) if rows else 0}
                                             for k in ("exercise", "food", "quest", "memory", "refusal", "daily_other")},
        "duplicates": {
            "exact_user": groups_for(rows, lambda r: r["user_text"]),
            "normalized_user": groups_for(rows, lambda r: normalize(r["user_text"])),
            "exact_speech": groups_for(rows, lambda r: r["speech"]),
            "exact_answer_object": groups_for(rows, lambda r: stable(r["answer"]) if r["answer"] else None),
            "normalized_speech": groups_for(rows, lambda r: normalize(r["speech"]) if r["speech"] else None),
            "exact_context_user": groups_for(rows, lambda r: stable([r["context"], r["user_text"]])),
        },
        "response_metrics": {
            "tokenizer": "local Qwen3.5 tokenizer; speech only; add_special_tokens=False" if tokenizer else "unavailable",
            "qwen_token_counts": summary_stats([len(tokenizer.encode(r["speech"], add_special_tokens=False)) for r in answered]) if tokenizer else None,
            "lexical_word_counts": summary_stats(list(map(len, tokens))),
            "sentence_counts": summary_stats([len(sentences(r["speech"])) for r in answered]),
            "distinct_1": len(set(unigrams))/len(unigrams) if unigrams else None,
            "distinct_2": len(set(bigrams))/len(bigrams) if bigrams else None,
            "distinct_definition": "Unicode word/eojeol-like tokens; bigrams within response only; not morphology",
            "top_start_1_word": collections.Counter(" ".join(t[:1]) for t in tokens).most_common(20),
            "top_start_2_words": collections.Counter(" ".join(t[:2]) for t in tokens).most_common(20),
            "structure_proxy_counts": dict(collections.Counter(structure(r["speech"]) for r in answered)),
            "structure_proxy_caveat": "Regex speech-act sequence, not syntactic parsing or human quality judgment",
            "phrase_counts": phrase_counts,
            "questions": sum("?" in r["speech"] for r in answered),
        },
        "phrase_trait_associations": correlations(rows),
        "contrast": contrast_audit(rows),
        "human_reviewed": sum(r["review"].get("human") in ("reviewed", "approved", True) for r in rows),
    }


def lexical_matrix(texts):
    import numpy as np
    counts = [collections.Counter(normalize(t)[i:i+3] for i in range(max(len(normalize(t))-2, 0))) for t in texts]
    vocab = sorted(set().union(*(set(c) for c in counts)))
    indices = {v: i for i, v in enumerate(vocab)}
    x = np.zeros((len(texts), len(vocab)), dtype=np.float32)
    df = collections.Counter(k for c in counts for k in c)
    for i, c in enumerate(counts):
        for token, count in c.items():
            x[i, indices[token]] = (1+math.log(count))*(math.log((len(texts)+1)/(df[token]+1))+1)
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)


def pair_metrics(rows, vectors, threshold, include_pairs=50):
    import numpy as np
    scores = vectors @ vectors.T
    ii, jj = np.triu_indices(len(rows), 1)
    values = scores[ii, jj]
    ranking = np.argsort(values)[::-1]
    top = [{"similarity": float(values[k]), "a": ref(rows[int(ii[k])]), "b": ref(rows[int(jj[k])]),
            "same_normalized_text": normalize(rows[int(ii[k])]["_text"]) == normalize(rows[int(jj[k])]["_text"])}
           for k in ranking[:include_pairs]]
    qualifying = np.flatnonzero(values >= threshold)
    nonidentical = [k for k in ranking if normalize(rows[int(ii[k])]["_text"]) != normalize(rows[int(jj[k])]["_text"])]
    top_nonidentical = [{"similarity": float(values[k]), "a": ref(rows[int(ii[k])]), "b": ref(rows[int(jj[k])])}
                        for k in nonidentical[:include_pairs]]
    return {"records": len(rows), "pairs": len(values), "mean_pairwise_similarity": float(values.mean()) if len(values) else None,
            "threshold": threshold, "pairs_above_threshold": len(qualifying), "top_pairs": top,
            "top_nonidentical_pairs": top_nonidentical}, scores


def leakage(version_rows, kind="exact"):
    result = []
    for a_name, b_name in itertools.combinations(version_rows, 2):
        a, b = version_rows[a_name], version_rows[b_name]
        fields = {
            "exact_user": lambda r: r["user_text"],
            "normalized_user": lambda r: normalize(r["user_text"]),
            "exact_speech": lambda r: r["speech"],
            "exact_answer_object": lambda r: stable(r["answer"]) if r["answer"] else None,
            "normalized_speech": lambda r: normalize(r["speech"]) if r["speech"] else None,
            "exact_input_context": lambda r: stable([r["user_text"], r["context"]]),
            "scenario_group": lambda r: r["scenario_group"] if r["scenario_group"] != "unknown" else None,
        }
        checks = {}
        for label, function in fields.items():
            av, bv = collections.defaultdict(list), collections.defaultdict(list)
            for row in a:
                key = function(row)
                if key is not None:
                    av[key].append(row)
            for row in b:
                key = function(row)
                if key is not None:
                    bv[key].append(row)
            overlap = av.keys() & bv.keys()
            checks[label] = {"shared_values": len(overlap), "cross_split_pairs": sum(len(av[k])*len(bv[k]) for k in overlap),
                             "examples": [{"value": k, "a_ids": [r["id"] for r in av[k]], "b_ids": [r["id"] for r in bv[k]]}
                                          for k in sorted(overlap)[:20]]}
        result.append({"a_split": a_name, "b_split": b_name, "checks": checks})
    return result


def semantic_embeddings(texts, output):
    import numpy as np
    import torch
    from transformers import AutoModel, AutoTokenizer
    torch.set_num_threads(6)
    path = ROOT / "models/bge-m3"
    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
    model = AutoModel.from_pretrained(path, local_files_only=True).eval().cpu()
    embeddings = []
    truncated = 0
    for start in range(0, len(texts), 16):
        part = texts[start:start+16]
        lengths = [len(tokenizer.encode(s, add_special_tokens=True)) for s in part]
        truncated += sum(n > 256 for n in lengths)
        batch = tokenizer(part, padding=True, truncation=True, max_length=256, return_tensors="pt")
        with torch.inference_mode():
            value = model(**batch).last_hidden_state[:, 0]
            embeddings.append(torch.nn.functional.normalize(value, p=2, dim=1).cpu().numpy())
        print(f"BGE CPU {min(start+16,len(texts))}/{len(texts)}", flush=True)
    array = np.concatenate(embeddings)
    np.save(output / "bge_unique_embeddings.npy", array)
    dump(output / "bge_unique_texts.json", texts)
    return array, {"status": "completed", "model": str(path), "device": "cpu", "dtype": str(next(model.parameters()).dtype),
                   "model_config_sha256": hashlib.sha256((path / "config.json").read_bytes()).hexdigest(),
                   "pooling": "normalized last_hidden_state CLS",
                   "max_length": 256, "truncated_texts": truncated, "unique_texts": len(texts), "seed": 42}


def kmeans(vectors, k=8):
    import numpy as np
    rng = np.random.default_rng(42)
    centers = vectors[rng.choice(len(vectors), size=k, replace=False)].copy()
    assignments = np.zeros(len(vectors), dtype=np.int64)
    iterations = 0
    for iterations in range(1, 101):
        new = np.argmax(vectors @ centers.T, axis=1)
        if iterations > 1 and np.array_equal(assignments, new):
            break
        assignments = new
        for i in range(k):
            if np.any(assignments == i):
                c = vectors[assignments == i].mean(axis=0)
                centers[i] = c / max(np.linalg.norm(c), 1e-12)
    return assignments, centers, iterations


def quality_candidates(rows):
    result = []
    for row in rows:
        speech = row["speech"]
        if not speech:
            continue
        c, answer = row["context"], row["answer"]
        flags = []
        if c.get("settings", {}).get("profanity") == "none" and re.search("젠장|씨발|시발|씨벅", speech):
            flags.append("profanity_none_conflict")
        if answer.get("personality_update") is not None:
            flags.append("model_generated_personality_update")
        offered = answer.get("action", {}).get("type") == "offer_quest"
        target = answer.get("action", {}).get("target_id")
        ids = {x.get("id", x.get("quest_id")) for x in c.get("candidates", [])}
        if offered and target not in ids:
            flags.append("offer_not_in_candidates")
        memory_ids = {x.get("id") for x in c.get("memories", [])}
        if any(i not in memory_ids for i in answer.get("memory_ids", [])):
            flags.append("unknown_memory_id")
        if re.search(r"(완료했|완료됐|완료된|보상.*(받았|지급됐|지급했|줄게))", speech):
            flags.append("completion_or_reward_assertion_review")
        if re.search(r"(기억하고 있어|기억해|했었|했지|했어\.)", speech) and not c.get("memories") and not c.get("recent") and not c.get("activities"):
            flags.append("unsupported_past_statement_review")
        if c.get("settings", {}).get("speech_level") == "casual" and re.search(r"(세요|해요|어요|습니다)[.!?]", speech):
            flags.append("casual_context_formal_speech_review_assignment_exception_possible")
        if flags:
            result.append({**ref(row), "flags": flags, "context": c, "answer": answer})
    return {"status": "heuristic_candidates_only_not_confirmed_errors", "candidates": result,
            "flag_counts": dict(collections.Counter(f for r in result for f in r["flags"]))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--semantic", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "runs/persona-audit-20261001")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "runs"):
        raise ValueError("Audit output must be inside this project's runs directory")
    output.mkdir(parents=True, exist_ok=True)
    started = time.time()
    originals = sorted(p for p in (ROOT / "data").rglob("*") if p.is_file())
    before = {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}
    dump(output / "preservation-before.json", before)
    inventory = []
    for path in originals:
        rows = extract_rows(path) if path.suffix in (".json", ".jsonl") else []
        ancillary = {}
        if path.suffix == ".json":
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                ancillary = {"top_level_entries": len(raw), "turns": sum(len(r.get("turns", [])) for r in raw if isinstance(r, dict))}
            elif isinstance(raw, dict):
                ancillary = {"list_field_counts": {k: len(v) for k,v in raw.items() if isinstance(v, list)}}
        inventory.append({"file": str(path.relative_to(ROOT)).replace("\\", "/"), "bytes": path.stat().st_size,
                          "recognized_user_text_records": len(rows), "reference_speech_count": sum(bool(r["speech"]) for r in rows), **ancillary,
                          "sha256": before[str(path.relative_to(ROOT)).replace("\\", "/")]})
    dump(output / "inventory.json", inventory)
    tokenizer, tokenizer_error = None, None
    try:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(ROOT / "models/qwen3.5-9b", local_files_only=True)
    except Exception as exc:
        tokenizer_error = repr(exc)
    versions, raw_versions = {}, {}
    for version in VERSION_NAMES:
        splits = {}
        for split, name in (("train", "train.jsonl"), ("validation", "validation.jsonl"), ("test", "final-frozen.json")):
            path = ROOT / "data" / version / name
            if path.exists():
                splits[split] = extract_rows(path)
        raw_versions[version] = splits
        versions[version] = {"splits": {k: audit_corpus(v, tokenizer) for k, v in splits.items()},
                             "split_overlap": leakage(splits)}
        print(f"Audited {version}: {[(k,len(v)) for k,v in splits.items()]}", flush=True)
    dump(output / "versions.json", versions)
    latest = [dict(r, split=split) for split, rows in raw_versions["improvement_v3"].items() for r in rows]
    dump(output / "current-quality-candidates.json", quality_candidates(latest))
    similarities = {"scope": "improvement_v3 only; includes 58 test inputs without reference answers", "lexical": {}, "semantic": {}}
    semantic_status = {"status": "not_requested"}
    all_canonical = [r for splits in raw_versions.values() for rows in splits.values() for r in rows]
    texts = sorted({r["user_text"] for r in all_canonical} | {r["speech"] for r in all_canonical if r["speech"]})
    semantic, text_index = None, {t: i for i,t in enumerate(texts)}
    if args.semantic:
        try:
            semantic, semantic_status = semantic_embeddings(texts, output)
        except Exception as exc:
            semantic_status = {"status": "failed", "reason": repr(exc), "device_requested": "cpu"}
    for field in ("user_text", "speech"):
        selected = [dict(r, _text=r[field]) for r in latest if r[field]]
        vectors = lexical_matrix([r[field] for r in selected])
        metric, scores = pair_metrics(selected, vectors, 0.80)
        metric["method"] = "NFKC normalized alphanumeric character trigram TF-IDF cosine"
        metric["cross_split_high_similarity"] = [{"similarity": float(scores[i,j]), "a_split": a["split"], "b_split": b["split"],
                                                  "a": ref(a), "b": ref(b)} for i,a in enumerate(selected) for j,b in enumerate(selected)
                                                  if i < j and a["split"] != b["split"] and scores[i,j] >= .80]
        similarities["lexical"][field] = metric
        if field == "speech":
            metric["same_user_different_context_near_answer_pairs"] = [{"similarity": float(scores[i,j]), "a": ref(a), "b": ref(b)}
                for i,a in enumerate(selected) for j,b in enumerate(selected) if i < j and a["user_text"] == b["user_text"]
                and a["context"] != b["context"] and scores[i,j] >= .80]
        if semantic is not None:
            vectors = semantic[[text_index[r[field]] for r in selected]]
            metric, scores = pair_metrics(selected, vectors, .92)
            metric["cross_split_high_similarity"] = [{"similarity": float(scores[i,j]), "a_split": a["split"], "b_split": b["split"],
                                                       "a": ref(a), "b": ref(b)} for i,a in enumerate(selected) for j,b in enumerate(selected)
                                                       if i < j and a["split"] != b["split"] and scores[i,j] >= .92]
            labels, centers, iterations = kmeans(vectors)
            metric["clusters"] = {"method": "spherical k-means, k=8, seed=42; exploratory not semantic ground truth", "iterations": iterations,
                                   "counts": dict(collections.Counter(str(int(i)) for i in labels)),
                                   "members": [{"cluster": int(labels[i]), **ref(r)} for i,r in enumerate(selected)]}
            similarities["semantic"][field] = metric
            if field == "speech":
                metric["same_user_different_context_near_answer_pairs"] = [{"similarity": float(scores[i,j]), "a": ref(a), "b": ref(b)}
                    for i,a in enumerate(selected) for j,b in enumerate(selected) if i < j and a["user_text"] == b["user_text"]
                    and a["context"] != b["context"] and scores[i,j] >= .92]
    similarities["semantic_status"] = semantic_status
    dump(output / "similarities.json", similarities)
    historical_similarities = {}
    for version, splits in raw_versions.items():
        historical_similarities[version] = {}
        vv_rows = [dict(r, split=split) for split, rows in splits.items() for r in rows]
        for field in ("user_text", "speech"):
            selected = [dict(r, _text=r[field]) for r in vv_rows if r[field]]
            methods = {"lexical": (lexical_matrix([r[field] for r in selected]), .80)}
            if semantic is not None:
                methods["semantic"] = (semantic[[text_index[r[field]] for r in selected]], .92)
            historical_similarities[version][field] = {}
            for method, (vectors, threshold) in methods.items():
                metric, scores = pair_metrics(selected, vectors, threshold, include_pairs=20)
                metric["cross_split_high_similarity"] = [{"similarity": float(scores[i,j]), "a_split": a["split"], "b_split": b["split"],
                    "a": ref(a), "b": ref(b)} for i,a in enumerate(selected) for j,b in enumerate(selected)
                    if i < j and a["split"] != b["split"] and scores[i,j] >= threshold]
                historical_similarities[version][field][method] = metric
    dump(output / "historical-similarities.json", historical_similarities)
    all_supervised = [r for splits in raw_versions.values() for rows in splits.values() for r in rows if r["speech"]]
    cross_version = {"sum_supervised_version_rows": len(all_supervised),
                     "unique_context_user_answer": len({stable([r["context"], r["user_text"], r["answer"]]) for r in all_supervised}),
                     "unique_user_speech": len({stable([r["user_text"], r["speech"]]) for r in all_supervised}),
                     "duplicate_bytes": [[a["file"], b["file"]] for a,b in itertools.combinations(inventory,2) if a["sha256"] == b["sha256"]],
                     "warning": "Version totals are historical copies, not independent examples. Former validation was intentionally promoted to train."}
    dump(output / "cross-version.json", cross_version)
    after = {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}
    preservation = {"files_checked": len(before), "before": before, "after": after, "unchanged": before == after,
                    "added_source_files": sorted(str(p.relative_to(ROOT)) for p in (ROOT / "data").rglob("*") if p.is_file() and p not in originals)}
    dump(output / "preservation.json", preservation)
    meta = {"elapsed_seconds": time.time()-started, "semantic": semantic_status, "tokenizer_error": tokenizer_error,
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "preserved": before == after, "report_data": "versions.json, similarities.json, inventory.json, current-quality-candidates.json, cross-version.json",
            "limitations": ["No human annotation; content contradiction candidates require review", "No four-axis data present; do not map legacy fields to fabricate coverage",
                            "Semantic thresholds are candidate triage, not proof of leakage", "Test has no reference outputs; response metrics exclude it",
                            "No Qwen inference or LoRA evaluation in this audit; see separate real-model evaluation"]}
    dump(output / "summary.json", meta)
    print(json.dumps(meta, ensure_ascii=False), flush=True)
    if before != after:
        raise RuntimeError("Preserved source data changed during audit")


if __name__ == "__main__":
    main()
