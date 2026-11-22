"""Match FPB mass predictions to existing food regions without duplicating masses."""
import json
import math
import subprocess
import tempfile
from pathlib import Path
from detect import ROOT, overlap

DEFAULT_REPO = ROOT.parent/'음식 탐지/Multitask-Food-Portion-Estimation'
DEFAULT_MODEL = DEFAULT_REPO/'YOLOv12XL.pt'
DEFAULT_PYTHON = ROOT.parent/'.venv/Scripts/python.exe'


def coverage(box, target):
    area = max(0,target[2]-target[0])*max(0,target[3]-target[1])
    intersection = max(0,min(box[2],target[2])-max(box[0],target[0])) * max(0,min(box[3],target[3])-max(box[1],target[1]))
    return intersection/area if area else 0


def attach(payload, prediction, min_iou=.5):
    if payload['image_size'] != prediction['image_size']:
        raise ValueError('Weight and locator images must share upright pixel coordinates')
    foods, proposals = payload['foods'], prediction['foods']
    scores = [[overlap(f['bbox_xyxy'],p['bbox_xyxy']) for p in proposals] for f in foods]
    # A weight box covering two locator regions cannot be divided reliably.
    shared = {j for j,p in enumerate(proposals)
              if sum(coverage(p['bbox_xyxy'],f['bbox_xyxy']) >= .5 for f in foods) > 1}
    for i, food in enumerate(foods):
        food.update(weight_g=None, weight_status='no_matching_weight_detection',
                    weight_details={'method':'fpb_yolov12', 'match_iou_threshold':min_iou})
        candidates = [j for j,s in enumerate(scores[i]) if s >= min_iou]
        if not candidates:
            continue
        j = candidates[0]
        if len(candidates)!=1 or j in shared or sum(row[j]>=min_iou for row in scores)!=1:
            food['weight_status'] = 'ambiguous_weight_match'
            continue
        proposal = proposals[j]
        grams = proposal['weight_g']
        if grams is None or not math.isfinite(grams) or grams <= 0:
            food['weight_status'] = 'invalid_weight_prediction'
            continue
        food.update(weight_g=grams, weight_status='estimated_fpb_yolov12',
                    weight_details={'method':'fpb_yolov12', 'match_iou':scores[i][j],
                                    'fpb_detection_id':proposal['id'], 'fpb_class_id':proposal['class_id'],
                                    'fpb_name':proposal['name'], 'fpb_confidence':proposal['confidence'],
                                    'fpb_bbox_xyxy':proposal['bbox_xyxy']})
    payload['weight_estimator'] = {'model':prediction.get('model'),
                                  'implementation':prediction.get('implementation'),
                                  'matching':'unique IoU >= 0.5; reject boxes covering multiple foods',
                                  'detections':proposals}


def estimate(payload, image, output, device='cuda:0', model=DEFAULT_MODEL):
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fpb_',dir=output) as temp:
        temp = Path(temp)
        # Lossless and already EXIF-corrected: both models use identical coordinates.
        image.save(temp/'input.png')
        regions = []
        for food in payload['foods']:
            b = food['bbox_xyxy']
            crop = [max(0,math.floor(b[0])),max(0,math.floor(b[1])),
                    min(image.width,math.ceil(b[2])),min(image.height,math.ceil(b[3]))]
            if crop[2]<=crop[0] or crop[3]<=crop[1]:
                raise ValueError('Invalid food crop for weight prediction')
            regions.append({'id':food['id'],'crop_xyxy':crop})
        (temp/'regions.json').write_text(json.dumps(regions),encoding='utf-8')
        command = [str(DEFAULT_PYTHON),str(ROOT/'fpb_worker.py'), '--repo',str(DEFAULT_REPO),
                   '--model',str(model),'--image',str(temp/'input.png'),
                   '--output',str(temp/'prediction.json'),'--device',device,
                   '--regions',str(temp/'regions.json')]
        process = subprocess.run(command,capture_output=True)
        (output/'weight_inference.log').write_bytes(process.stdout+process.stderr)
        if process.returncode:
            raise RuntimeError(f'FPB inference failed; see {output / "weight_inference.log"}')
        prediction = json.loads((temp/'prediction.json').read_text(encoding='utf-8'))
    attach_crops(payload,prediction)


def attach_crops(payload,prediction):
    rows = prediction['foods']
    by_id = {r['id']:r for r in rows}
    if len(by_id)!=len(rows) or set(by_id)!={f['id'] for f in payload['foods']}:
        raise ValueError('Crop weight outputs must match every input food ID exactly')
    for food in payload['foods']:
        row = by_id[food['id']]
        if not math.isfinite(row['weight_g']) or row['weight_g']<=0:
            raise ValueError('Invalid crop weight prediction')
        food.update(weight_g=row['weight_g'],weight_status=row['weight_status'],
                    weight_details=dict(row,method='fpb_per_food_crop'),
                    needs_weight_confirmation=row['needs_weight_confirmation'])
    payload['weight_estimator'] = {'model':prediction.get('model'),
                                  'implementation':prediction.get('implementation'),
                                  'method':'per_crop_raw_weight_regression',
                                  'note':'One mass proposal per crop, including low-confidence predictions; no whole-image box matching.'}
