"""Create the existing common-gateway manifest after real contract evaluation."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package(adapter, evaluation):
    base=ROOT/'models/qwen3.5-4b'
    source=json.loads((base/'healthmon-source.json').read_text(encoding='utf-8'))
    report=json.loads(evaluation.read_text(encoding='utf-8'))
    if (report.get('complete') is not True or report.get('count',0)<12
        or report.get('contract_valid')!=report['count'] or report.get('profile')!='full-facts'
        or report.get('adapter_sha256')!=sha(adapter/'adapter_model.safetensors')):
        raise ValueError('Require a complete matching real common-server contract evaluation')
    manifest={'model_version':'qwen4b-v1','status':'ready','format':'peft_lora',
        'base_model_id':source['model_id'],'base_revision':source['revision'],
        'base_config_sha256':sha(base/'config.json'),
        'artifact_checksums':{name:sha(adapter/name) for name in ('adapter_config.json','adapter_model.safetensors')},
        'training_quantization':'nf4','evaluation_sha256':sha(evaluation),
        'production_quality_approved':False,'nine_b_parity_verified':False,
        'readiness_scope':'loadable candidate; real common-server JSON contract checked; not Unity or production approval'}
    target=adapter/'healthmon-model.json'
    with target.open('x',encoding='utf-8') as f:json.dump(manifest,f,ensure_ascii=False,indent=2)
    print(str(target))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--adapter',type=Path,required=True)
    p.add_argument('--evaluation',type=Path,required=True)
    a=p.parse_args()
    package(a.adapter,a.evaluation)
