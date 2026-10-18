#!/usr/bin/env python3
"""Create an isolated TRELLIS.2 runtime; never modify an existing environment.

Use --native-from to COPY compatible previously built native packages, or
--build-native to compile official sources with CUDA 13 and sm_121.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import time

ROOT = Path(__file__).resolve().parents[1]
TRELLIS_COMMIT = "75fbf0183001ed9876c8dbb35de6b68552ee08bd"
SOURCES = {
    "TRELLIS.2": ("https://github.com/microsoft/TRELLIS.2.git", TRELLIS_COMMIT),
    "CuMesh": ("https://github.com/JeffreyXiang/CuMesh.git", "12289e1062f0603f2f0d0771b02e1395d247f26f"),
    "FlexGEMM": ("https://github.com/JeffreyXiang/FlexGEMM.git", "6dd94a859c26ee8246888502eada3dd8ad85532e"),
    "nvdiffrast": ("https://github.com/NVlabs/nvdiffrast.git", "v0.4.0"),
}
DEPENDENCIES = [
    "transformers==4.57.3", "huggingface-hub==0.36.0", "easydict==1.13",
    "opencv-python-headless", "trimesh", "imageio", "imageio-ffmpeg", "ninja",
    "timm", "kornia", "plyfile", "zstandard", "numpy==2.1.0",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, default=ROOT / ".venvs/trellis")
    native = parser.add_mutually_exclusive_group(required=True)
    native.add_argument("--native-from", type=Path, help="Read-only source venv with matching Python/PyTorch ABI")
    native.add_argument("--build-native", action="store_true")
    parser.add_argument("--reuse-cache", type=Path, help="HF hub directory containing official Microsoft caches")
    parser.add_argument("--download-public", action="store_true", help="Download missing public inference weights")
    parser.add_argument("--arch", default="12.1", help="TORCH_CUDA_ARCH_LIST (GB10 is 12.1)")
    args = parser.parse_args()
    started = time.perf_counter()
    logs = ROOT / "logs/trellis"
    logs.mkdir(parents=True, exist_ok=True)
    evidence = {"status": "running", "environment": str(args.env), "sources": {},
                "native_mode": "copied_existing_builds" if args.native_from else "source_build",
                "existing_environments_modified": False, "commands": []}
    report = logs / "setup.json"

    def run(command, cwd=None, env=None):
        print(" ".join(map(str, command)), flush=True)
        evidence["commands"].append(list(map(str, command)))
        with (logs / "setup.log").open("a") as handle:
            completed = subprocess.run(list(map(str, command)), cwd=cwd, env=env,
                                       stdout=handle, stderr=subprocess.STDOUT)
        if completed.returncode:
            raise RuntimeError(f"Command failed ({completed.returncode}); see {logs / 'setup.log'}")

    try:
        if not (args.env / "bin/python").exists():
            run([sys.executable, "-m", "venv", "--system-site-packages", args.env])
        python = args.env / "bin/python"
        # pip sees the inherited NVIDIA CUDA 13 PyTorch; constrain it explicitly
        # so an installer cannot silently select a different torch/CUDA ABI.
        constraint = logs / "torch-constraints.txt"
        constraint.write_text("torch==2.10.0+cu130\ntorchvision==0.25.0+cu130\ntriton==3.6.0\n")
        run([python, "-m", "pip", "install", "--constraint", constraint, *DEPENDENCIES])
        # utils3d's optional moderngl extras are unused in this headless pipeline;
        # their aarch64 build needs X11 headers. Install the official pinned code.
        run([python, "-m", "pip", "install", "--no-deps",
             "git+https://github.com/EasternJournalist/utils3d.git@9a4eb15e4021b67b12c460c7057d642626897ec8"])
        needed = SOURCES if args.build_native else {"TRELLIS.2": SOURCES["TRELLIS.2"]}
        for name, (url, revision) in needed.items():
            target = ROOT / "vendor" / name
            if not (target / ".git").exists():
                run(["git", "clone", url, target])
            run(["git", "-C", target, "checkout", revision])
            if args.build_native:
                run(["git", "-C", target, "submodule", "update", "--init", "--recursive"])
            commit = subprocess.check_output(["git", "-C", str(target), "rev-parse", "HEAD"], text=True).strip()
            evidence["sources"][name] = {"repository": url, "commit": commit,
                                         "license": str(target / "LICENSE")}
        if args.native_from:
            source_python = args.native_from / "bin/python"
            query = "import sysconfig,torch,sys,json;print(json.dumps([sysconfig.get_paths()['purelib'],torch.__version__,sys.version_info[:2]]))"
            old = json.loads(subprocess.check_output([str(source_python), "-c", query], text=True))
            new = json.loads(subprocess.check_output([str(python), "-c", query], text=True))
            if old[1:] != new[1:]:
                raise RuntimeError(f"Cannot reuse native builds across different ABI: {old[1:]} vs {new[1:]}")
            source, destination = Path(old[0]), Path(new[0])
            selected = []
            for prefix in ("cumesh", "o_voxel", "flex_gemm", "nvdiffrast", "_nvdiffrast_c", "flash_attn"):
                for entry in source.glob(prefix + "*"):
                    target = destination / entry.name
                    if target.exists():
                        continue
                    if entry.is_dir():
                        shutil.copytree(entry, target, ignore=shutil.ignore_patterns("__pycache__"))
                    else:
                        shutil.copy2(entry, target)
                    selected.append(entry.name)
            evidence["reused_native_source"] = str(args.native_from.resolve())
            evidence["copied_native_entries"] = selected
        else:
            build_env = os.environ.copy()
            build_env.update(TORCH_CUDA_ARCH_LIST=args.arch, MAX_JOBS="4", BUILD_TARGET="cuda")
            # Setuptools is already available in the inherited NVIDIA runtime.
            for name, location in (("CuMesh", ROOT / "vendor/CuMesh"),
                                   ("FlexGEMM", ROOT / "vendor/FlexGEMM"),
                                   ("O-Voxel", ROOT / "vendor/TRELLIS.2/o-voxel"),
                                   ("nvdiffrast", ROOT / "vendor/nvdiffrast")):
                # FlexGEMM's setup script unconditionally writes a home-directory
                # autotune cache. Redirect that documented setup side effect into
                # the task cache in a COPY; the official checkout stays intact.
                if name == "FlexGEMM":
                    staged = ROOT / "cache/trellis/build/FlexGEMM"
                    shutil.copytree(location, staged, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", "build"))
                    setup = staged / "setup.py"
                    setup.write_text(setup.read_text().replace(
                        'os.path.expanduser("~/.flex_gemm',
                        f'os.path.expanduser("{ROOT / "cache/trellis/flex_gemm"}'))
                    location = staged
                    evidence["flexgemm_build_change"] = "Only setup.py autotune-cache path redirected in staging copy"
                run([python, "-m", "pip", "install", "--no-deps", "--no-build-isolation", location], env=build_env)
            # The host NVIDIA image supplies a CUDA13 FlashAttention build. If
            # absent, upstream builds are available without replacing torch.
            try:
                subprocess.check_output([str(python), "-c", "import flash_attn"], stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError:
                run([python, "-m", "pip", "install", "--no-deps", "--no-build-isolation", "flash-attn==2.7.3"], env=build_env)
        hub = ROOT / "cache/trellis/huggingface/hub"
        hub.mkdir(parents=True, exist_ok=True)
        if args.reuse_cache:
            reused = []
            for cached in args.reuse_cache.glob("models--microsoft--TRELLIS*"):
                destination = hub / cached.name
                if not destination.exists():
                    shutil.copytree(cached, destination, symlinks=True, copy_function=os.link)
                    reused.append(str(cached))
            evidence["reused_checkpoint_cache"] = reused
        if args.download_public:
            code = """
from huggingface_hub import snapshot_download, hf_hub_download
snapshot_download('microsoft/TRELLIS.2-4B', allow_patterns=['pipeline.json','ckpts/*512*','ckpts/ss_flow*','ckpts/shape_dec*','ckpts/tex_dec*'])
for ext in ['json','safetensors']:
 hf_hub_download('microsoft/TRELLIS-image-large', 'ckpts/ss_dec_conv3d_16l8_fp16.'+ext)
"""
            download_env = os.environ.copy()
            original_home = Path(download_env.get("HF_HOME", str(Path.home() / ".cache/huggingface")))
            download_env.setdefault("HF_TOKEN_PATH", str(original_home / "token"))
            download_env["HF_HOME"] = str(hub.parent)
            download_env["HF_HUB_CACHE"] = str(hub)
            run([python, "-c", code], env=download_env)
        verify = """
import importlib,json,torch,platform,importlib.metadata as meta
result={'torch':torch.__version__,'cuda':torch.version.cuda,'architecture':platform.machine(),'imports':{}}
for name in ['cumesh','o_voxel','flex_gemm','nvdiffrast.torch','flash_attn','transformers','utils3d']:
 try: result['imports'][name]={'status':'ok','file':importlib.import_module(name).__file__}
 except Exception as exc: result['imports'][name]={'status':'failed','error':str(exc)}
result['packages']={d.metadata['Name']:d.version for d in meta.distributions()}
print(json.dumps(result))
"""
        result = json.loads(subprocess.check_output([str(python), "-c", verify], text=True))
        evidence["verification"] = result
        failed = [name for name, check in result["imports"].items() if check["status"] != "ok"]
        evidence["status"] = "setup_failed" if failed else "native_imports_passed_checkpoint_access_unverified"
        if failed:
            evidence["error"] = "Failed imports: " + ", ".join(failed)
    except Exception as exc:
        evidence.update(status="setup_failed", error=str(exc))
    finally:
        evidence["elapsed_seconds"] = time.perf_counter() - started
        report.write_text(json.dumps(evidence, indent=2) + "\n")
        print(json.dumps({"status": evidence["status"], "report": str(report)}))
    return 0 if evidence["status"].startswith("native_imports_passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
