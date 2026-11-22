"""Select the completed parameter-priority run without evaluation, as requested."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1]
RUN=ROOT/'runs/qwen4b-axis-priority-v1'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    selection=json.loads((RUN/'selection.json').read_text(encoding='utf-8'))
    adapter=RUN/'checkpoint-epoch-2'
    if not selection['trained'] or Path(selection['selected']['path']).resolve()!=adapter.resolve():
        raise RuntimeError('Expected final training checkpoint is not complete')
    source=json.loads((ROOT/'models/qwen3.5-4b/healthmon-source.json').read_text(encoding='utf-8'))
    manifest={'model_version':'qwen4b-v1','status':'ready','format':'peft_lora',
        'base_model_id':source['model_id'],'base_revision':source['revision'],
        'base_config_sha256':sha(ROOT/'models/qwen3.5-4b/config.json'),
        'artifact_checksums':{n:sha(adapter/n) for n in ['adapter_config.json','adapter_model.safetensors']},
        'training_quantization':'nf4','fine_tune_run':'qwen4b-axis-priority-v1',
        'evaluation_skipped_by_user':True,'production_quality_approved':False,'nine_b_parity_verified':False,
        'readiness_scope':'loadable completed checkpoint; no response comparison or validation requested'}
    (adapter/'healthmon-model.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    for p in [ROOT/'config/serving.qwen4b.json',ROOT/'config/common-gateway.qwen4b.example.json',REPO/'.runtime/qwen4b-live/gateway.json']:
        backup=p.with_name(p.name+'.before-axis-priority-v1')
        if not backup.exists():backup.write_bytes(p.read_bytes())
        config=json.loads(p.read_text(encoding='utf-8'));config.update(adapter_path=str(adapter),fine_tune_run='qwen4b-axis-priority-v1')
        p.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    report={'run':'qwen4b-axis-priority-v1','adapter_sha256':manifest['artifact_checksums']['adapter_model.safetensors'],
        'validation_skipped_by_user':True,'previous_adapter_retained':True,'inference_optimizations_retained':True}
    (RUN/'promotion.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    status=ROOT/'QWEN4B_STATUS.json';data=json.loads(status.read_text(encoding='utf-8'))
    data.update(current_serving_run='qwen4b-axis-priority-v1',axis_priority_update=report)
    status.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Final parameter-priority checkpoint selected without validation.',flush=True)

if __name__=='__main__':main()
