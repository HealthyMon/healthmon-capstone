"""CPU-only check that the PNG's actual text follows the selected model SHA."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import pytest


ROOT = Path(__file__).resolve().parents[2]


def candidate(phase, text):
    result = {'speech': text}
    hashed = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'phase': phase, 'candidate_sha256': hashed, 'result': result,
            'quality': {'passed': True, 'failures': []}, 'contract_valid': True}


@pytest.mark.skipif(os.name != 'nt', reason='The Windows acceptance renderer uses System.Drawing.')
@pytest.mark.parametrize('selected_index', [0, 2])
@pytest.mark.parametrize('long_text', [False, True])
def test_actual_png_text_uses_selected_original_or_later_refinement(selected_index, long_text):
    powershell = shutil.which('powershell')
    if not powershell:
        pytest.skip('Windows PowerShell is required by the local acceptance renderer.')
    runtime = ROOT / '.runtime'
    runtime.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='renderer-regression-', dir=runtime) as directory:
        directory = Path(directory)
        suffix = (' 긴 문장이 다른 열을 넘거나 마지막 문장이 잘리지 않도록 실제 줄바꿈과 높이를 검증합니다.' * 7
                  + ' 마지막 문장까지 표시합니다.') if long_text else ''
        candidates = [candidate('original', 'Original generated candidate.' + suffix),
                      candidate('refined', 'Rejected or unselected first refinement.' + suffix),
                      candidate('refined', 'Selected second refinement.' + suffix)]
        selected = candidates[selected_index]
        report = {'cases': [{'case_id': 'fictional-renderer-selection', 'suite': 'neutral',
                    'automatic_quality': {'passed': True}, 'model_candidates': candidates,
                    'metrics': {'quality_refinement': {'selected_candidate': selected['phase'],
                        'selected_candidate_sha256': selected['candidate_sha256']}}}]}
        report_path = directory / 'report.json'
        report_path.write_text(json.dumps(report), encoding='utf-8')
        subprocess.run([powershell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(ROOT / 'Server/local_probe/render_refinement_review.ps1'),
                        '-Report', str(report_path)], check=True, capture_output=True, timeout=30)
        audit = json.loads((directory / 'rendered-candidate-audit.json').read_text(encoding='utf-8-sig'))
        displayed = next(row for row in audit if row['column'] == 'refined')
        original = next(row for row in audit if row['column'] == 'original')
        assert displayed['candidate_sha256'] == selected['candidate_sha256']
        assert displayed['speech_sha256'] == hashlib.sha256(selected['result']['speech'].encode()).hexdigest()
        assert original['candidate_sha256'] == candidates[0]['candidate_sha256']
        for row in audit:
            assert row['word_wrap'] is True
            assert row['characters_fitted'] == row['text_length']
            assert row['layout_height'] >= row['measured_height']
            assert row['bottom'] < row['codes_top'] <= row['codes_bottom'] < row['row_bottom']
            assert row['row_bottom'] < row['canvas_height']
            assert 0 <= row['left'] < row['right'] < row['canvas_width']
            if long_text:
                assert row['line_count'] >= 3
        assert original['right'] < displayed['left']
        assert (directory / 'neutral-original-refined.png').is_file()
        assert (directory / 'native-original-refined.png').is_file()
