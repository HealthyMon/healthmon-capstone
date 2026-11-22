"""Promote the reviewed natural-dialogue adapter; retain rollback configurations."""
import json
import re
from pathlib import Path
from package_qwen4b import package

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
RUN = ROOT / 'runs/qwen4b-natural-v1'

def main():
    evaluation = RUN / 'final-generation.json'
    report = json.loads(evaluation.read_text(encoding='utf-8'))
    leaked = []
    for row in report['results']:
        if not row['contract_valid']:
            raise ValueError('Invalid response contract: ' + row['id'])
        speech = json.loads(row['raw'])['speech']
        if re.search(r'반말|존댓말|존대말|speech_level|casual|formal|말투 설정|성격축|내부 지침', speech, re.I):
            leaked.append(row['id'])
    if leaked:
        raise ValueError('Style narration remains: ' + ', '.join(leaked))
    adapter = RUN / 'checkpoint-epoch-2'
    package(adapter, evaluation)
    targets = [ROOT / 'config/serving.qwen4b.json', ROOT / 'config/common-gateway.qwen4b.example.json',
               REPO / '.runtime/qwen4b-live/gateway.json']
    for path in targets:
        backup = path.with_name(path.name + '.before-natural-v1')
        if backup.exists():
            raise ValueError('Promotion backup already exists: ' + str(backup))
    for path in targets:
        path.with_name(path.name + '.before-natural-v1').write_bytes(path.read_bytes())
        config = json.loads(path.read_text(encoding='utf-8'))
        config['adapter_path'] = str(adapter)
        config['fine_tune_run'] = 'qwen4b-natural-v1'
        path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {'run': 'qwen4b-natural-v1', 'adapter_path': str(adapter),
               'generation_cases': report['count'], 'contract_valid': report['contract_valid'],
               'unsolicited_style_narration_cases': len(leaked), 'prior_adapter_retained': True,
               'scope': 'Final real-model generation batch; not proof of all possible dialogue quality'}
    (RUN / 'promotion.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary))

if __name__ == '__main__': main()
