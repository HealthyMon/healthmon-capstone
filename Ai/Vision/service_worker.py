"""Private JSON-lines worker for the shared API; uses the team's CPU environment."""
import contextlib
import functools
import json
import sys
import traceback
import warnings
from pathlib import Path


def analyze(path):
    from PIL import Image
    import main as vision

    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(path) as image:
            if image.format not in ('JPEG', 'PNG') or image.width * image.height > 16_000_000:
                raise ValueError('Use a JPEG or PNG image up to 16 megapixels.')
            image.verify()
    result = vision.predict(Path(path), device='cpu')
    database = vision.read_nutrition(vision.ROOT / 'nutrition.json')
    candidates, seen = [], set()
    for item in sorted(result['detections'] + result['candidates'], key=lambda x: x['confidence'], reverse=True):
        if item['food'] in seen:
            continue
        seen.add(item['food'])
        candidates.append({'food': item['food'], 'confidence': item['confidence'],
                           'per_100g': vision.nutrition_for(item['food'], database)['per_100g']})
        if len(candidates) == 3:
            break
    grams, warning = None, ''
    if len(result['detections']) == 1:
        try:
            coordinates = vision.automatic_cuboid(Path(path))
            grams = vision.predict_weight(Path(path), coordinates)['predicted_g']
        except (ValueError, OSError) as error:
            warning = str(error)
    elif candidates:
        warning = '사진 전체의 중량을 개별 음식의 섭취량으로 사용할 수 없습니다.'
    for item in candidates:
        # A whole-photo estimate belongs only to the unique detected food.
        item['estimated_grams'] = grams if len(result['detections']) == 1 and item['food'] == result['detections'][0]['food'] else None
        item['weight_warning'] = warning
    return {'candidates': candidates, 'detected_count': len(result['detections']),
            'backend': 'team-fasterrcnn-swin-resnet18-cpu'}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stdin.reconfigure(encoding='utf-8')
    with contextlib.redirect_stdout(sys.stderr):
        import torch
        import main as vision
        torch.set_num_threads(4)
        vision.restore_model = functools.lru_cache(maxsize=1)(vision.restore_model)
        vision.restore_weight = functools.lru_cache(maxsize=1)(vision.restore_weight)
    for line in sys.stdin:
        job = json.loads(line)
        try:
            with contextlib.redirect_stdout(sys.stderr):
                output = analyze(job['image'])
            response = {'id': job['id'], 'result': output}
        except Exception as error:
            traceback.print_exc(file=sys.stderr)
            response = {'id': job['id'], 'error': type(error).__name__,
                        'invalid_image': isinstance(error, (ValueError, OSError))}
        print(json.dumps(response, ensure_ascii=False, allow_nan=False), flush=True)
        break  # One photo per process: release every model allocation before the next job.


if __name__ == '__main__':
    main()
