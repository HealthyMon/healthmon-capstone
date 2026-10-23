"""Official TRELLIS.2 image-to-3D inference and O-Voxel PBR export.

This module imports no GPU libraries until the isolated worker starts.  Missing
checkpoints are reported before loading the multi-billion parameter models.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = "microsoft/TRELLIS.2-4B"
SOURCE_COMMIT = "75fbf0183001ed9876c8dbb35de6b68552ee08bd"


class TrellisError(RuntimeError):
    def __init__(self, report: dict[str, Any]):
        self.report = report
        super().__init__(report.get("error", report.get("status", "TRELLIS failed")))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n")
    temporary.replace(path)


def _config(config: Mapping | str | Path | None) -> dict:
    if isinstance(config, Mapping):
        return dict(config)
    path = Path(config) if config else ROOT / "configs/runtime.json"
    return json.loads(path.read_text()) if path.exists() else {}


def _sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _environment(cfg: dict) -> None:
    cache = Path(cfg.get("trellis_cache", ROOT / "cache/trellis")).resolve()
    # Preserve standard `hf auth login` credentials when isolating weight caches.
    # Explicit HF_TOKEN/HF_TOKEN_PATH continue to take precedence; never log them.
    original_hf_home = Path(os.environ.get("HF_HOME", str(Path.home() / ".cache/huggingface")))
    os.environ.setdefault("HF_TOKEN_PATH", str(original_hf_home / "token"))
    os.environ["HF_HOME"] = str(cache / "huggingface")
    os.environ["HF_HUB_CACHE"] = str(cache / "huggingface/hub")
    os.environ["TORCH_HOME"] = str(cache / "torch")
    os.environ["TORCH_EXTENSIONS_DIR"] = str(cache / "torch_extensions")
    os.environ["TRITON_CACHE_DIR"] = str(cache / "triton")
    flex_cache = cache / "flex_gemm/autotune_cache.json"
    flex_cache.parent.mkdir(parents=True, exist_ok=True)
    previous_flex_cache = Path.home() / ".flex_gemm/autotune_cache.json"
    if not flex_cache.exists() and previous_flex_cache.is_file():
        flex_cache.write_bytes(previous_flex_cache.read_bytes())
    os.environ["FLEX_GEMM_AUTOTUNE_CACHE_PATH"] = str(flex_cache)
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ.setdefault("ATTN_BACKEND", "flash_attn")
    os.environ.setdefault("SPARSE_CONV_BACKEND", "flex_gemm")
    os.environ.setdefault("OMP_NUM_THREADS", "4")
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    for name in ("HF_HOME", "TORCH_HOME", "TORCH_EXTENSIONS_DIR", "TRITON_CACHE_DIR"):
        Path(os.environ[name]).mkdir(parents=True, exist_ok=True)


def _manifest(cfg: dict) -> tuple[dict, str, Path]:
    from huggingface_hub import hf_hub_download
    model = str(cfg.get("trellis_model", DEFAULT_MODEL))
    if Path(model).is_dir():
        manifest_path = Path(model) / "pipeline.json"
    else:
        try:
            manifest_path = Path(hf_hub_download(model, "pipeline.json", local_files_only=True))
        except Exception:
            manifest_path = Path(hf_hub_download(model, "pipeline.json"))
    return json.loads(manifest_path.read_text()), model, manifest_path


def _checkpoint_access(model: str) -> dict:
    from huggingface_hub import hf_hub_download, get_hf_file_metadata, hf_hub_url
    if Path(model).is_dir():
        root = Path(model)
        found = any((root / filename).is_file() for filename in
                    ("model.safetensors", "model.safetensors.index.json", "pytorch_model.bin"))
        return {"model": model, "available": found, "source": "local",
                **({} if found else {"error": "Checkpoint directory has no model weights"})}
    try:
        cached = hf_hub_download(model, "model.safetensors", local_files_only=True)
        return {"model": model, "available": True, "source": "cache", "path": cached}
    except Exception:
        pass
    try:
        get_hf_file_metadata(hf_hub_url(model, "model.safetensors"), timeout=20)
        return {"model": model, "available": True, "source": "huggingface"}
    except Exception as exc:
        return {"model": model, "available": False,
                "error_type": type(exc).__name__, "error": str(exc)}


def _preflight(image: Path, cfg: dict, report: dict) -> tuple[dict, str, bool]:
    from PIL import Image
    import numpy as np
    with Image.open(image) as source:
        # Match the official preprocessing alpha branch exactly.
        alpha = np.asarray(source)[:, :, 3] if source.mode == "RGBA" else None
        has_alpha = alpha is not None and bool(np.any(alpha != 255))
        if has_alpha and not np.any(alpha > 0.8 * 255):
            raise ValueError("Input has no opaque foreground pixels for official preprocessing")
        report["input_mode"] = source.mode
        report["input_size"] = list(source.size)
        report["usable_alpha"] = has_alpha
    manifest, model, manifest_path = _manifest(cfg)
    report["pipeline_manifest"] = str(manifest_path)
    report["pipeline_manifest_sha256"] = _sha256(manifest_path)
    if manifest_path.parent.parent.name == "snapshots":
        report["model_revision"] = manifest_path.parent.name
    dino = str(cfg.get("trellis_dino_model", manifest["args"]["image_cond_model"]["args"]["model_name"]))
    rmbg = str(cfg.get("trellis_rembg_model", manifest["args"]["rembg_model"]["args"]["model_name"]))
    report["checkpoint_access"] = [_checkpoint_access(dino)]
    if has_alpha:
        report["background_removal"] = "Official preprocess_image usable-alpha branch; RMBG not needed"
    else:
        report["checkpoint_access"].append(_checkpoint_access(rmbg))
        report["background_removal"] = rmbg
    report["conditioning_model"] = dino
    report["model"] = model
    if not all(item["available"] for item in report["checkpoint_access"]):
        report["status"] = "blocked_checkpoint_access"
        report["error"] = "Required official conditioning checkpoint unavailable: " + "; ".join(
            f"{item['model']}: {item.get('error', 'missing weights')}"
            for item in report["checkpoint_access"] if not item["available"])
        raise TrellisError(report)
    return manifest, model, has_alpha


def _load_pipeline(manifest: dict, model: str, cfg: dict, has_alpha: bool):
    from trellis2 import models
    from trellis2.modules import image_feature_extractor
    from trellis2.pipelines import Trellis2ImageTo3DPipeline
    from trellis2.pipelines import samplers, rembg
    args = copy.deepcopy(manifest["args"])
    loaded = {}
    # The official constructor accepts preloaded models.  1024-only models are
    # unnecessary for its documented 512 path and consume several extra GB.
    for name, relative in args["models"].items():
        if name.endswith("_1024"):
            continue
        path = relative if relative.startswith("microsoft/") else f"{model}/{relative}"
        component = models.from_pretrained(path)
        if not bool(cfg.get("trellis_low_vram", True)):
            component = component.to("cuda")
            print(f"Loaded {name} directly into retained GPU residency", flush=True)
        loaded[name] = component
    sampler_kwargs = {}
    for name in ("sparse_structure", "shape_slat", "tex_slat"):
        spec = args[name + "_sampler"]
        sampler_kwargs[name + "_sampler"] = getattr(samplers, spec["name"])(**spec["args"])
        sampler_kwargs[name + "_sampler_params"] = spec["params"]
    cond_spec = args["image_cond_model"]
    cond_spec["args"]["model_name"] = cfg.get("trellis_dino_model", cond_spec["args"]["model_name"])
    conditioning = getattr(image_feature_extractor, cond_spec["name"])(**cond_spec["args"])
    background = None
    if not has_alpha:
        spec = args["rembg_model"]
        spec["args"]["model_name"] = cfg.get("trellis_rembg_model", spec["args"]["model_name"])
        background = getattr(rembg, spec["name"])(**spec["args"])
    return Trellis2ImageTo3DPipeline(
        models=loaded, image_cond_model=conditioning, rembg_model=background,
        shape_slat_normalization=args["shape_slat_normalization"],
        tex_slat_normalization=args["tex_slat_normalization"],
        default_pipeline_type="512", low_vram=bool(cfg.get("trellis_low_vram", True)),
        **sampler_kwargs)


def _sanitize_alpha(source, minimum: int = 16, support_radius: int = 4):
    """Suppress faint decoded matte noise, preserving the source file and RGB.

    Qwen's RGBA decoder can leave alpha=1..15 grid lines in empty background.
    The upstream preprocessor composites every nonzero alpha pixel, which can
    turn those lines into spurious 3D planes. Retain ordinary antialiased edges.
    """
    import numpy as np
    from PIL import Image
    from scipy import ndimage
    if source.mode != "RGBA":
        return source.copy(), {"applied": False, "reason": "No RGBA alpha"}
    if not 0 <= minimum <= 255:
        raise ValueError("trellis_alpha_noise_floor must be between 0 and 255")
    rgba = np.asarray(source).copy()
    alpha = rgba[:, :, 3]
    labels, count = ndimage.label(alpha > 128)
    sizes = np.bincount(labels.ravel())[1:]
    if not count:
        raise ValueError("RGBA input has no confident foreground component")
    # Keep all substantial islands so detached appendages remain possible.
    # A four-pixel support band retains the original antialiased silhouette.
    kept = np.flatnonzero(sizes >= min(sizes.max(), max(64, sizes.max() * .001))) + 1
    support = np.isin(labels, kept)
    if support_radius:
        support = ndimage.binary_dilation(support, iterations=support_radius)
    exterior = (alpha > 0) & ~support
    noise = (alpha > 0) & ((alpha < minimum) | ~support)
    rgba[:, :, 3][noise] = 0
    return Image.fromarray(rgba), {"applied": bool(noise.any()),
        "minimum_retained_alpha": minimum, "suppressed_pixels": int(noise.sum()),
        "support_dilation_pixels": support_radius,
        "confident_components": count, "retained_components": int(len(kept)),
        "exterior_residual_pixels": int(exterior.sum()),
        "original_file_modified": False, "rgb_modified": False}


def _worker(image: Path, output: Path, seed: int, cfg: dict, preflight_only: bool) -> dict:
    start = time.perf_counter()
    report_path = output.with_suffix(".trellis.json")
    report = {"status": "running", "image": str(image), "output": str(output),
              "seed": seed, "pipeline_type": "512", "voxel_resolution": 512,
              "actual_inference_called": False, "actual_export_called": False,
              "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "report_path": str(report_path)}
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        _environment(cfg)
        repo = Path(cfg.get("trellis_repo", ROOT / "vendor/TRELLIS.2")).resolve()
        if not (repo / "trellis2").is_dir():
            raise FileNotFoundError(f"Official TRELLIS.2 source missing: {repo}")
        sys.path.insert(0, str(repo))
        report["source_repo"] = str(repo)
        report["source_commit"] = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        report["input_sha256"] = _sha256(image)
        manifest, model, has_alpha = _preflight(image, cfg, report)
        if preflight_only:
            report["status"] = "preflight_passed"
            return report
        import torch
        from PIL import Image
        import o_voxel
        report.update(torch=torch.__version__, cuda=torch.version.cuda,
                      gpu=torch.cuda.get_device_name(), capability=list(torch.cuda.get_device_capability()))
        load_start = time.perf_counter()
        pipeline = _load_pipeline(manifest, model, cfg, has_alpha)
        pipeline.cuda()
        report["load_seconds"] = time.perf_counter() - load_start
        report["loading_memory_mode"] = "each_component_to_cuda_after_loading"
        with Image.open(image) as original:
            sanitized, alpha_report = _sanitize_alpha(
                original, int(cfg.get("trellis_alpha_noise_floor", 16)))
        sanitized_path = output.with_suffix(".alpha_sanitized.png")
        sanitized.save(sanitized_path)
        report["alpha_sanitation"] = {**alpha_report, "output": str(sanitized_path),
                                      "output_sha256": _sha256(sanitized_path)}
        image_preprocessed = pipeline.preprocess_image(sanitized)
        preprocessed_path = output.with_suffix(".preprocessed.png")
        image_preprocessed.save(preprocessed_path)
        report["preprocessed_image"] = str(preprocessed_path)
        torch.cuda.synchronize()
        inference_start = time.perf_counter()
        report["actual_inference_called"] = True
        _write(report_path, report)
        with torch.inference_mode():
            mesh = pipeline.run(image_preprocessed, seed=seed, pipeline_type="512", preprocess_image=False)[0]
            torch.cuda.synchronize()
            report["inference_seconds"] = time.perf_counter() - inference_start
            report["raw_vertices"] = int(len(mesh.vertices))
            report["raw_faces"] = int(len(mesh.faces))
            if not report["raw_vertices"] or not report["raw_faces"]:
                raise RuntimeError("Official inference returned empty geometry")
            if not torch.isfinite(mesh.vertices).all().item():
                raise RuntimeError("Official inference returned nonfinite vertices")
            mesh.simplify(16777216)  # Official example's nvdiffrast limit.
            export_start = time.perf_counter()
            report["actual_export_called"] = True
            export_options = dict(decimation_target=int(cfg.get("trellis_decimation_target", 1000000)),
                                  texture_size=int(cfg.get("trellis_texture_size", 2048)),
                                  remesh=bool(cfg.get("trellis_remesh", True)),
                                  remesh_band=1, remesh_project=0, verbose=True)
            report["export_options"] = export_options
            _write(report_path, report)
            glb = o_voxel.postprocess.to_glb(
                vertices=mesh.vertices, faces=mesh.faces, attr_volume=mesh.attrs,
                coords=mesh.coords, attr_layout=mesh.layout, voxel_size=mesh.voxel_size,
                aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]], **export_options)
            # PNG textures work in standard glTF viewers without an optional
            # EXT_texture_webp decoder, while preserving official PBR maps.
            glb.export(str(output), extension_webp=False)
            torch.cuda.synchronize()
            report["export_seconds"] = time.perf_counter() - export_start
        report.update(status="success", output_sha256=_sha256(output), output_bytes=output.stat().st_size)
    except Exception as exc:
        if report["status"] == "running":
            report["status"] = ("export_failed" if report["actual_export_called"] else
                                "inference_failed" if report["actual_inference_called"] else "setup_failed")
        report["error"] = str(exc)
        report["error_type"] = type(exc).__name__
        report["traceback"] = traceback.format_exc()
    finally:
        report["elapsed_seconds"] = time.perf_counter() - start
        report["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        _write(report_path, report)
    return report


def run_trellis(image: str | Path, output: str | Path, seed: int = 42, *,
                config: Mapping | str | Path | None = None, preflight_only: bool = False) -> dict:
    """Run the official 512 pipeline in its configured isolated interpreter.

    Return a success report; raise TrellisError (with .report) on real failure.
    The evidence JSON is always saved as ``<output stem>.trellis.json``.
    """
    cfg = _config(config)
    image, output = Path(image).resolve(), Path(output).resolve()
    if not image.is_file():
        raise FileNotFoundError(image)
    if output.suffix.lower() != ".glb":
        raise ValueError("TRELLIS output must end in .glb")
    python = str(cfg.get("trellis_python", ROOT / ".venvs/trellis/bin/python"))
    output.parent.mkdir(parents=True, exist_ok=True)
    worker_config = output.with_suffix(".trellis.config.json")
    _write(worker_config, {key: value for key, value in cfg.items() if key.startswith("trellis_")})
    command = [python, str(Path(__file__).resolve()), "--image", str(image), "--output", str(output),
               "--seed", str(seed), "--config", str(worker_config), "--in-process"]
    if preflight_only:
        command.append("--preflight")
    log_path = output.with_suffix(".trellis.log")
    report_path = output.with_suffix(".trellis.json")
    _write(report_path, {"status": "worker_starting", "image": str(image), "output": str(output),
                         "seed": seed, "actual_inference_called": False, "actual_export_called": False})
    try:
        with log_path.open("w") as handle:
            completed = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT, check=False)
    except OSError as exc:
        report = {"status": "worker_failed", "error": str(exc), "log_path": str(log_path),
                  "actual_inference_called": False, "actual_export_called": False}
        _write(report_path, report)
        raise TrellisError(report) from exc
    report = json.loads(report_path.read_text())
    if report["status"] == "worker_starting":
        report.update(status="worker_failed", error=f"TRELLIS worker exited {completed.returncode}; see {log_path}")
    report["log_path"] = str(log_path)
    _write(report_path, report)
    if completed.returncode or report["status"] not in ("success", "preflight_passed"):
        raise TrellisError(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", default=42, type=int)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--preflight", action="store_true", help="Check checkpoint access without GPU inference")
    parser.add_argument("--in-process", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.in_process:
        report = _worker(args.image.resolve(), args.output.resolve(), args.seed, _config(args.config), args.preflight)
    else:
        try:
            report = run_trellis(args.image, args.output, args.seed, config=args.config, preflight_only=args.preflight)
        except TrellisError as exc:
            report = exc.report
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] in ("success", "preflight_passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
