"""Final paired latency/contract batch; fresh processes and identical contexts."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

def cases():
    from scripts.evaluate_qwen4b_common import fixtures
    rows = [x for x in fixtures() if x['id'] in ('activity-90', 'memory-revision', 'memory-number', 'exercise-complaint', 'rest-high')]
    recent = deepcopy(rows[0])
    recent.update(id='recent-dialogue', text='오늘은 쉬면서 그 음악을 듣고 싶어.')
    recent['context']['recent'] = [{'speech':'잔잔한 피아노 음악을 들으면서 쉬어도 좋겠다.', 'source_id':'recent-1'}]
    rows.append(recent)
    return rows

def worker(profile, destination):
    from Server.local_probe.gpu_gateway import LocalModels
    config = json.loads((REPO/'.runtime/qwen4b-live/gateway.json').read_text(encoding='utf-8'))
    config.update(merge_lora_for_inference=profile=='optimized',
                  dequantize_for_inference=profile=='optimized',
                  text_only_inference=profile=='optimized',
                  fused_linear_attention=profile=='optimized',
                  inference_cpu_threads=1 if profile=='optimized' else 8,
                  release_cuda_cache_after_request=profile=='baseline')
    runtime=destination/profile; runtime.mkdir(parents=True, exist_ok=True)
    os.environ['TRITON_CACHE_DIR']=str((REPO/'.runtime/qwen4b-live/cache/triton').resolve())
    model=LocalModels(config, runtime)
    model.load()
    rows=[]
    try:
        for case in cases():
            start=time.perf_counter()
            output,metrics=model.chat({'text':case['text'], 'context':case['context']})
            elapsed=time.perf_counter()-start
            rows.append({'id':case['id'],'seconds':elapsed,'result':output,
                         'attempts':metrics['attempts'],'fallback':metrics['fallback']})
        report={'profile':profile,'model':model.identity,'cases':rows,'median_seconds':statistics.median(r['seconds'] for r in rows),'complete':True}
        (destination/(profile+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    finally: model.close()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--worker',choices=['baseline','optimized']);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    if args.worker: return worker(args.worker,args.output)
    env=dict(os.environ,PYTHONUTF8='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
    for profile in ['baseline','optimized']:
        with (args.output/(profile+'.log')).open('w',encoding='utf-8') as log:
            subprocess.run([sys.executable,'-B',__file__,'--worker',profile,'--output',str(args.output.resolve())],cwd=REPO,env=env,stdout=log,stderr=log,check=True)
    reports={name:json.loads((args.output/(name+'.json')).read_text(encoding='utf-8')) for name in ['baseline','optimized']}
    summary={name:{'median_seconds':r['median_seconds'],'cases':len(r['cases']),'attempt_counts':[len(c['attempts']) for c in r['cases']]} for name,r in reports.items()}
    summary['speedup']=reports['baseline']['median_seconds']/reports['optimized']['median_seconds']
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
