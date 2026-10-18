#!/usr/bin/env python3
"""Check copied weights, source code and required assets. Never runs a model."""
import argparse,hashlib,json
from pathlib import Path
import models
from verify_sources import verify as verify_sources

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--runtime-root',type=Path,default=Path(__file__).resolve().parents[2]);ap.add_argument('--quick',action='store_true',help='Sizes/paths only; does not replace the full SHA-256 verification after transfer.');a=ap.parse_args();root=a.runtime_root.expanduser().resolve()
    doc=json.loads((root/'migration/model_manifest.json').read_text());specs=[f for f in doc['files'] if f['required']];issues=[]
    for f in specs:
        p=models.target(root,f['target'])
        if a.quick:
            err=[] if p.is_file() and p.stat().st_size==f['bytes'] else ['missing_or_wrong_size']
        else:err=models.check(p,f)
        if err:issues.append({'path':f['target'],'errors':err})
    issues.extend(models.verify_indices(root,specs))
    for cache,repo,rev in sorted({(f['cache'],f['repo_id'],f['revision']) for f in specs if f.get('cache')}):
        p=root/cache/('models--'+repo.replace('/','--'))/'refs/main'
        if not p.is_file() or p.read_text().strip()!=rev:issues.append({'path':str(p),'errors':['cache_ref_not_pinned']})
    sources=verify_sources(root,not a.quick);issues.extend(sources['issues'])
    for rel in ['run_pipeline.py','scripts/run_stages.sh','scripts/run_image_to_rigged.py','scripts/prepare_3d_input.py','scripts/background_matte.py','src/healthmon/blender_tool.py','src/healthmon/qwen_runner.py','src/healthmon/trellis_runner.py','src/healthmon/rigging_runner.py','src/healthmon/riganything_blender_entry.py','configs/runtime.json','Dockerfile','compose.yaml','PACKAGE_MANIFEST.json']:
        if not (root/rel).is_file():issues.append({'path':rel,'errors':['missing_code']})
    asset_manifest=root/'migration/reports/copied_assets_verified.json'
    if not asset_manifest.is_file():issues.append({'path':str(asset_manifest),'errors':['missing_asset_manifest']})
    else:
        for f in json.loads(asset_manifest.read_text())['files']:
            p=root/f['path']
            if not p.resolve().is_relative_to(root) or not p.is_file() or p.stat().st_size!=f['bytes']:
                issues.append({'path':f['path'],'errors':['missing_or_wrong_asset']});continue
            if not a.quick:
                with p.open('rb') as h:actual=hashlib.file_digest(h,'sha256').hexdigest()
                if actual!=f['sha256']:issues.append({'path':f['path'],'errors':['asset_sha256_mismatch']})
    # Full code manifest is generated from the same files as the GitHub archive.
    package=root/'PACKAGE_MANIFEST.json'
    if package.is_file():
        for f in json.loads(package.read_text())['files']:
            p=root/f['path']
            if not p.is_file():issues.append({'path':f['path'],'errors':['missing_github_code']});continue
            if not a.quick and hashlib.sha256(p.read_bytes()).hexdigest()!=f['sha256']:issues.append({'path':f['path'],'errors':['code_sha256_mismatch']})
    result={'file_configuration':'FAIL' if issues else 'PASS','mode':'size_only' if a.quick else 'full_sha256','model_files':len(specs),'model_bytes':sum(f['bytes'] for f in specs),'source_repositories':sources['repositories'],'source_files':sources['files'],'issues':issues,'target_docker_build_tested':False,'rtx3090_inference_tested':False}
    print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(bool(issues))
if __name__=='__main__':main()
