#!/usr/bin/env python3
"""Restore or verify pinned weights. Never loads a model or uses a GPU."""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, struct, sys, urllib.request, zipfile
from pathlib import Path
DEFAULT = Path(__file__).resolve().parents[1] / 'model_manifest.json'

def check(path, spec):
    errors = []
    if not path.is_file():
        return ['broken_symlink' if path.is_symlink() else 'missing']
    before = path.stat()
    if before.st_size != spec['bytes']: errors.append('size_mismatch')
    with path.open('rb') as f:
        head = f.read(200)
        if head.startswith(b'version https://git-lfs.github.com/spec/v1'): errors.append('git_lfs_pointer')
        f.seek(0)
        if hashlib.file_digest(f, 'sha256').hexdigest() != spec['sha256']: errors.append('sha256_mismatch')
    if any(x in path.name for x in ['.incomplete', '.partial', '.part']): errors.append('unfinished_name')
    if path.suffix == '.safetensors' and not errors:
        try:
            with path.open('rb') as f:
                n = struct.unpack('<Q', f.read(8))[0]
                if not 2 <= n <= 100_000_000 or n + 8 > before.st_size: raise ValueError('header_length')
                h = json.loads(f.read(n)); tensors = [v for k,v in h.items() if k != '__metadata__']
                end = 0
                for t in sorted(tensors, key=lambda v:v['data_offsets']):
                    a,b = t['data_offsets']
                    if a != end or not a <= b <= before.st_size - n - 8: raise ValueError('offsets')
                    end = b
                if end != before.st_size - n - 8: raise ValueError('payload_length')
        except Exception as exc: errors.append('safetensors_structure:' + type(exc).__name__)
    if path.suffix == '.pt' and not errors:
        try:
            with zipfile.ZipFile(path) as z:
                if not any('/data/' in n for n in z.namelist()): errors.append('no_tensor_entries')
        except zipfile.BadZipFile: errors.append('invalid_torch_zip')
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns): errors.append('changed_during_read')
    return errors

def target(root, name):
    p = root / name
    # HF snapshot symlinks may resolve into the same dedicated runtime root.
    if not p.resolve().is_relative_to(root): raise ValueError('Path escapes runtime root: ' + name)
    return p

def verify_indices(root, specs):
    errors=[]
    for spec in specs:
        p=target(root,spec['target'])
        if p.name.endswith('.index.json') and p.is_file():
            try:
                idx=json.loads(p.read_text())
                for shard in sorted(set(idx['weight_map'].values())):
                    if not (p.parent/shard).resolve().is_relative_to(root) or not (p.parent/shard).is_file():
                        errors.append({'path':str(p),'errors':['missing_or_external_index_shard:'+shard]})
            except (ValueError,KeyError) as exc:errors.append({'path':str(p),'errors':['invalid_weight_index']})
    return errors

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action',choices=['plan','download','verify'])
    ap.add_argument('--runtime-root',type=Path,required=True)
    ap.add_argument('--manifest',type=Path,default=DEFAULT)
    ap.add_argument('--all-observed',action='store_true',help='Also download unused 1024/encoder checkpoints')
    args=ap.parse_args();root=args.runtime_root.expanduser().resolve()
    doc=json.loads(args.manifest.read_text());specs=[f for f in doc['files'] if f['required'] or args.all_observed]
    if args.action=='plan':
        print(json.dumps({'files':len(specs),'bytes':sum(f['bytes'] for f in specs),'runtime_root':str(root),'download_only_note':'HF access may be needed ONLY when downloading absent gated files; copied files verify offline.','inference_verified':False},indent=2));return 0
    if args.action=='download':
        # A dedicated destination prevents accidentally repairing or replacing the source Docker cache.
        marker=root/'.healthmon_migration_destination'
        if root.exists() and any(root.iterdir()) and not marker.exists():
            raise SystemExit('Destination must be empty, or already marked by this downloader. Choose a NEW runtime directory.')
        root.mkdir(parents=True,exist_ok=True);marker.touch(exist_ok=True)
        missing=sum(f['bytes'] for f in specs if not target(root,f['target']).exists())
        if shutil.disk_usage(root).free < missing + 5*1024**3:raise SystemExit('Insufficient free disk space (needs missing bytes + 5 GiB).')
        try:from huggingface_hub import hf_hub_download
        except ImportError:raise SystemExit('Install huggingface-hub in a separate download venv first.')
        for f in specs:
            p=target(root,f['target'])
            if p.exists():
                err=check(p,f)
                if err:raise SystemExit(f'Existing file is invalid; preserved without overwrite: {p}: {err}')
                print('verified',f['filename'],flush=True);continue
            if f['kind']=='huggingface':
                kw={'repo_id':f['repo_id'],'filename':f['filename'],'revision':f['revision']}
                if f.get('cache'):kw['cache_dir']=str(root/f['cache'])
                else:kw['local_dir']=str(p.parent)
                hf_hub_download(**kw)  # HF_TOKEN/login handled by the official client; never logged here.
            else:
                p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+'.part')
                if tmp.exists():raise SystemExit('Incomplete download preserved; inspect before retry: '+str(tmp))
                with urllib.request.urlopen(f['url'],timeout=60) as response,tmp.open('xb') as out:shutil.copyfileobj(response,out,16*1024*1024)
                # Validate using final expected name, while keeping incomplete bytes separate.
                if tmp.stat().st_size != f['bytes']:raise SystemExit('Downloaded size mismatch: '+str(tmp))
                with tmp.open('rb') as s:actual=hashlib.file_digest(s,'sha256').hexdigest()
                if actual!=f['sha256']:raise SystemExit('Downloaded SHA256 mismatch: '+str(tmp))
                tmp.rename(p)
            err=check(p,f)
            if err:raise SystemExit(f'Integrity failure: {p}: {err}')
            print('downloaded and verified',f['filename'],flush=True)
        # Legacy TRELLIS loaders ask for main. Bind ONLY this new dedicated cache to pinned revisions.
        for f in specs:
            if not f.get('cache'):continue
            ref=root/f['cache']/('models--'+f['repo_id'].replace('/','--'))/'refs/main'
            if ref.exists() and ref.read_text().strip()!=f['revision']:raise SystemExit('Ref conflict; preserved: '+str(ref))
            ref.parent.mkdir(parents=True,exist_ok=True)
            if not ref.exists():ref.write_text(f['revision'])
    issues=[]
    for f in specs:
        p=target(root,f['target']);err=check(p,f)
        if err:issues.append({'path':str(p),'errors':err})
    issues += verify_indices(root,specs)
    for cache,repo,revision in sorted({(f['cache'],f['repo_id'],f['revision']) for f in specs if f.get('cache')}):
        ref=target(root,cache+'/models--'+repo.replace('/','--')+'/refs/main')
        if not ref.is_file() or ref.read_text().strip()!=revision:
            issues.append({'path':str(ref),'errors':['unpinned_or_mismatched_legacy_ref']})
    print(json.dumps({'integrity':'FAIL' if issues else 'PASS','files':len(specs),'issues':issues,'inference_verified':False,'rtx3090_inference_verified':False},indent=2))
    return 2 if issues else 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:print('Migration failed: '+str(exc),file=sys.stderr);raise SystemExit(2)
