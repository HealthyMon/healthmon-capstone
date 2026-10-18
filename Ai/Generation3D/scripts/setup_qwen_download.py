#!/usr/bin/env python3
"""Download the pinned official Qwen Image 2.1 checkpoint and record provenance."""
import argparse
import json
from pathlib import Path
import shutil
from huggingface_hub import HfApi, snapshot_download

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
args = p.parse_args()
model_id = "Qwen/Qwen-Image-2.1"
revision = "d26bb61231c349cf6b7896fa83353113880e1ba3"
cache = args.project / "models" / "huggingface"
cache.mkdir(parents=True, exist_ok=True)
info = HfApi().model_info(model_id, revision=revision, files_metadata=True)
total_bytes = sum(f.size or 0 for f in info.siblings)
if shutil.disk_usage(cache).free < total_bytes + 5 * 1024**3:
    raise SystemExit(f"Need at least {total_bytes + 5 * 1024**3} free bytes before download.")
path = snapshot_download(model_id, revision=revision, cache_dir=str(cache), max_workers=4)
payload = {"model_id": model_id, "revision": revision, "snapshot": path,
           "total_download_bytes": total_bytes,
           "license": "Qwen RESEARCH LICENSE AGREEMENT; noncommercial research/evaluation only",
           "files": [{"path": f.rfilename, "size": f.size,
                      "blob_id": f.blob_id,
                      "lfs_sha256": getattr(f.lfs, "sha256", None)} for f in info.siblings]}
(args.project / "logs" / "qwen_checkpoint.json").write_text(json.dumps(payload, indent=2) + "\n")
print(path)
