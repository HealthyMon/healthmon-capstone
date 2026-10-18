#!/usr/bin/env python3
"""Check exported package and optional backup bytes; never loads a model."""
import argparse,hashlib,json
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--asset-root',type=Path);ap.add_argument('--readiness',action='store_true');a=ap.parse_args()
root=Path(__file__).resolve().parents[2];issues=[];count=0
for base,manifest in [(root,root/'PACKAGE_MANIFEST.json')]+([(a.asset_root.resolve(),a.asset_root/'BACKUP_MANIFEST.json')] if a.asset_root else []):
 if not manifest.is_file():issues.append({'path':str(manifest),'reason':'missing_manifest'});continue
 for f in json.loads(manifest.read_text())['files']:
  p=base/f['path'];count+=1
  if not p.resolve().is_relative_to(base.resolve()) or not p.is_file():issues.append({'path':str(p),'reason':'missing_or_external'});continue
  with p.open('rb') as s:digest=hashlib.file_digest(s,'sha256').hexdigest()
  if p.stat().st_size!=f['bytes'] or digest!=f['sha256']:issues.append({'path':str(p),'reason':'content_changed'})
blocked=json.loads((root/'migration/model_manifest.json').read_text())['blockers']
print(json.dumps({'package_integrity':'FAIL' if issues else 'PASS','files_checked':count,'issues':issues,'pipeline_readiness':'RTX3090_INFERENCE_NOT_TESTED','blockers':blocked,'rtx3090_inference_tested':False},ensure_ascii=False,indent=2))
raise SystemExit(2 if issues or a.readiness else 0)
