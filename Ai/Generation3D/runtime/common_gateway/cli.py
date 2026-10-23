"""Local administration. Never enables GPU execution by starting the HTTP service."""
import argparse
import os
from pathlib import Path

from .runtime import prepare_runtime,provision_parent
from .service import Settings
from .store import Store


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','bind-parent','run-once'])
    parser.add_argument('--work-root',type=Path,required=True)
    parser.add_argument('--model-root',type=Path)
    parser.add_argument('--vendor-root',type=Path)
    parser.add_argument('--pet-id')
    parser.add_argument('--parent-manifest',type=Path)
    parser.add_argument('--allow-gpu',action='store_true',help='Only after the operator has released all other GPU workloads')
    args=parser.parse_args()
    store=Store(args.work_root)
    if args.command=='bind-parent':
        if not args.pet_id or not args.parent_manifest: parser.error('pet ID and actual parent manifest are required')
        result=provision_parent(store,args.pet_id,args.parent_manifest)
        print('Bound read-only historical parent stage',result['stage'],'to the isolated test pet; no new generation performed')
        return
    if not args.model_root or not args.vendor_root: parser.error('existing model and vendor roots are required')
    if args.command=='prepare':
        print(prepare_runtime(args.work_root,args.model_root,args.vendor_root))
        print('Only isolated source copied; models/vendor remain external read-only mounts; no GPU launched')
        return
    if not args.allow_gpu: parser.error('GPU run explicitly prohibited without --allow-gpu')
    from .worker import run_once
    settings=Settings(args.work_root,os.environ.get('AI_SERVER_TOKEN',''))
    result=run_once(settings,store,args.model_root,args.vendor_root,allow_gpu=True)
    print('No queued jobs' if result is None else 'Job '+result['id']+': '+result['status'])


if __name__=='__main__': main()
