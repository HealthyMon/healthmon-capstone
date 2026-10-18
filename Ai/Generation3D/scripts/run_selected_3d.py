#!/usr/bin/env python3
"""Run only explicitly selected diversity cases through existing 3D adapters.

Selection JSON: {"cases": [{"case_id": "stage2_fit", "image": "fit.png",
"target_stage": 2, "form": "FIT", "rig": true, "seed": 42}, ...]}.
Relative image paths resolve against the selection JSON directory. Exactly three
cases are required: Stage 2 FIT, Stage 2 HEAVY, and one RECOVERY. FIT and at least
one other case must request rigging. --plan-only never launches a subprocess or
writes outputs. --resume reuses complete cases only after verifying fingerprints
and all saved artifact hashes; unsuccessful cases get a new attempt directory.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from healthmon.rigging_runner import blender_command, blender_environment

VIEWS = ("front", "three_quarter", "side", "back")
CODE_FILES = (
    Path(__file__).resolve(), ROOT / "src/healthmon/trellis_runner.py",
    ROOT / "src/healthmon/rigging_runner.py", ROOT / "src/healthmon/blender_tool.py",
    ROOT / "src/healthmon/riganything_blender_entry.py",
)


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def load_runtime(path):
    config = json.loads((ROOT / 'configs/runtime.json').read_text())
    local = ROOT / 'configs/runtime.local.json'
    if local.is_file():
        config.update(json.loads(local.read_text()))
    for name in ('qwen', 'trellis', 'rigging'):
        fragment = ROOT / f'configs/{name}_runtime.json'
        if fragment.is_file():
            config.update(json.loads(fragment.read_text()))
    if Path(path).resolve() != (ROOT / 'configs/runtime.json').resolve():
        config.update(json.loads(Path(path).read_text()))
    def expand(value):
        if isinstance(value, str):
            return os.path.expandvars(os.path.expanduser(value))
        if isinstance(value, dict):
            return {k: expand(v) for k, v in value.items()}
        return value
    config = expand(config)
    unresolved = [k for k,v in config.items() if isinstance(v,str) and '${' in v]
    if unresolved:
        raise ValueError('Configure configs/runtime.local.json or runtime environment: ' + ', '.join(unresolved))
    for key, env in [('matting_python','HEALTHMON_MATTING_PYTHON'), ('matting_checkpoint','HEALTHMON_MATTING_CHECKPOINT')]:
        if config.get(key): os.environ[env] = str(config[key])
    return config


def load_selection(path, default_seed):
    document = json.loads(path.read_text())
    cases = document.get("cases") if isinstance(document, dict) else None
    if not isinstance(cases, list) or len(cases) != 3:
        raise ValueError("Selection must contain exactly three cases")
    resolved, identifiers = [], set()
    for raw in cases:
        if not isinstance(raw, dict):
            raise ValueError("Each selected case must be an object")
        case_id = raw.get("case_id", "")
        if not isinstance(case_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", case_id):
            raise ValueError("case_id must contain only letters, digits, underscores, or hyphens")
        if case_id in identifiers:
            raise ValueError(f"Duplicate case_id: {case_id}")
        identifiers.add(case_id)
        image = Path(raw["image"]).expanduser()
        image = (path.parent / image).resolve() if not image.is_absolute() else image.resolve()
        if not image.is_file():
            raise FileNotFoundError(f"Selected image does not exist: {image}")
        form = str(raw.get("form", "")).upper()
        stage = raw.get("target_stage")
        seed = raw.get("seed", default_seed)
        rig = raw.get("rig", False)
        azimuth = float(raw.get("front_azimuth", 0))
        if type(stage) is not int or stage not in (1, 2, 3):
            raise ValueError(f"{case_id}: target_stage must be 1, 2, or 3")
        if type(seed) is not int or not 0 <= seed < 2**32:
            raise ValueError(f"{case_id}: seed must be an unsigned 32-bit integer")
        if type(rig) is not bool or not math.isfinite(azimuth):
            raise ValueError(f"{case_id}: rig must be boolean and front_azimuth finite")
        resolved.append({**raw, "case_id": case_id, "image": str(image), "form": form,
                         "target_stage": stage, "seed": seed, "rig": rig,
                         "front_azimuth": azimuth, "input_sha256": sha256(image)})
    fit = [c for c in resolved if c["form"] == "FIT" and c["target_stage"] == 2]
    heavy = [c for c in resolved if c["form"] == "HEAVY" and c["target_stage"] == 2]
    recovery = [c for c in resolved if c["form"] == "RECOVERY"]
    if len(fit) != 1 or len(heavy) != 1 or len(recovery) != 1:
        raise ValueError("Select one Stage 2 FIT, one Stage 2 HEAVY, and one RECOVERY")
    if not fit[0]["rig"] or sum(c["rig"] for c in resolved) < 2:
        raise ValueError("Request rigging for FIT and at least one HEAVY or RECOVERY case")
    return resolved


def artifact_records(paths):
    records = []
    for path in map(Path, paths):
        if not path.is_file() or not path.stat().st_size:
            raise RuntimeError(f"Expected nonempty artifact is missing: {path}")
        records.append({"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)})
    return records


def next_attempt(case_root):
    number = 1
    while (case_root / f"attempt_{number:03d}").exists():
        number += 1
    return case_root / f"attempt_{number:03d}"


def reusable_result(case_root, fingerprint):
    for path in sorted(case_root.glob("attempt_*/case_result.json"), reverse=True):
        try:
            result = json.loads(path.read_text())
            records = [a for stage in result["stages"].values() for a in stage.get("artifacts", [])]
            if result.get("status") != "PASS" or result.get("fingerprint") != fingerprint or not records:
                continue
            if all(Path(a["path"]).is_file() and Path(a["path"]).stat().st_size == a["bytes"]
                   and sha256(a["path"]) == a["sha256"] for a in records):
                return {**result, "reused": True}
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def commands_for(case, attempt, config_path, config, size):
    tool = ROOT / "src/healthmon/blender_tool.py"
    model = attempt / "trellis/model.glb"
    blender = config.get("blender")
    if not blender:
        raise ValueError("Runtime config must specify blender")
    commands = {
        "trellis": [sys.executable, str(ROOT / "src/healthmon/trellis_runner.py"),
                    "--image", str(attempt / ("selected_input" + Path(case["image"]).suffix.lower())),
                    "--output", str(model), "--seed", str(case["seed"]),
                    "--config", str(config_path)],
        "validate_unrigged": blender_command(blender, tool, ["validate", "--input", model,
                                    "--report", attempt / "unrigged_validation.json"]),
        "render_unrigged": blender_command(blender, tool, ["render", "--input", model,
                    "--out-dir", attempt / "renders", "--size", size,
                    "--front-azimuth", case["front_azimuth"]]),
    }
    if case["rig"]:
        commands["rigging"] = [sys.executable, str(ROOT / "src/healthmon/rigging_runner.py"),
                    "--input", str(model), "--output-dir", str(attempt / "rigging"),
                    "--config", str(config_path), "--seed", str(case["seed"]), "--size", str(size),
                    "--front-azimuth", str(case["front_azimuth"])]
    return commands


def require_validation(path, rig=False):
    report = json.loads(Path(path).read_text())
    raw = report.get("glb_structure") or {}
    checks = [report.get("technical_valid") is True, report.get("status") == "PASS",
              report.get("actual_file_reopened") is True, report.get("geometry", {}).get("vertices", 0) > 0,
              bool(report.get("materials")), bool(report.get("textures")),
              all(t.get("width", 0) > 0 and t.get("height", 0) > 0 for t in report.get("textures", [])),
              raw.get("materials", 0) > 0, raw.get("textures", 0) > 0, raw.get("images", 0) > 0,
              raw.get("images_embedded") is True, raw.get("primitives", 0) > 0,
              bool(report.get("meshes")), all(m.get("uv_layers") for m in report.get("meshes", []))]
    if rig:
        skeleton, pose = report.get("rig", {}), report.get("pose_test", {})
        checks.extend([skeleton.get("valid") is True, skeleton.get("bone_count", 0) >= 2,
                       skeleton.get("active_joint_count", 0) >= 2, skeleton.get("invalid_weight_vertices") == 0,
                       raw.get("skins", 0) > 0, raw.get("skinned_primitives") == raw.get("primitives"),
                       pose.get("valid") is True, bool(pose.get("best")),
                       (pose.get("best") or {}).get("moved_vertices", 0) > 0])
    if not all(checks):
        raise RuntimeError(f"Actual Blender texture/geometry{'/skinning/pose' if rig else ''} checks failed: {path}")
    return report


def stage_artifacts(name, attempt):
    if name == "trellis":
        report = json.loads((attempt / "trellis/model.trellis.json").read_text())
        if (report.get("status") != "success" or report.get("actual_inference_called") is not True
                or report.get("actual_export_called") is not True):
            raise RuntimeError("TRELLIS success requires actual inference and export call evidence")
        paths = [attempt / "trellis/model.glb", attempt / "trellis/model.trellis.json",
                 attempt / "trellis/model.trellis.log", attempt / "trellis/model.preprocessed.png",
                 attempt / "trellis/model.alpha_sanitized.png"]
        paths += sorted(attempt.glob("selected_input.*"))
    elif name == "validate_unrigged":
        require_validation(attempt / "unrigged_validation.json")
        paths = [attempt / "unrigged_validation.json"]
    elif name == "render_unrigged":
        paths = [attempt / f"renders/{view}.png" for view in VIEWS]
        paths.append(attempt / "renders/render_metadata.json")
    else:
        require_validation(attempt / "rigging/validation.json", rig=True)
        paths = [attempt / "rigging/final_rigged.glb", attempt / "rigging/validation.json",
                 attempt / "rigging/spatial_transfer.json", attempt / "rigging/inference_settings.json"]
        paths += [attempt / f"rigging/validation/{name}" for name in
                  ("neutral.png", "pose_test.png", "skeleton_preview.png", "pose_test.blend")]
        paths += [attempt / f"rigging/renders/{view}.png" for view in VIEWS]
        paths += sorted((attempt / "rigging").glob("*.log"))
        paths += sorted((attempt / "rigging").glob("*.command.json"))
    paths += [attempt / f"logs/{name}.log", attempt / f"logs/{name}.command.json"]
    return artifact_records(paths)


def execute_case(case, attempt, fingerprint, commands, config):
    attempt.mkdir(parents=True, exist_ok=False)
    result = {"case": case, "fingerprint": fingerprint, "attempt_directory": str(attempt),
              "status": "RUNNING", "reused": False, "started_utc": utc_now(),
              "visual_quality": "REVIEW_REQUIRED", "stages": {}}
    record_path = attempt / "case_result.json"
    write_json(record_path, result)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    current = None
    try:
        selected_input = attempt / ("selected_input" + Path(case["image"]).suffix.lower())
        shutil.copyfile(case["image"], selected_input)
        if sha256(selected_input) != case["input_sha256"]:
            raise RuntimeError("Selected image changed after planning; create a new selection plan")
        result["selected_input"] = str(selected_input)
        for name, command in commands.items():
            current = name
            stage = {"status": "RUNNING", "started_utc": utc_now(), "argv": command}
            result["stages"][name] = stage
            write_json(record_path, result)
            log = attempt / f"logs/{name}.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            command_record = {"argv": command, "cwd": str(ROOT), "started_utc": stage["started_utc"]}
            write_json(log.with_suffix(".command.json"), command_record)
            started = time.monotonic()
            print(f"{case['case_id']}: {name} → {log}", flush=True)
            stage_env = blender_environment(config["blender"], extra=config.get("blender_environment")) if name in (
                "validate_unrigged", "render_unrigged") else env
            with log.open("w") as stream:
                completed = subprocess.run(command, cwd=ROOT, env=stage_env, stdout=stream, stderr=subprocess.STDOUT)
            command_record.update(returncode=completed.returncode, duration_seconds=time.monotonic() - started,
                                  finished_utc=utc_now())
            write_json(log.with_suffix(".command.json"), command_record)
            stage.update(returncode=completed.returncode, duration_seconds=command_record["duration_seconds"])
            if completed.returncode:
                raise RuntimeError(f"{name} exited {completed.returncode}; see {log}")
            stage["artifacts"] = stage_artifacts(name, attempt)
            stage.update(status="PASS", finished_utc=utc_now())
            write_json(record_path, result)
        result["status"] = "PASS"
    except (Exception, KeyboardInterrupt) as error:
        result.update(status="INTERRUPTED" if isinstance(error, KeyboardInterrupt) else "FAIL", error=str(error))
        if current:
            result["stages"][current].update(status=result["status"], error=str(error), finished_utc=utc_now())
        if isinstance(error, KeyboardInterrupt):
            raise
    finally:
        result["finished_utc"] = utc_now()
        write_json(record_path, result)
    return result


def save_results(directory, output_root, report):
    write_json(directory / "results.json", report)
    fields = ["case_id", "target_stage", "form", "seed", "rig_requested", "status", "reused",
              "image", "input_sha256", "attempt_directory", "trellis_glb", "rigged_glb", "error"]
    with (directory / "results.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for result in report["cases"]:
            case, attempt = result["case"], Path(result["attempt_directory"])
            writer.writerow({**{k: case[k] for k in ("case_id", "target_stage", "form", "seed", "image", "input_sha256")},
                "rig_requested": case["rig"], "status": result["status"], "reused": result.get("reused", False),
                "attempt_directory": str(attempt), "trellis_glb": str(attempt / "trellis/model.glb") if (attempt / "trellis/model.glb").is_file() else "",
                "rigged_glb": str(attempt / "rigging/final_rigged.glb") if (attempt / "rigging/final_rigged.glb").is_file() else "",
                "error": result.get("error", "")})
    # Each complete summary remains under runs/; these are pointers to the latest run.
    write_json(output_root / "latest_run.json", {"run_directory": str(directory), "updated_utc": utc_now()})
    write_json(output_root / "results.json", report)
    (output_root / "results.csv").write_bytes((directory / "results.csv").read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/runtime.json")
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs/diversity_evaluation/selected_3d")
    parser.add_argument("--seed", type=int, default=42, help="Default seed for cases without an explicit seed")
    parser.add_argument("--size", type=int, default=512, help="Blender render resolution")
    parser.add_argument("--plan-only", action="store_true", help="Print commands and hashes; do not execute or write")
    parser.add_argument("--resume", action="store_true", help="Reuse complete matching cases with verified artifact hashes")
    args = parser.parse_args()
    if args.size < 64:
        parser.error("--size must be at least 64")
    selection, output_root = args.selection.resolve(), args.output_root.resolve()
    config = load_runtime(args.config.resolve())
    cases = load_selection(selection, args.seed)
    code_hashes = {str(path): sha256(path) for path in CODE_FILES}
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ") + f"_{os.getpid()}"
    directory = output_root / "runs" / run_id
    runtime_path = directory / "runtime.resolved.json"
    plan = {"schema_version": 1, "selection_file": str(selection), "selection_sha256": sha256(selection),
            "created_utc": utc_now(), "runtime": config, "code_sha256": code_hashes, "render_size": args.size, "cases": []}
    for case in cases:
        signature = {"case": case, "runtime": config, "code_sha256": code_hashes, "render_size": args.size}
        fingerprint = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
        case_root = output_root / case["case_id"]
        reused = reusable_result(case_root, fingerprint) if args.resume else None
        attempt = Path(reused["attempt_directory"]) if reused else next_attempt(case_root)
        plan["cases"].append({"case": case, "fingerprint": fingerprint, "attempt_directory": str(attempt),
                              "reused": bool(reused), "commands": commands_for(case, attempt, runtime_path, config, args.size),
                              "previous_result": reused})
    if args.plan_only:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 0
    directory.mkdir(parents=True, exist_ok=False)
    write_json(runtime_path, config)
    write_json(directory / "selection.resolved.json", {"cases": cases, "source": str(selection), "sha256": sha256(selection)})
    write_json(directory / "execution_plan.json", plan)
    report = {"schema_version": 1, "run_directory": str(directory), "started_utc": utc_now(),
              "status": "RUNNING", "code_sha256": code_hashes, "render_size": args.size, "cases": [],
              "visual_quality": "REVIEW_REQUIRED"}
    try:
        for item in plan["cases"]:
            result = item["previous_result"] or execute_case(item["case"], Path(item["attempt_directory"]),
                     item["fingerprint"], item["commands"], config)
            report["cases"].append(result)
            save_results(directory, output_root, report)
        report["status"] = "PASS" if all(c["status"] == "PASS" for c in report["cases"]) else "FAIL"
    except KeyboardInterrupt:
        report["status"] = "INTERRUPTED"
        interrupted = Path(item["attempt_directory"]) / "case_result.json"
        if interrupted.is_file():
            report["cases"].append(json.loads(interrupted.read_text()))
    finally:
        report["finished_utc"] = utc_now()
        save_results(directory, output_root, report)
    print(json.dumps({"status": report["status"], "results": str(directory / "results.json")}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else (130 if report["status"] == "INTERRUPTED" else 1)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Selection/configuration error: {error}", file=sys.stderr)
        raise SystemExit(2)
