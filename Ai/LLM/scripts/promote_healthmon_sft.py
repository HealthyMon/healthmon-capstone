"""Promote only after the final offline evaluation and explicit semantic review."""
import json
from pathlib import Path
from package_qwen4b import package,sha

ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1]
RUN=ROOT/'runs/qwen4b-healthmon-sft-v1'

def main():
    evaluation=RUN/'final-evaluation/after.json'
    review=json.loads((RUN/'final-evaluation/semantic-review.json').read_text(encoding='utf-8'))
    if review.get('approved') is not True or review.get('evaluation_sha256')!=sha(evaluation):
        raise ValueError('A matching final semantic review is required before promotion')
    adapter=RUN/'checkpoint-epoch-2';package(adapter,evaluation)
    for path in [ROOT/'config/serving.qwen4b.json',ROOT/'config/common-gateway.qwen4b.example.json',REPO/'.runtime/qwen4b-live/gateway.json']:
        backup=path.with_name(path.name+'.before-healthmon-sft-v1')
        if backup.exists():raise ValueError('Existing promotion backup: '+str(backup))
        backup.write_bytes(path.read_bytes())
        config=json.loads(path.read_text(encoding='utf-8'))
        config.update(adapter_path=str(adapter),fine_tune_run='qwen4b-healthmon-sft-v1')
        # Preserve the previously measured low-latency inference configuration.
        path.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    (RUN/'promotion.json').write_text(json.dumps({'run':'qwen4b-healthmon-sft-v1','adapter_sha256':sha(adapter/'adapter_model.safetensors'),
        'evaluation_sha256':sha(evaluation),'semantic_review_sha256':sha(RUN/'final-evaluation/semantic-review.json'),
        'previous_adapter_retained':True,'inference_optimizations_retained':True},indent=2),encoding='utf-8')
    print('Reviewed Healthmon SFT adapter selected; restart the GPU server to activate it.')

if __name__=='__main__':main()
