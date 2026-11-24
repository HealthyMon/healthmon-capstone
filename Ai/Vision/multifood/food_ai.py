"""Food detection and estimated mass, using the official FPB multitask fork."""
import argparse
import json
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT / '.yolo'))
os.environ.setdefault('MPLCONFIGDIR', str(ROOT / '.matplotlib'))
DEFAULT_MODEL = ROOT / 'assets' / 'Model Weights' / 'YOLOv12S.pt'

def load_model(path=DEFAULT_MODEL):
    from ultralytics import YOLO
    path = Path(path)
    if not path.is_file() or path.stat().st_size < 1024:
        raise FileNotFoundError(f'Actual checkpoint required: {path}. Run download.py first.')
    return YOLO(str(path), task='detect')

def format_result(result, threshold):
    height, width = result.orig_shape
    boxes = result.boxes.data.detach().cpu().tolist()
    mtl = getattr(result, 'mtl', None)
    if mtl is None or len(mtl) != len(boxes):
        raise RuntimeError('Requires the official FPB fork with aligned mtl weight predictions')
    weights = mtl.detach().cpu().tolist()
    foods = []
    for row, extra in zip(boxes, weights):
        x1, y1, x2, y2, confidence, class_id = row
        if not all(math.isfinite(x) for x in row) or confidence < threshold:
            continue
        x1, x2 = max(0., min(width, x1)), max(0., min(width, x2))
        y1, y2 = max(0., min(height, y1)), max(0., min(height, y2))
        if x2 <= x1 or y2 <= y1:
            continue
        grams = extra[2]
        valid_weight = math.isfinite(grams) and grams > 0
        foods.append({'id': len(foods), 'class_id': int(class_id), 'name': result.names[int(class_id)],
                      'confidence': round(confidence, 5), 'bbox_xyxy': [round(v, 2) for v in (x1, y1, x2, y2)],
                      'bbox_normalized_xyxy': [x1 / width, y1 / height, x2 / width, y2 / height],
                      'weight_g': round(grams, 1) if valid_weight else None,
                      'weight_status': 'estimated' if valid_weight else 'unavailable',
                      'needs_weight_confirmation': True})
    return {'schema_version': 1, 'image_size': {'width': width, 'height': height},
            'coordinate_system': 'exif_corrected_image_pixels_xyxy', 'foods': foods,
            'note': 'Weight is an RGB-model estimate, not a measurement. Labels are FPB classes; unknown dishes may be misclassified.'}

def predict(model, image, device='cpu', confidence=0.35):
    from PIL import Image, ImageOps
    if not 0 <= confidence <= 1:
        raise ValueError('confidence must be between 0 and 1')
    if isinstance(image, (str, Path)):
        with Image.open(image) as opened:
            image = ImageOps.exif_transpose(opened).convert('RGB')
    else:
        image = ImageOps.exif_transpose(image).convert('RGB')
    result = model.predict(source=image, imgsz=640, device=device, conf=confidence, verbose=False)[0]
    return format_result(result, confidence), image

def save_result(payload, image, directory):
    from PIL import ImageDraw
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    canvas = image.copy()
    draw = ImageDraw.Draw(canvas)
    for food in payload['foods']:
        box = food['bbox_xyxy']
        crop = f"food_{food['id']:03d}.jpg"
        image.crop(tuple(map(int, box))).save(directory / crop)
        food['crop_file'] = crop
        draw.rectangle(box, outline='#36bc55', width=3)
        draw.text((box[0], max(0, box[1] - 14)), f"{food['id']}: {food['name']} ~{food['weight_g']} g", fill='#ef3030')
    canvas.save(directory / 'annotated.jpg')
    (directory / 'result.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('image', type=Path)
    parser.add_argument('--model', type=Path, default=DEFAULT_MODEL)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--confidence', type=float, default=0.35)
    parser.add_argument('--output', type=Path, default=ROOT / 'outputs' / 'prediction')
    args = parser.parse_args()
    payload, image = predict(load_model(args.model), args.image, args.device, args.confidence)
    save_result(payload, image, args.output)
    print(json.dumps(payload, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
