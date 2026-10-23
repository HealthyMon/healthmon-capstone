#!/usr/bin/env python3
"""Restore fixed public implementation sources only. Copied weights are never downloaded here."""
import argparse,hashlib,json,os,subprocess,urllib.request
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--runtime-root',type=Path,default=Path(__file__).resolve().parents[2]);a=ap.parse_args();root=a.runtime_root.expanduser().resolve()
    if root in (Path('/workspace/generation'),Path('/workspace/healthmon-evolution')):raise SystemExit('Original Spark paths are protected.')
    m=json.loads((root/'migration/source_manifest.json').read_text())
    env=dict(os.environ,GIT_TERMINAL_PROMPT='0')
    for repo in m['repositories']:
        dest=root/'vendor'/repo['name'];dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():
            head=subprocess.check_output(['git','-C',str(dest),'rev-parse','HEAD'],text=True).strip()
            dirty=subprocess.check_output(['git','--no-optional-locks','-C',str(dest),'status','--porcelain','--untracked-files=no'],text=True)
            if head!=repo['commit'] or dirty:raise SystemExit('Different existing source preserved: '+str(dest))
        else:
            dest.mkdir();subprocess.run(['git','init','--quiet',str(dest)],check=True,env=env)
            subprocess.run(['git','-C',str(dest),'remote','add','origin',repo['url']],check=True,env=env)
            subprocess.run(['git','-C',str(dest),'fetch','--depth','1','origin',repo['commit']],check=True,env=env)
            subprocess.run(['git','-C',str(dest),'checkout','--detach','FETCH_HEAD'],check=True,env=env)
        subprocess.run(['git','-C',str(dest),'submodule','update','--init','--recursive','--depth','1'],check=True,env=env)
    spec=json.loads((root/'migration/reports/python310_source.json').read_text());p=root/'vendor'/spec['filename']
    if not p.exists():
        temp=p.with_suffix(p.suffix+'.part')
        with urllib.request.urlopen(spec['url'],timeout=60) as src,temp.open('xb') as out:
            while b:=src.read(1024*1024):out.write(b)
        with temp.open('rb') as h:actual=hashlib.file_digest(h,'sha256').hexdigest()
        if actual!=spec['sha256']:raise SystemExit('Invalid source download preserved: '+str(temp))
        temp.rename(p)
    subprocess.run([os.sys.executable,str(root/'migration/tools/verify_sources.py'),'--runtime-root',str(root)],check=True)
if __name__=='__main__':main()
