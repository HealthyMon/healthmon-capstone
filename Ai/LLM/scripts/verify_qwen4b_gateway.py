"""Real model through the existing authenticated AI HTTP app, without a DB/APK."""
import argparse
import json
from pathlib import Path
import secrets
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(REPO))
from scripts.evaluate_qwen4b_common import fixtures


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--adapter',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    a=p.parse_args()
    from fastapi.testclient import TestClient
    from Server.local_probe.gpu_gateway import create_app
    if a.report.exists():raise ValueError('Choose a new report')
    runtime=REPO/'.runtime'/('qwen4b-acceptance-'+uuid.uuid4().hex[:8])
    runtime.mkdir(parents=True)
    token=secrets.token_urlsafe(32)
    config={'environment':'test','server_token':token,'model_path':str(ROOT/'models/qwen3.5-4b'),
        'adapter_path':str(a.adapter.resolve()),'expected_model_version':'qwen4b-v1',
        'expected_model_mode':'lora','quantization':'nf4','warmup':True,
        'full_personality_facts':True,'quality_refinement':False,
        'embedding_path':str(runtime/'embedding-not-configured')}
    private=runtime/'private.json'
    private.write_text(json.dumps(config,indent=2),encoding='utf-8')
    results=[]
    with TestClient(create_app(private)) as client:
        health=client.get('/health').json()
        assert health['ready'] and health['model']['model_id']=='Qwen/Qwen3.5-4B'
        assert health['model']['adapter_activation']['verified_expected_adapter_active']
        for case in [c for c in fixtures() if c['id'] in ('activity-90','memory-revision','exercise-complaint')]:
            body={'contract_version':'healthmon.ai.v1','request_id':'qwen4b-'+case['id'],
                  'pet_id':'offline-acceptance-fixture','input':{'text':case['text'],'context':case['context']}}
            assert client.post('/v1/chat',json=body).status_code==401
            headers={'Authorization':'Bearer '+token}
            response=client.post('/v1/chat',json=body,headers=headers)
            assert response.status_code==200,response.text
            reply=response.json()
            assert reply['provenance']=='real'
            duplicate=client.post('/v1/chat',json=body,headers=headers)
            assert duplicate.status_code==200 and duplicate.json()==reply
            body['input']['text']='different frozen input'
            assert client.post('/v1/chat',json=body,headers=headers).status_code==409
            results.append({'id':case['id'],'response':reply,'authentication_checked':True,'idempotency_checked':True})
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps({'passed':True,'model':health['model'],'cases':results,
        'scope':'real model and FastAPI HTTP app in TestClient; no network bind, DB, embedding retrieval, or Unity APK',
        'runtime':str(runtime)},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'cases':len(results),'report':str(a.report)}))


if __name__=='__main__':main()
