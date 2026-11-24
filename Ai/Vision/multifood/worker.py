"""One CPU photo per process, using the team's multi-food pipeline."""
import base64
import contextlib
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'aihub'))
sys.path.insert(0, str(ROOT.parents[2]))
from assets import BACKEND


def thumbnail(image, bound):
    from PIL import Image
    preview = image.copy()
    preview.thumbnail((bound, bound), Image.Resampling.LANCZOS)
    stream = io.BytesIO()
    preview.save(stream, format='JPEG', quality=72, optimize=True)
    return base64.b64encode(stream.getvalue()).decode('ascii')


def nutrition(values):
    result = {}
    for target, source in [('calories', 'energy_kcal_100g'), ('carbs', 'carbohydrate_g_100g'),
                           ('protein', 'protein_g_100g'), ('fat', 'fat_g_100g')]:
        value = values.get(source)
        valid = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0
        result[target] = float(value) if valid else 0.0
        result['has_' + target] = valid
    return result


def response(payload, image, request_id):
    foods = []
    for item in payload['foods']:
        mass = item.get('weight_g')
        valid = mass is not None and math.isfinite(mass) and 0 < mass <= 10000
        info = item.get('nutrition') or {}
        x1, y1, x2, y2 = item['classification_crop_xyxy']
        foods.append(dict(id=item['id'], class_id=item['class_id'], name=item['name'],
            grams=float(mass) if valid else 0.0, has_weight=valid,
            weight_status=item['weight_status'] if valid else 'requires_user_weight',
            name_confidence=item['name_confidence'], bbox=item['bbox_normalized_xyxy'],
            per100=nutrition(info.get('per_100g', {})),
            crop_base64=thumbnail(image.crop((x1, y1, x2, y2)), 192),
            nutrition_source=info.get('matched_food_name') or '',
            nutrition_confidence=info.get('reference_confidence') or '', name_edited=False, weight_edited=False))
    candidates = []
    for item in foods[:3]:
        n = item['per100']
        per100 = {target: n[source] if n['has_' + source] else None for target, source in
                  [('energy_kcal', 'calories'), ('carbohydrate_g', 'carbs'), ('protein_g', 'protein'), ('fat_g', 'fat')]}
        candidates.append(dict(food=item['name'], confidence=item['name_confidence'], per_100g=per100,
                               estimated_grams=item['grams'] if item['has_weight'] else None))
    return {'backend': BACKEND, 'candidates': candidates, 'vision': {
        'schema_version': 1, 'analysis_id': request_id, 'image_width': image.width, 'image_height': image.height,
        'original_base64': thumbnail(image, 1024), 'annotated_base64': '', 'foods': foods}}


def analyze(path, request_id):
    import torch
    from PIL import Image
    from region_model import load
    from food2k import FoodClassifier, predict_food2k
    from fpb_weight import estimate
    torch.set_num_threads(4)
    with Image.open(path) as photo:
        if photo.format not in ('JPEG', 'PNG') or photo.width * photo.height > 16000000:
            raise ValueError('Invalid photo')
        photo.verify()
    locator = load(ROOT / 'models/food_regions.pth', 'cpu')
    classifier = FoodClassifier(ROOT / 'models/classifier.pkl', ROOT / 'nutrition.csv', 'cpu', 'csv')
    payload, image = predict_food2k(classifier, locator, path)
    if not payload['foods']:
        raise ValueError('no_food_detected')
    if len(payload['foods']) > 32:
        raise ValueError('too_many_food_regions')
    with tempfile.TemporaryDirectory(prefix='healthmon-food-') as temporary:
        estimate(payload, image, temporary, 'cpu', ROOT / 'models/portion.pt')
    return response(payload, image, request_id)


def main():
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    job = json.loads(sys.stdin.readline())
    with tempfile.TemporaryDirectory(prefix='healthmon-food-cache-') as cache:
        os.environ.update(CUDA_VISIBLE_DEVICES='', YOLO_AUTOINSTALL='false',
                          YOLO_CONFIG_DIR=cache, MPLCONFIGDIR=cache)
        try:
            with contextlib.redirect_stdout(sys.stderr):
                result = analyze(job['image'], job['id'])
            output = {'id': job['id'], 'result': result}
        except Exception as error:
            traceback.print_exc(file=sys.stderr)
            output = {'id': job['id'], 'error': type(error).__name__,
                      'no_food': str(error) == 'no_food_detected', 'invalid_image': isinstance(error, ValueError)}
        print(json.dumps(output, ensure_ascii=False, allow_nan=False), flush=True)


if __name__ == '__main__':
    main()
