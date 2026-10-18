#!/usr/bin/env python3
"""Resolve paths in this copy. No model imports, downloads or inference."""
import argparse, json, os
from pathlib import Path

def resolve_config(root, env_root, blender):
    root, env_root, blender = (Path(p).expanduser().resolve() for p in (root, env_root, blender))
    c = json.loads((root / 'configs/runtime.json').read_text())
    c.update(_healthmon_generated_runtime=True, _project_root=str(root))
    for stage in ('qwen', 'trellis', 'riganything', 'matting'):
        key = 'rigging' if stage == 'riganything' else stage
        c[key + '_python'] = str(env_root / stage / 'bin/python')
    c.update(qwen_cache=str(root/'models/huggingface'),
        qwen_pipeline_file=str(root/'vendor/diffusers/src/diffusers/pipelines/qwenimage21/pipeline_qwenimage21.py'),
        trellis_repo=str(root/'vendor/TRELLIS.2'), trellis_cache=str(root/'models/trellis'),
        rigging_repo=str(root/'vendor/RigAnything'),
        rigging_checkpoint=str(root/'models/RigAnything/riganything_ckpt.pt'),
        blender=str(blender), blender_binary=str(blender),
        matting_checkpoint=str(root/'models/matting/bria-rmbg.onnx'))
    return c

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--runtime-root',type=Path,default=Path(__file__).resolve().parents[2])
    ap.add_argument('--env-root',type=Path)
    ap.add_argument('--blender',type=Path,default=Path('/usr/bin/blender'))
    ap.add_argument('--replace-generated',action='store_true')
    ap.add_argument('--print-only',action='store_true')
    a=ap.parse_args();root=a.runtime_root.expanduser().resolve()
    if root in (Path('/workspace/generation'),Path('/workspace/healthmon-evolution')):
        raise SystemExit('Refusing to change the original Spark paths.')
    env_root=a.env_root or Path(os.environ.get('HEALTHMON_ENVS',root/'.venvs'))
    c=resolve_config(root,env_root,a.blender)
    if a.print_only: print(json.dumps(c,indent=2));return
    p=root/'configs/runtime.local.json'
    if p.exists():
        old=json.loads(p.read_text())
        if old==c: print(p);return
        if not a.replace_generated or old.get('_healthmon_generated_runtime') is not True:
            raise SystemExit('Existing local configuration preserved; review it manually: '+str(p))
    p.write_text(json.dumps(c,indent=2)+'\n');print(p)
if __name__=='__main__':main()
