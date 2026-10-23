#!/usr/bin/env python3
"""Verify original source bytes and pinned Git/submodule identity without importing models."""
import argparse,hashlib,json,subprocess
from pathlib import Path

def verify(root, full=True):
    doc=json.loads((root/'migration/source_manifest.json').read_text());issues=[]
    for r in doc['repositories']:
        p=root/'vendor'/r['name']
        try:
            head=subprocess.check_output(['git','--no-optional-locks','-C',str(p),'rev-parse','HEAD'],text=True,stderr=subprocess.PIPE).strip()
            sub=subprocess.check_output(['git','--no-optional-locks','-C',str(p),'submodule','status','--recursive'],text=True,stderr=subprocess.PIPE)
            if head!=r['commit']:issues.append({'source':r['name'],'error':'commit_mismatch'})
            if any(l and l[0] in '-+U' for l in sub.splitlines()):issues.append({'source':r['name'],'error':'submodule_not_at_pin'})
        except (subprocess.CalledProcessError,FileNotFoundError):issues.append({'source':r['name'],'error':'missing_source_or_git_metadata'})
    for f in doc['files']:
        p=root/f['path']
        if not p.is_file() or not p.resolve().is_relative_to(root):issues.append({'path':f['path'],'error':'missing_or_external_link'});continue
        if p.stat().st_size!=f['bytes']:issues.append({'path':f['path'],'error':'size_mismatch'});continue
        if full:
            with p.open('rb') as h:actual=hashlib.file_digest(h,'sha256').hexdigest()
            if actual!=f['sha256']:issues.append({'path':f['path'],'error':'sha256_mismatch'})
    py=json.loads((root/'migration/reports/python310_source.json').read_text())
    p=root/'vendor'/py['filename']
    if not p.is_file():issues.append({'path':str(p),'error':'missing_python310_source'})
    elif full:
        with p.open('rb') as h:actual=hashlib.file_digest(h,'sha256').hexdigest()
        if actual!=py['sha256']:issues.append({'path':str(p),'error':'python_source_sha256_mismatch'})
    return {'source_integrity':'FAIL' if issues else 'PASS','repositories':len(doc['repositories']),'files':len(doc['files']),'issues':issues,'compiled_or_inference_tested':False}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--runtime-root',type=Path,default=Path(__file__).resolve().parents[2]);ap.add_argument('--quick',action='store_true');a=ap.parse_args()
    result=verify(a.runtime_root.resolve(),not a.quick);print(json.dumps(result,indent=2));raise SystemExit(bool(result['issues']))
if __name__=='__main__':main()
