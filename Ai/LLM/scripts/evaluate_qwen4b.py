"""Comparable raw and guarded generation on development validation, never training.

This is not a 9B parity claim or an independent semantic quality benchmark.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--model',type=Path,default=ROOT/'models/qwen3.5-4b')
    p.add_argument('--adapter',type=Path)
    p.add_argument('--data',type=Path,default=ROOT/'data/qwen4b_candidate_v1/validation.jsonl')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--limit',type=int,default=16)
    args=p.parse_args()
    if args.output.exists():
        raise ValueError('Refusing to overwrite evaluation')
    if args.limit<1:
        raise ValueError('limit must be positive')
    os.environ['MODEL_PATH']=str(args.model.resolve())
    os.environ['MODEL_QUANTIZATION']='nf4'
    if args.adapter:
        os.environ['ADAPTER_PATH']=str(args.adapter.resolve())
    else:
        os.environ.pop('ADAPTER_PATH',None)
    import torch
    from src.model import QwenBackend
    from src.agent import validate
    from src.prompts import messages
    rows=[json.loads(x) for x in args.data.read_text(encoding='utf-8').splitlines() if x.strip()]
    # Round-robin scenario coverage, independent of model results.
    groups={}
    for row in rows:
        groups.setdefault(row['scenario_group'],[]).append(row)
    selected=[]
    while len(selected)<min(args.limit,len(rows)):
        for group in sorted(groups):
            if groups[group] and len(selected)<args.limit:
                selected.append(groups[group].pop(0))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    backend=QwenBackend(runtime_guidance=True)
    backend.load()
    results=[]
    try:
        for index,row in enumerate(selected):
            torch.manual_seed(123+index)
            started=time.monotonic()
            raw=backend.generate(row['context'],row['user_text'])
            try:
                output=validate(raw,row['context'],row['user_text'])
                valid,error=True,None
            except Exception as exc:
                output=None
                valid,error=False,str(exc)
            result={'sample_id':row['sample_id'],'scenario_group':row['scenario_group'],
                    'user_text':row['user_text'],'context':row['context'],'reference':row['answer'],
                    'raw':raw,'raw_valid':valid,'validation_error':error,
                    'latency_seconds':time.monotonic()-started,
                    'prompt_sha256':hashlib.sha256(json.dumps(messages(row['context'],row['user_text']),ensure_ascii=False).encode()).hexdigest()}
            results.append(result)
            print(json.dumps({k:result[k] for k in ('sample_id','raw_valid','validation_error','latency_seconds','raw')},ensure_ascii=False),flush=True)
            report={'model':backend.name,'adapter':str(args.adapter) if args.adapter else None,
                    'data_sha256':hashlib.sha256(args.data.read_bytes()).hexdigest(),
                    'split':'development validation, not independent final test','seed':123,
                    'raw_valid':sum(x['raw_valid'] for x in results),'count':len(results),
                    'complete':len(results)==len(selected),'results':results,'human_review':False,
                    'nine_b_parity_verified':False,'semantic_pass_rate':None}
            args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        backend.model=None
        torch.cuda.empty_cache()
        backend.gpu_lease.release()


if __name__=='__main__':
    main()
