"""One final validation batch after training; never retrains or changes prompts."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[1]


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    selection=json.loads((a.run/'selection.json').read_text(encoding='utf-8'))
    if selection.get('trained') is not True:raise ValueError('Training must complete first')
    adapter=Path(selection['selected']['path'])
    a.output=a.output.resolve()
    a.output.mkdir(parents=True,exist_ok=False)
    env={**os.environ,'PYTHONUTF8':'1','HF_HUB_DISABLE_PROGRESS_BARS':'1',
         'PYTHONPATH':os.pathsep.join([str(ROOT),str(REPO)])}
    results=[]
    def run(name,arguments):
        started=time.time()
        print(json.dumps({'phase':name,'status':'started'}),flush=True)
        with (a.output/(name+'.log')).open('w',encoding='utf-8') as log:
            result=subprocess.run([sys.executable,*map(str,arguments)],cwd=REPO,env=env,stdout=log,stderr=subprocess.STDOUT)
        results.append({'phase':name,'exit_code':result.returncode,'seconds':time.time()-started})
        print(json.dumps(results[-1]),flush=True)
        (a.output/'progress.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        return result.returncode==0
    passed=run('unit-tests',['-m','pytest','Ai/LLM/tests/test_qwen4b_migration.py',
        'Ai/LLM/tests/test_model_runtime.py','Ai/LLM/tests/test_agent.py','Ai/LLM/tests/test_guard_scope.py',
        'Server/local_probe/test_model_selection.py','Server/local_probe/test_contract.py','-q'])
    legacy=run('legacy-generation',[ROOT/'scripts/evaluate_qwen4b.py','--adapter',adapter,
        '--output',a.output/'legacy-validation.json','--limit','16'])
    common=run('common-generation',[ROOT/'scripts/evaluate_qwen4b_common.py','--adapter',adapter,
        '--output',a.output/'common-validation.json'])
    packaged=False
    gateway=False
    if common:
        common_report=json.loads((a.output/'common-validation.json').read_text(encoding='utf-8'))
        if common_report['complete'] and common_report['contract_valid']==common_report['count']:
            packaged=run('package',[ROOT/'scripts/package_qwen4b.py','--adapter',adapter,
                '--evaluation',a.output/'common-validation.json'])
            if packaged:
                gateway=run('http-gateway',[ROOT/'scripts/verify_qwen4b_gateway.py','--adapter',adapter,
                    '--report',a.output/'gateway.json'])
    report={'training_completed':True,'adapter':str(adapter),'validation_batches':1,
            'unit_tests_passed':passed,'generation_runs_completed':legacy and common,
            'common_bundle_packaged':packaged,'real_http_gateway_passed':gateway,
            'nine_b_parity_verified':False,'live_unity_apk_verified':False,
            'production_quality_approved':False,'phases':results}
    (a.output/'summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
