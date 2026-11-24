"""AI Hub 800-class multi-food inference. Coordinates refer to upright input."""
import argparse
import hashlib
import json
import math
import os
import collections
import pickle
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault('MPLCONFIGDIR', str(ROOT.parent / '.matplotlib'))
DEFAULT_WEIGHT = ROOT.parent / '01.음식 탐지 및 분류 모델' / '학습모델파일.pth'

class TensorUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        import torch
        if (module,name)==('collections','OrderedDict'):
            return collections.OrderedDict
        if module=='torch._utils' and name in ('_rebuild_tensor_v2','_rebuild_parameter'):
            return getattr(torch._utils,name)
        if module=='torch' and name in ('FloatStorage','LongStorage','HalfStorage','DoubleStorage','IntStorage','ByteStorage','BoolStorage'):
            return getattr(torch,name)
        raise pickle.UnpicklingError(f'Unsupported checkpoint object: {module}.{name}')

SAFE_PICKLE=types.SimpleNamespace(__name__='tensor_checkpoint',Unpickler=TensorUnpickler,
                                  load=lambda stream,**kw:TensorUnpickler(stream,**kw).load())

def checkpoint(path):
    import torch
    path = Path(path)
    if not path.is_file() or path.stat().st_size < 1024:
        raise ValueError(f'Actual checkpoint required, not a Git LFS pointer: {path}')
    return torch.load(str(path), map_location='cpu', pickle_module=SAFE_PICKLE)

def load_model(path=DEFAULT_WEIGHT, device='cuda:0'):
    from mmcv import Config
    from mmdet.models import build_detector
    ckpt = checkpoint(path)
    names = tuple(ckpt['meta']['CLASSES'])
    cfg = Config.fromfile(str(ROOT / 'detector_config.py'))
    cfg.model.init_cfg = None
    cfg.model.backbone.init_cfg = None
    cfg.model.backbone.pretrained = None
    cfg.model.roi_head.bbox_head.num_classes = len(names)
    model = build_detector(cfg.model, test_cfg=cfg.get('test_cfg'))
    model.load_state_dict(ckpt['state_dict'], strict=True)
    model.cfg, model.CLASSES = cfg, names
    return model.to(device).eval()

def overlap(a, b):
    inter = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / union if union > 0 else 0

def detections(raw, names, size, threshold=.35, duplicate_iou=.85):
    width, height = size
    found = []
    for class_id, boxes in enumerate(raw):
        for x1, y1, x2, y2, score in boxes:
            if not all(math.isfinite(float(x)) for x in (x1,y1,x2,y2,score)) or score < threshold:
                continue
            box = [max(0., min(width, float(x1))), max(0., min(height, float(y1))),
                   max(0., min(width, float(x2))), max(0., min(height, float(y2)))]
            if box[2]-box[0] < 1 or box[3]-box[1] < 1:
                continue
            found.append({'class_id': class_id, 'name': names[class_id], 'confidence': float(score), 'bbox_xyxy': box})
    kept = []
    for item in sorted(found, key=lambda x:x['confidence'], reverse=True):
        # Suppress near-identical boxes bearing competing class names, not spatially separate same-class plates.
        if duplicate_iou < 1 and any(overlap(item['bbox_xyxy'], x['bbox_xyxy']) > duplicate_iou for x in kept):
            continue
        kept.append(item)
    for i, item in enumerate(kept):
        box = item['bbox_xyxy']
        item.update(id=i, bbox_normalized_xyxy=[box[0]/width,box[1]/height,box[2]/width,box[3]/height],
                    weight_g=None, weight_status='requires_existing_cuboid_pipeline')
    return kept

def predict(model, path, threshold=.35, duplicate_iou=.85):
    from PIL import Image, ImageOps
    import numpy as np
    from mmdet.apis import inference_detector
    if not 0 <= threshold <= 1 or not 0 <= duplicate_iou <= 1:
        raise ValueError('Threshold and duplicate IoU must be between 0 and 1')
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert('RGB')
    raw = inference_detector(model, np.asarray(image)[:,:,::-1].copy())
    return {'schema_version': 2, 'image_size': {'width':image.width,'height':image.height},
            'coordinate_system':'exif_corrected_image_pixels_xyxy', 'region_type':'food_not_plate',
            'foods':detections(raw, model.CLASSES, image.size, threshold, duplicate_iou)}, image

def predict_regions(model,locator,path,region_threshold=.5,name_threshold=.5):
    from PIL import Image,ImageOps
    from region_model import locate
    from mmdet.apis import inference_detector
    import numpy as np
    with Image.open(path) as source:
        image=ImageOps.exif_transpose(source).convert('RGB')
    foods=[]
    for proposal in locate(locator,image,region_threshold):
        box=proposal['bbox_xyxy']
        x1,y1,x2,y2=map(int,box)
        if x2<=x1 or y2<=y1:continue
        crop=image.crop((x1,y1,x2,y2))
        raw=inference_detector(model,np.asarray(crop)[:,:,::-1].copy())
        candidates=detections(raw,model.CLASSES,crop.size,.05,.85)
        candidates=[c for c in candidates if overlap(c['bbox_xyxy'],[0,0,crop.width,crop.height])>=.25]
        best=max(candidates,key=lambda c:c['confidence'],default=None)
        accepted=best is not None and best['confidence']>=name_threshold
        foods.append({'id':len(foods),'bbox_xyxy':box,
                      'bbox_normalized_xyxy':[box[0]/image.width,box[1]/image.height,box[2]/image.width,box[3]/image.height],
                      'confidence':proposal['confidence'],'localization_confidence':proposal['confidence'],
                      'class_id':best['class_id'] if accepted else None,'name':best['name'] if accepted else '미확인 음식',
                      'name_confidence':best['confidence'] if best else None,
                      'name_status':'predicted_closed_set' if accepted else 'needs_user_selection',
                      'candidates':[{'class_id':c['class_id'],'name':c['name'],'confidence':c['confidence']} for c in candidates[:3]],
                      'weight_g':None,'weight_status':'requires_existing_cuboid_pipeline'})
    return {'schema_version':2,'image_size':{'width':image.width,'height':image.height},
            'coordinate_system':'exif_corrected_image_pixels_xyxy','region_type':'food_not_plate',
            'pipeline':'trained_food_locator_then_unchanged_aihub800','foods':foods},image

def save(payload, image, directory):
    from PIL import ImageDraw, ImageFont
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)
    fontpath = Path('C:/Windows/Fonts/malgun.ttf')
    font = ImageFont.truetype(str(fontpath), max(16, image.width//55)) if fontpath.exists() else ImageFont.load_default()
    for food in payload['foods']:
        box = food['bbox_xyxy']
        food['crop_file'] = f"food_{food['id']:03d}.jpg"
        image.crop(tuple(map(int, box))).save(directory / food['crop_file'])
        label = food['name']
        draw.rectangle(box, outline='#00b861', width=max(2,image.width//350))
        xy = (box[0], max(0,box[1]-max(22,image.width//45)))
        draw.rectangle(draw.textbbox(xy,label,font=font), fill='#005b31')
        draw.text(xy,label,font=font,fill='white')
    annotated.save(directory/'annotated.jpg')
    if payload.get('pipeline') == 'dishseg_locator_then_noisyvit_food2k':
        from food_overlay import render
        render(payload, image, directory)
    image.save(directory/'input_upright.jpg')
    (directory/'result.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('image', type=Path)
    p.add_argument('--model', type=Path, default=DEFAULT_WEIGHT)
    p.add_argument('--device', default='cuda:0')
    p.add_argument('--threshold', type=float, default=.35)
    p.add_argument('--duplicate-iou', type=float, default=.85, help='1 disables cross-class duplicate suppression')
    p.add_argument('--output', type=Path, default=ROOT.parent/'outputs/aihub')
    p.add_argument('--weight-labels', type=Path, help='JSON mapping detection ID to an existing per-food cuboid label path')
    p.add_argument('--regions',type=Path,help='Trained food_regions.pth; enables multi-food locator + original naming model')
    p.add_argument('--region-threshold',type=float,default=.5)
    p.add_argument('--name-threshold',type=float,default=.5)
    p.add_argument('--classifier', choices=['aihub', 'food2k'], default='aihub')
    p.add_argument('--food2k-model', type=Path)
    p.add_argument('--nutrition-csv', type=Path)
    p.add_argument('--class-order', choices=['auto','csv','imagefolder','numeric'], default='auto')
    p.add_argument('--weight-backend', choices=['fpb','legacy','none'], default='fpb')
    p.add_argument('--fpb-model', type=Path)
    a=p.parse_args()
    if a.weight_labels and a.weight_backend != 'legacy':
        p.error('--weight-labels requires --weight-backend legacy')
    import torch
    torch.set_num_threads(4)
    if a.classifier == 'food2k' and not a.regions:
        p.error('Food2K classification requires --regions')
    if a.regions:
        from region_model import load
        if not 0<=a.region_threshold<=1 or not 0<=a.name_threshold<=1:
            p.error('Thresholds must be in [0,1]')
        locator=load(a.regions,a.device)
        if a.classifier == 'food2k':
            from food2k import FoodClassifier, DEFAULT_MODEL, DEFAULT_CSV, predict_food2k
            model=FoodClassifier(a.food2k_model or DEFAULT_MODEL,a.nutrition_csv or DEFAULT_CSV,a.device,a.class_order)
            payload,image=predict_food2k(model,locator,a.image,a.region_threshold,a.name_threshold)
        else:
            model=load_model(a.model,a.device)
            payload,image=predict_regions(model,locator,a.image,a.region_threshold,a.name_threshold)
    else:
        model=load_model(a.model,a.device)
        payload,image=predict(model,a.image,a.threshold,a.duplicate_iou)
    if a.weight_labels:
        from PIL import Image
        from legacy_weight import restore_weight, predict_weight
        with Image.open(a.image) as source:
            if source.getexif().get(274,1)!=1:
                raise ValueError('Legacy cuboid labels require orientation-normalized input and matching coordinates')
        mapping=json.loads(a.weight_labels.read_text(encoding='utf-8-sig'))
        valid_ids={str(f['id']) for f in payload['foods']}
        if set(mapping)-valid_ids:
            raise ValueError('Weight label map contains unknown detection IDs; inspect detection JSON first')
        weight_model=restore_weight(a.device)
        for food in payload['foods']:
            if str(food['id']) in mapping:
                label=Path(mapping[str(food['id'])])
                if not label.is_absolute():
                    label=a.weight_labels.parent/label
                value=predict_weight(a.image,label,a.device,weight_model)
                food.update(weight_g=value['predicted_g'],weight_status='estimated_legacy_cuboid',weight_details=value)
    if a.weight_backend == 'fpb':
        from fpb_weight import estimate, DEFAULT_MODEL as FPB_MODEL
        estimate(payload,image,a.output,a.device,a.fpb_model or FPB_MODEL)
    elif a.weight_backend == 'none':
        for food in payload['foods']:
            food.update(weight_g=None,weight_status='disabled')
    if a.classifier == 'food2k':
        from food2k import add_portions
        add_portions(payload)
    save(payload,image,a.output)
    print(json.dumps(payload,ensure_ascii=True,indent=2))

if __name__=='__main__':
    main()
