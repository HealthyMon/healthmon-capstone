#!/usr/bin/env python3
"""Run the official local Qwen-Image-2.1 multi-image editing pipeline.

This process owns all Qwen model allocations and exits after a single image,
so the orchestrator can load TRELLIS separately without overlapping models.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone

PROJECT = Path(__file__).resolve().parents[2]
MODEL_ID = "Qwen/Qwen-Image-2.1"
MODEL_REVISION = "d26bb61231c349cf6b7896fa83353113880e1ba3"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def git_revision(name: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(PROJECT / "vendor" / name), "rev-parse", "HEAD"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--images", nargs="*", type=Path, default=[],
                   help="Zero images for native text-to-image, or 1 to 10 ordered image references.")
    p.add_argument("--roles", nargs="*", default=[],
                   help="One explicit reference role per image, in matching order.")
    p.add_argument("--prompt-file", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--width", type=int, default=768)
    p.add_argument("--height", type=int, default=768)
    p.add_argument("--steps", type=int, default=40)
    p.add_argument("--reference-resolution", type=int, default=None,
                   help="Official output_resolution argument: condition-image area target side.")
    p.add_argument("--cache-dir", type=Path, default=PROJECT / "models" / "huggingface")
    p.add_argument("--memory-mode", choices=("cuda", "model-cpu-offload", "sequential-cpu-offload", "phased-cpu-offload"), default="cuda")
    p.add_argument("--local-files-only", action="store_true")
    p.add_argument("--no-kv-cache", action="store_true")
    p.add_argument("--vae-tiling", action="store_true",
                   help="Opt into official VAE tiling when full-image decode does not fit.")
    return p


def main() -> int:
    args = parser().parse_args()
    if len(args.images) != len(args.roles) or not 0 <= len(args.images) <= 10:
        raise SystemExit("Provide zero to ten images and one role per image.")
    if min(args.width, args.height) < 256 or args.width % 32 or args.height % 32:
        raise SystemExit("Width and height must be at least 256 and multiples of 32.")
    if args.steps < 1:
        raise SystemExit("Steps must be positive.")
    if args.output.suffix.lower() != ".png":
        raise SystemExit("Output must be PNG so native model transparency can be preserved.")
    paths = [p.resolve(strict=True) for p in args.images]
    prompt_path = args.prompt_file.resolve(strict=True)
    prompt = prompt_path.read_text().strip()
    if not prompt:
        raise SystemExit("Prompt file is empty.")
    # The order/role declaration is part of the actual model prompt, not metadata alone.
    role_prefix = "Ordered reference images and their roles:\n" + "\n".join(
        f"Image {i}: {role}." for i, role in enumerate(args.roles, start=1)
    )
    effective_prompt = role_prefix + "\n\n" + prompt if paths else prompt
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata_path = output.with_suffix(output.suffix + ".json")
    effective_prompt_path = output.with_suffix(".effective_prompt.txt")
    effective_prompt_path.write_text(effective_prompt + "\n")
    reference_resolution = args.reference_resolution or min(args.width, args.height)
    metadata = {
        "status": "RUNNING", "model_id": MODEL_ID, "model_revision": MODEL_REVISION,
        "implementation": "diffusers.QwenImage21Pipeline", "local_inference": True, "generation_mode": "image_conditioned" if paths else "native_text_to_image",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "requested_output": str(output), "source_prompt_file": str(prompt_path),
        "source_prompt_sha256": sha256(prompt_path), "prompt": effective_prompt,
        "effective_prompt_file": str(effective_prompt_path),
        "ordered_references": [{"index": i, "path": str(path), "role": role,
                                "sha256": sha256(path)}
                               for i, (path, role) in enumerate(zip(paths, args.roles), start=1)],
        "parameters": {"seed": args.seed, "width": args.width, "height": args.height,
                       "num_inference_steps": args.steps, "output_resolution": reference_resolution,
                       "torch_dtype": "bfloat16", "true_cfg_scale": 1.0,
                       "use_kv_cache": not args.no_kv_cache, "num_images_per_prompt": 1,
                       "generator_device": "cuda", "memory_mode": args.memory_mode, "vae_tiling": args.vae_tiling},
        "versions": {"python": sys.version, "platform": platform.platform(),
                     "diffusers_commit": git_revision("diffusers"),
                     "qwen_repository_commit": git_revision("Qwen-Image-2.1")},
        "license": "Qwen RESEARCH LICENSE AGREEMENT: noncommercial research/evaluation only",
        "visual_quality": "REQUIRES_REVIEW",
        "command": sys.argv,
    }
    write_json(metadata_path, metadata)
    started = time.monotonic()
    try:
        from PIL import Image
        import torch
        import diffusers
        from diffusers import QwenImage21Pipeline
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable; genuine local Qwen GPU inference cannot run.")
        metadata["versions"].update({
            "torch": torch.__version__, "cuda": torch.version.cuda,
            "diffusers": diffusers.__version__,
            "transformers": importlib.metadata.version("transformers"),
            "accelerate": importlib.metadata.version("accelerate"),
        })
        metadata["gpu"] = {"name": torch.cuda.get_device_name(0),
                           "capability": list(torch.cuda.get_device_capability(0))}
        references = []
        for path, item in zip(paths, metadata["ordered_references"]):
            with Image.open(path) as image:
                item.update({"original_mode": image.mode, "size": list(image.size)})
                references.append(image.convert("RGBA"))
        write_json(metadata_path, metadata)
        print(f"Loading {MODEL_ID}@{MODEL_REVISION} in bfloat16", flush=True)
        pipe = QwenImage21Pipeline.from_pretrained(
            MODEL_ID, revision=MODEL_REVISION, torch_dtype=torch.bfloat16,
            cache_dir=str(args.cache_dir), local_files_only=args.local_files_only,
        )
        if args.memory_mode in ("sequential-cpu-offload", "phased-cpu-offload"):
            pipe.enable_sequential_cpu_offload()
            if args.memory_mode == "phased-cpu-offload":
                original_encode_prompt = pipe.encode_prompt
                encoded_once = False

                def encode_then_release(*positional, **keywords):
                    nonlocal encoded_once
                    if encoded_once:
                        raise RuntimeError("Phased mode supports this runner's single positive prompt only.")
                    encoded = original_encode_prompt(*positional, **keywords)
                    # Keep a small, local recovery point before loading the
                    # denoiser, so retries need not encode the prompt again.
                    torch.save([item.detach().cpu() if item is not None else None for item in encoded],
                               output.with_suffix(".prompt-embeds.pt"))
                    encoded_once = True
                    # The pinned pipeline does not read text_encoder after this call.
                    # Do not detach its sequential hooks: doing so would restore all
                    # 17.5 GB of encoder parameters to CPU before discarding them.
                    pipe.register_modules(text_encoder=None, transformer=None)
                    gc.collect()
                    torch.cuda.empty_cache()
                    # Restore only the small VAE. Load the denoiser directly on
                    # CUDA instead of restoring a full CPU copy then moving it.
                    pipe.remove_all_hooks()
                    gc.collect()
                    torch.cuda.empty_cache()
                    from diffusers import QwenImage21Transformer2DModel
                    denoiser = QwenImage21Transformer2DModel.from_pretrained(
                        MODEL_ID, subfolder="transformer", revision=MODEL_REVISION,
                        torch_dtype=torch.bfloat16, device_map="cuda",
                        cache_dir=str(args.cache_dir), local_files_only=args.local_files_only,
                    )
                    pipe.register_modules(transformer=denoiser)
                    pipe.vae.to("cuda")
                    metadata["prompt_encoder_released"] = True
                    metadata["denoising_memory_mode"] = "direct-cuda-load"
                    write_json(metadata_path, metadata)
                    print("Prompt encoded; released text encoder. Denoiser will stay on GPU.", flush=True)
                    return encoded

                pipe.encode_prompt = encode_then_release
        elif args.memory_mode == "model-cpu-offload":
            pipe.enable_model_cpu_offload()
        else:
            pipe = pipe.to("cuda")
        if args.vae_tiling:
            pipe.vae.enable_tiling()
        metadata["loading_seconds"] = round(time.monotonic() - started, 3)
        metadata["scheduler"] = dict(pipe.scheduler.config)
        metadata["pipeline_sampling_sigmas"] = getattr(pipe.config, "sample_sigmas", None)
        write_json(metadata_path, metadata)
        print(f"Editing {len(references)} ordered references, {args.width}x{args.height}, "
              f"{args.steps} steps, seed {args.seed}", flush=True)
        generation_started = time.monotonic()
        with torch.inference_mode():
            result = pipe(
                prompt=effective_prompt, image=references or None,
                width=args.width, height=args.height, output_resolution=reference_resolution,
                num_inference_steps=args.steps,
                generator=torch.Generator("cuda").manual_seed(args.seed),
                use_kv_cache=not args.no_kv_cache,
            ).images[0]
        result.save(output)
        metadata["generation_seconds"] = round(time.monotonic() - generation_started, 3)
        metadata["output"] = {"path": str(output), "sha256": sha256(output),
                              "size": list(result.size), "mode": result.mode}
        if "A" in result.getbands():
            alpha = result.getchannel("A")
            hist = alpha.histogram()
            metadata["output"]["alpha_extrema"] = list(alpha.getextrema())
            metadata["output"]["transparent_pixel_fraction"] = sum(hist[:250]) / (result.width * result.height)
        metadata["peak_cuda_allocated_gb"] = torch.cuda.max_memory_allocated() / 1e9
        metadata["peak_cuda_reserved_gb"] = torch.cuda.max_memory_reserved() / 1e9
        metadata["status"] = "PASS"
        print(f"Saved real Qwen output: {output}", flush=True)
        del result, pipe, references
        torch.cuda.empty_cache()
    except Exception as exc:
        metadata.update({"status": "FAIL", "error": str(exc), "traceback": traceback.format_exc()})
        traceback.print_exc()
    metadata["elapsed_seconds"] = round(time.monotonic() - started, 3)
    metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_json(metadata_path, metadata)
    return 0 if metadata["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
