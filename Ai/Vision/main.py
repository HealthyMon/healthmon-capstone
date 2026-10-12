import argparse
import collections
import csv
import hashlib
import io
import json
import math
import pickle
import sys
import types
import unicodedata
from pathlib import Path
ROOT = Path(__file__).resolve().parent
NUTRIENTS = ('energy_kcal', 'carbohydrate_g', 'protein_g', 'fat_g', 'sugar_g', 'fiber_g', 'sodium_mg')
EXPECTED_SHA256 = '38282bbf4034c15e16c2ddb9384ba8714072a5bc71ef14f9b30c8eedd657514a'
MODEL_CONFIG = "load_from = '/home/jovyan/mmdetection/afs_faster_swin/iter_200000.pth'\nmodel = dict(\n    init_cfg=dict(\n        type='Pretrained',\n        checkpoint='/home/jovyan/mmdetection/afs_faster_swin/iter_200000.pth'),\n    type='FasterRCNN',\n    backbone=dict(\n        type='SwinTransformer',\n        embed_dims=96,\n        depths=[2, 2, 18, 2],\n        num_heads=[3, 6, 12, 24],\n        window_size=7,\n        mlp_ratio=4,\n        qkv_bias=True,\n        qk_scale=None,\n        drop_rate=0.0,\n        attn_drop_rate=0.0,\n        drop_path_rate=0.2,\n        patch_norm=True,\n        out_indices=(0, 1, 2, 3),\n        with_cp=False,\n        convert_weights=True),\n    neck=dict(\n        type='FPN',\n        in_channels=[96, 192, 384, 768],\n        out_channels=256,\n        num_outs=5),\n    rpn_head=dict(\n        type='RPNHead',\n        in_channels=256,\n        feat_channels=256,\n        anchor_generator=dict(\n            type='AnchorGenerator',\n            scales=[8],\n            ratios=[0.5, 1.0, 2.0],\n            strides=[4, 8, 16, 32, 64]),\n        bbox_coder=dict(\n            type='DeltaXYWHBBoxCoder',\n            target_means=[0.0, 0.0, 0.0, 0.0],\n            target_stds=[1.0, 1.0, 1.0, 1.0]),\n        loss_cls=dict(\n            type='CrossEntropyLoss', use_sigmoid=True, loss_weight=1.0),\n        loss_bbox=dict(type='L1Loss', loss_weight=1.0)),\n    roi_head=dict(\n        type='StandardRoIHead',\n        bbox_roi_extractor=dict(\n            type='SingleRoIExtractor',\n            roi_layer=dict(type='RoIAlign', output_size=7, sampling_ratio=0),\n            out_channels=256,\n            featmap_strides=[4, 8, 16, 32]),\n        bbox_head=dict(\n            type='Shared2FCBBoxHead',\n            in_channels=256,\n            fc_out_channels=1024,\n            roi_feat_size=7,\n            num_classes=800,\n            bbox_coder=dict(\n                type='DeltaXYWHBBoxCoder',\n                target_means=[0.0, 0.0, 0.0, 0.0],\n                target_stds=[0.1, 0.1, 0.2, 0.2]),\n            reg_class_agnostic=False,\n            loss_cls=dict(\n                type='CrossEntropyLoss', use_sigmoid=False, loss_weight=1.0),\n            loss_bbox=dict(type='L1Loss', loss_weight=1.0))),\n    train_cfg=dict(\n        rpn=dict(\n            assigner=dict(\n                type='MaxIoUAssigner',\n                pos_iou_thr=0.7,\n                neg_iou_thr=0.3,\n                min_pos_iou=0.3,\n                match_low_quality=True,\n                ignore_iof_thr=-1),\n            sampler=dict(\n                type='RandomSampler',\n                num=256,\n                pos_fraction=0.5,\n                neg_pos_ub=-1,\n                add_gt_as_proposals=False),\n            allowed_border=-1,\n            pos_weight=-1,\n            debug=False),\n        rpn_proposal=dict(\n            nms_pre=2000,\n            max_per_img=1000,\n            nms=dict(type='nms', iou_threshold=0.7),\n            min_bbox_size=0),\n        rcnn=dict(\n            assigner=dict(\n                type='MaxIoUAssigner',\n                pos_iou_thr=0.5,\n                neg_iou_thr=0.5,\n                min_pos_iou=0.5,\n                match_low_quality=False,\n                ignore_iof_thr=-1),\n            sampler=dict(\n                type='RandomSampler',\n                num=512,\n                pos_fraction=0.25,\n                neg_pos_ub=-1,\n                add_gt_as_proposals=True),\n            pos_weight=-1,\n            debug=False)),\n    test_cfg=dict(\n        rpn=dict(\n            nms_pre=1000,\n            max_per_img=1000,\n            nms=dict(type='nms', iou_threshold=0.7),\n            min_bbox_size=0),\n        rcnn=dict(\n            score_thr=0.05,\n            nms=dict(type='nms', iou_threshold=0.5),\n            max_per_img=100)))\nimg_norm_cfg = dict(\n    mean=[123.675, 116.28, 103.53], std=[58.395, 57.12, 57.375], to_rgb=True)\ndataset_type = 'AmazingFoodDataset'\ndata_root = '/home/jovyan/sharedata-pvc-guenuk4/Food/final_dataset/img'\ntrain_pipeline = [\n    dict(type='LoadImageFromFile'),\n    dict(type='LoadAnnotations', with_bbox=True),\n    dict(type='Resize', img_scale=(1333, 800), keep_ratio=True),\n    dict(type='RandomFlip', flip_ratio=0.5),\n    dict(\n        type='Normalize',\n        mean=[123.675, 116.28, 103.53],\n        std=[58.395, 57.12, 57.375],\n        to_rgb=True),\n    dict(type='Pad', size_divisor=32),\n    dict(type='DefaultFormatBundle'),\n    dict(type='Collect', keys=['img', 'gt_bboxes', 'gt_labels'])\n]\ntest_pipeline = [\n    dict(type='LoadImageFromFile'),\n    dict(\n        type='MultiScaleFlipAug',\n        img_scale=(1333, 800),\n        flip=False,\n        transforms=[\n            dict(type='Resize', keep_ratio=True),\n            dict(type='RandomFlip'),\n            dict(\n                type='Normalize',\n                mean=[123.675, 116.28, 103.53],\n                std=[58.395, 57.12, 57.375],\n                to_rgb=True),\n            dict(type='Pad', size_divisor=32),\n            dict(type='ImageToTensor', keys=['img']),\n            dict(type='Collect', keys=['img'])\n        ])\n]\ndata = dict(\n    samples_per_gpu=2,\n    workers_per_gpu=2,\n    train=dict(\n        type='AmazingFoodDataset',\n        data_root='/home/jovyan/sharedata-pvc-guenuk4/Food/final_dataset/img',\n        ann_file='/home/jovyan/mmdetection/afs/afs_voc_txt/train.txt',\n        img_prefix='',\n        pipeline=[\n            dict(type='LoadImageFromFile'),\n            dict(type='LoadAnnotations', with_bbox=True),\n            dict(type='Resize', img_scale=(1333, 800), keep_ratio=True),\n            dict(type='RandomFlip', flip_ratio=0.5),\n            dict(\n                type='Normalize',\n                mean=[123.675, 116.28, 103.53],\n                std=[58.395, 57.12, 57.375],\n                to_rgb=True),\n            dict(type='Pad', size_divisor=32),\n            dict(type='DefaultFormatBundle'),\n            dict(type='Collect', keys=['img', 'gt_bboxes', 'gt_labels'])\n        ]),\n    val=dict(\n        type='AmazingFoodDataset',\n        data_root='/home/jovyan/sharedata-pvc-guenuk4/Food/final_dataset/img',\n        ann_file='/home/jovyan/mmdetection/afs/afs_voc_txt/val.txt',\n        img_prefix='',\n        pipeline=[\n            dict(type='LoadImageFromFile'),\n            dict(\n                type='MultiScaleFlipAug',\n                img_scale=(1333, 800),\n                flip=False,\n                transforms=[\n                    dict(type='Resize', keep_ratio=True),\n                    dict(type='RandomFlip'),\n                    dict(\n                        type='Normalize',\n                        mean=[123.675, 116.28, 103.53],\n                        std=[58.395, 57.12, 57.375],\n                        to_rgb=True),\n                    dict(type='Pad', size_divisor=32),\n                    dict(type='ImageToTensor', keys=['img']),\n                    dict(type='Collect', keys=['img'])\n                ])\n        ]),\n    test=dict(\n        type='AmazingFoodDataset',\n        data_root='/home/jovyan/sharedata-pvc-guenuk4/Food/final_dataset/img',\n        ann_file='/home/jovyan/mmdetection/afs/afs_voc_txt/test.txt',\n        img_prefix='',\n        pipeline=[\n            dict(type='LoadImageFromFile'),\n            dict(\n                type='MultiScaleFlipAug',\n                img_scale=(1333, 800),\n                flip=False,\n                transforms=[\n                    dict(type='Resize', keep_ratio=True),\n                    dict(type='RandomFlip'),\n                    dict(\n                        type='Normalize',\n                        mean=[123.675, 116.28, 103.53],\n                        std=[58.395, 57.12, 57.375],\n                        to_rgb=True),\n                    dict(type='Pad', size_divisor=32),\n                    dict(type='ImageToTensor', keys=['img']),\n                    dict(type='Collect', keys=['img'])\n                ])\n        ]))\nevaluation = dict(interval=120000, metric='mAP')\nwork_dir = './afs_faster_swin'\noptimizer = dict(type='SGD', lr=0.0025, momentum=0.9, weight_decay=0.0001)\noptimizer_config = dict(grad_clip=None)\nlr_config = dict(\n    policy='step',\n    warmup=None,\n    warmup_iters=500,\n    warmup_ratio=0.001,\n    step=[150000])\nrunner = dict(type='IterBasedRunner', max_iters=7680000)\ncheckpoint_config = dict(interval=40000)\nlog_config = dict(interval=10, hooks=[dict(type='TextLoggerHook')])\ncustom_hooks = [dict(type='NumClassCheckHook')]\ndist_params = dict(backend='nccl')\nlog_level = 'INFO'\nresume_from = None\nworkflow = [('train', 120000)]\nopencv_num_threads = 0\nmp_start_method = 'fork'\nauto_scale_lr = dict(enable=False, base_batch_size=128)\ndevice = 'cuda'\nauto_resume = False\ngpu_ids = [0]\n"

# .pth 로딩에 필요한 텐서와 OrderedDict만 허용한다. 다른 Python 객체는 복원하지 않는다.
class CheckpointUnpickler(pickle.Unpickler):

    def find_class(self, module, name):
        if (module, name) == ('collections', 'OrderedDict'):
            return collections.OrderedDict
        if (module, name) == ('torch._utils', '_rebuild_tensor_v2'):
            from torch._utils import _rebuild_tensor_v2
            return _rebuild_tensor_v2
        if module == 'torch' and name in ('FloatStorage', 'LongStorage'):
            import torch
            return getattr(torch, name)
        raise pickle.UnpicklingError(f'허용되지 않은 체크포인트 객체: {module}.{name}')

def restricted_load(file, **kwargs):
    return CheckpointUnpickler(file, **kwargs).load()
RESTRICTED_PICKLE = types.SimpleNamespace(__name__='restricted_checkpoint_pickle', Unpickler=CheckpointUnpickler, load=restricted_load, loads=lambda data, **kwargs: restricted_load(io.BytesIO(data), **kwargs))

def restore_model(device='cpu'):
    import torch
    from mmcv import Config
    from mmdet.models import build_detector
    path = ROOT / 'food_detector.pth'
    if not path.is_file():
        raise FileNotFoundError(f'가중치 파일이 없습니다: {path}')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != EXPECTED_SHA256:
        raise ValueError('제공된 원본과 가중치 해시가 다릅니다. 파일 손상을 확인하세요.')
    checkpoint = torch.load(str(path), map_location='cpu', weights_only=False, pickle_module=RESTRICTED_PICKLE)
    # 가중치는 로컬 파일에서 직접 불러온다. 설정에 남은 원본 서버 경로는 사용하지 않는다.
    cfg = Config.fromstring(MODEL_CONFIG, '.py')
    cfg.model.init_cfg = None
    cfg.model.backbone.init_cfg = None
    cfg.model.backbone.pretrained = None
    model = build_detector(cfg.model, test_cfg=cfg.get('test_cfg'))
    model.load_state_dict(checkpoint['state_dict'], strict=True)
    model.cfg = cfg
    model.CLASSES = tuple(checkpoint['meta']['CLASSES'])
    if len(model.CLASSES) != 800:
        raise ValueError('800종 음식 체크포인트가 아닙니다.')
    return model.to(device).eval()

def normalized_name(value):
    return unicodedata.normalize('NFC', value).strip()

def restore_weight_model(device='cpu'):
    import torch
    from torchvision.models import resnet18
    checkpoint = torch.load(str(ROOT / 'food_weight_checkpoint.pth'), map_location='cpu', weights_only=False, pickle_module=RESTRICTED_PICKLE)
    state = {k.removeprefix('model.'): v for k, v in checkpoint['state_dict'].items()}
    model = resnet18(weights=None)
    model.conv1 = torch.nn.Conv2d(4, 64, 7, stride=2, padding=3, bias=False)
    model.fc = torch.nn.Linear(512, 1)
    model.load_state_dict(state, strict=True)
    return model.to(device).eval()

def read_nutrition(path):
    if not path.is_file():
        return {}
    database = json.loads(path.read_text(encoding='utf-8-sig'))['foods']
    for name, record in database.items():
        for value in record['per_100g'].values():
            if value is not None and (not math.isfinite(value) or value < 0):
                raise ValueError(f'Invalid nutrient value: {name}')
    return database

def nutrition_for(food, database, grams=None):
    record = database.get(normalized_name(food))
    if record is None or all((v is None for v in record['per_100g'].values())):
        return {'status': 'unavailable', 'reason': '일치하는 영양성분 데이터가 없습니다.', 'per_100g': {key: None for key in NUTRIENTS}}
    result = {'status': 'matched' if all((v is not None for v in record['per_100g'].values())) else 'partial', 'method': 'exact_food_name_lookup', **record}
    if grams is not None:
        result['portion_g'] = grams
        result['portion_g_source'] = 'user_input'
        result['portion'] = {k: None if v is None else round(v * grams / 100, 4) for k, v in record['per_100g'].items()}
    return result

def predict(image_path, device='cpu', threshold=0.5, nutrition_path=None, grams=None):
    import numpy as np
    from PIL import Image, ImageOps
    from mmdet.apis import inference_detector
    database = read_nutrition(nutrition_path or ROOT / 'nutrition.json')
    # EXIF 방향을 적용한 뒤 RGB로 읽는다. 탐지 모델에는 OpenCV 방식의 BGR 배열을 전달한다.
    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source).convert('RGB')
    model = restore_model(device)
    boxes_by_class = inference_detector(model, np.asarray(image)[:, :, ::-1].copy())
    # 50% 미만도 후보로 보관한다. 확정 결과가 없을 때 음식명별 상위 3개를 출력한다.
    detections = []
    candidates = []
    for class_id, boxes in enumerate(boxes_by_class):
        for box in boxes:
            if float(box[4]) < threshold:
                candidates.append({'food': model.CLASSES[class_id], 'confidence': float(box[4])})
                continue
            food = model.CLASSES[class_id]
            detections.append({'food': food, 'class_id': class_id, 'confidence': float(box[4]), 'bbox_xyxy': [float(v) for v in box[:4]], 'nutrition': nutrition_for(food, database)})
    detections.sort(key=lambda item: item['confidence'], reverse=True)
    if grams is not None:
        if len(detections) != 1:
            raise ValueError('--grams는 탐지된 음식이 정확히 1개일 때만 사용할 수 있습니다. 여러 음식에는 각각의 중량이 필요합니다.')
        detections[0]['nutrition'] = nutrition_for(detections[0]['food'], database, grams)
    candidates.sort(key=lambda item: item['confidence'], reverse=True)
    return {'image': str(image_path), 'threshold': threshold, 'detections': detections, 'candidates': candidates, 'nutrition_method': 'food_name_lookup_not_image_regression', 'note': '영양소는 음식별 성분표를 연결한 참고값입니다. 사진만으로 실제 섭취량을 알 수 없습니다.'}

import json
import math
from pathlib import Path
ROOT = Path(__file__).resolve().parent
# 원본 라벨의 꼭짓점 순서. 각 목록은 상자의 한 면이다.
FACES = [[0, 1, 5, 4], [3, 2, 6, 7], [0, 1, 3, 2], [1, 3, 7, 5], [5, 7, 6, 4], [0, 4, 6, 2]]

def prepare_input(image_path, label_path):
    import cv2
    import numpy as np
    import torch
    label = (label_path if isinstance(label_path, dict) else json.loads(Path(label_path).read_text(encoding='utf-8-sig')))['data']
    info = label['image_info']
    if info.get('file_name') and Path(info['file_name']).name.casefold() != Path(image_path).name.casefold():
        raise ValueError('사진 이름과 JSON의 image_info.file_name이 다릅니다. 짝이 맞는 파일을 선택하세요.')
    image = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError('사진을 읽을 수 없습니다.')
    h, w = image.shape[:2]
    original_size = np.array([info['width'], info['height']], dtype=float)
    if not np.isfinite(original_size).all() or (original_size <= 0).any():
        raise ValueError('JSON의 이미지 크기가 올바르지 않습니다.')
    x = np.asarray(label['3d_annotation']['x'], dtype=float)
    y = np.asarray(label['3d_annotation']['y'], dtype=float)
    if x.shape != (8,) or y.shape != (8,) or (not np.isfinite(x).all()) or (not np.isfinite(y).all()):
        raise ValueError('3d_annotation에는 유한한 x, y 좌표가 각각 8개 필요합니다.')
    # x, y는 같은 꼭짓점의 픽셀 좌표다. 라벨의 사진 크기를 기준으로 현재 해상도에 맞춘다.
    cuboid = np.column_stack((x, y)).astype(int)
    cuboid = (cuboid * (np.array([w, h]) / original_size)).astype(np.int32)
    # 상자의 여섯 면을 255로 채우고 배경은 0으로 둔다. 이 영역이 RGB에 붙는 네 번째 채널이다.
    mask = np.zeros((h, w), dtype=np.uint8)
    for face in FACES:
        cv2.fillPoly(mask, [cuboid[face]], 255)
    if not mask.any():
        raise ValueError('cuboid 마스크가 비어 있습니다. 사진과 JSON 좌표를 확인하세요.')
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    # 학습 때와 동일하게 235로 리사이즈한 뒤 224 영역을 자른다.
    image = cv2.resize(image, (235, 235), interpolation=cv2.INTER_LINEAR)[5:229, 5:229]
    mask = cv2.resize(mask, (235, 235), interpolation=cv2.INTER_NEAREST)[5:229, 5:229]
    mean = np.asarray([0.485, 0.456, 0.406], dtype=np.float32) * 255
    inv_std = 1 / (np.asarray([0.229, 0.224, 0.225], dtype=np.float32) * 255)
    rgb = (image.astype(np.float32) - mean) * inv_std
    # 네 번째 채널은 마스크를 -0.5~0.5로 정규화한 값이다.
    extra = mask.astype(np.float32) / 255 - 0.5
    tensor = np.concatenate((rgb, extra[:, :, None]), axis=2).transpose(2, 0, 1)
    return (torch.from_numpy(tensor.copy()).unsqueeze(0), info)

def label_nutrition(label_path, grams):
    label = (label_path if isinstance(label_path, dict) else json.loads(Path(label_path).read_text(encoding='utf-8-sig')))['data']
    nutrition = label.get('nutrition', {})
    try:
        reference = float(nutrition.get('g', 0))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(reference) or reference <= 0:
        return None
    # nutrition.g는 영양소의 기준 중량이며 항상 100g인 것은 아니다. -99 등 음수는 결측값으로 처리한다.
    keys = {'e': 'energy_kcal', 'cal': 'carbohydrate_g', 'sug': 'sugar_g', 'fat': 'fat_g', 'pro': 'protein_g', 'na': 'sodium_mg', 'chol': 'cholesterol_mg', 'total_sfa': 'saturated_fat_g', 'total_tfa': 'trans_fat_g'}
    values = {}
    for source, target in keys.items():
        try:
            value = float(nutrition[source])
            values[target] = value if math.isfinite(value) and value >= 0 else None
        except (KeyError, ValueError, TypeError):
            values[target] = None
    return {'source': 'selected_label_json', 'reference_g': reference, 'at_reference': values, 'per_100g': {k: None if v is None else v * 100 / reference for k, v in values.items()}, 'estimated_portion': {k: None if v is None else v * grams / reference for k, v in values.items()}}

def restore_weight(device='cpu'):
    import torch
    from torchvision.models import resnet18
    checkpoint = torch.load(str(ROOT / 'food_weight_checkpoint.pth'), map_location='cpu', weights_only=False, pickle_module=RESTRICTED_PICKLE)
    if checkpoint.get('loss') != 'mse' or checkpoint.get('model') != 'ResNet18':
        raise ValueError('제공된 ResNet18/MSE 체크포인트가 아닙니다.')
    model = resnet18(weights=None)
    model.conv1 = torch.nn.Conv2d(4, 64, 7, stride=2, padding=3, bias=False)
    model.fc = torch.nn.Linear(512, 1)
    model.load_state_dict({k.removeprefix('model.'): v for k, v in checkpoint['state_dict'].items()}, strict=True)
    return model.to(device).eval()

def predict_weight(image_path, label_path, device='cpu', model=None):
    import torch
    # 라벨 파일과 자동 생성한 좌표 딕셔너리는 동일한 전처리를 거쳐 무게 모델에 들어간다.
    tensor, info = prepare_input(image_path, label_path)
    model = restore_weight(device) if model is None else model
    with torch.inference_mode():
        raw = float(model(tensor.to(device)).reshape(-1)[0].cpu())
    if not math.isfinite(raw):
        raise ValueError('모델이 유한하지 않은 값을 출력했습니다.')
    # 학습 시 사용한 중량 정규화 역변환: 출력 × 480 + 620(g).
    grams = max(1.0, raw * 480.0 + 620.0)
    result = {'predicted_g': grams, 'raw_output': raw, 'input': 'RGB + original cuboid mask', 'label': str(label_path)}
    # 실제 중량은 오차 계산에만 사용한다.
    actual = info.get('weight')
    if actual is not None:
        actual = float(actual)
        if math.isfinite(actual) and actual > 0:
            result.update(actual_g=actual, absolute_error_g=abs(grams - actual), relative_error_percent=abs(grams - actual) / actual * 100, absolute_log_difference=abs(math.log(actual) - math.log(grams)))
    result['nutrition'] = label_nutrition(label_path, grams)
    return result

import hashlib
import json
from pathlib import Path
import zipfile
ROOT = Path(__file__).resolve().parent

def find_label(image):
    image = Path(image).resolve()
    adjacent = image.with_suffix('.json')
    if adjacent.is_file():
        return adjacent
    for parent in image.parents:
        if parent.name in ('01.원천데이터', '01.원시데이터'):
            candidate = parent.parent / '02.라벨링데이터' / image.relative_to(parent).with_suffix('.json')
            if candidate.is_file():
                return candidate
    return None

def import_sample_zip(path):
    path = Path(path).resolve()
    stat = path.stat()
    token = hashlib.sha256(f'{path}|{stat.st_size}|{stat.st_mtime_ns}'.encode()).hexdigest()[:12]
    target = Path(os.environ.get('LOCALAPPDATA', str(ROOT))) / 'FoodPredict' / 'imported_data' / token
    marker = target / 'import_complete.json'
    if marker.is_file():
        return target
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            if member.is_dir() or Path(member.filename).suffix.lower() not in ('.jpg', '.jpeg', '.png', '.json'):
                continue
            destination = (target / member.filename).resolve()
            if not destination.is_relative_to(target.resolve()):
                raise ValueError(f'ZIP에 잘못된 경로가 있습니다: {member.filename}')
            if destination == target.resolve():
                raise ValueError('잘못된 ZIP 경로입니다.')
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, destination.open('wb') as output:
                import shutil
                shutil.copyfileobj(source, output)
            count += 1
    marker.write_text(json.dumps({'source': str(path), 'files': count}), encoding='utf-8')
    return target

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
ROOT = Path(__file__).resolve().parent
PACKAGES = ['numpy==1.23.5', 'pillow==9.5.0', 'opencv-python==4.8.1.78', 'yapf==0.40.1', 'setuptools==69.5.1', 'wheel', 'torch==1.13.1+cpu', 'torchvision==0.14.1+cpu']

def run(command, env=None):
    subprocess.run([str(x) for x in command], cwd=ROOT, env=env, check=True)

def ensure_environment():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if os.name != 'nt':
        raise RuntimeError('이 자동 설치 프로그램은 Windows용입니다.')
    for filename in ('food_detector.pth', 'food_weight_checkpoint.pth'):
        if not (ROOT / filename).is_file():
            raise FileNotFoundError(f'전체 ZIP을 풀어주세요. 모델 파일이 없습니다: {filename}')
    venv = ROOT / '.venv'
    python = venv / 'Scripts/python.exe'
    marker = venv / 'food_environment.json'
    # 폴더가 이동해도 환경이 정상 작동하면 재사용한다. 실행에 실패한 경우에만 다시 준비한다.
    if python.is_file():
        try:
            subprocess.run([str(python), '-c', 'import sys; assert sys.version_info[:2] == (3,10); import torch, torchvision, cv2, mmcv, mmdet, tkinter; from mmcv.ops import nms'], cwd=ROOT, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return python
        except (OSError, subprocess.CalledProcessError):
            pass
    print('최초 실행 또는 폴더 이동을 감지했습니다. 실행 환경을 자동 준비합니다.', flush=True)
    print('인터넷 다운로드가 필요하며 처음에는 시간이 걸립니다.', flush=True)
    cache = Path(os.environ.get('LOCALAPPDATA', str(ROOT))) / 'FoodPredict'
    tools = cache / 'tools'
    tools.mkdir(parents=True, exist_ok=True)
    uv = shutil.which('uv') or str(tools / 'uv.exe')
    if not Path(uv).is_file():
        archive = tools / 'uv.zip'
        urllib.request.urlretrieve('https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip', archive)
        with zipfile.ZipFile(archive) as z:
            member = next((n for n in z.namelist() if Path(n).name == 'uv.exe'))
            (tools / 'uv.exe').write_bytes(z.read(member))
        archive.unlink()
        uv = str(tools / 'uv.exe')
    env = os.environ.copy()
    env.update(UV_CACHE_DIR=str(cache / 'uv-cache'), UV_PYTHON_INSTALL_DIR=str(cache / 'python-runtime'), UV_PYTHON_BIN_DIR=str(cache / 'python-bin'), PYTHONDONTWRITEBYTECODE='1')
    if venv.exists():
        
        if venv.resolve().parent != ROOT.resolve():
            raise RuntimeError('Unexpected environment path')
        previous = cache / 'previous_environments'
        previous.mkdir(parents=True, exist_ok=True)
        shutil.move(str(venv), str(previous / f'venv-{time.time_ns()}'))
    run([uv, 'venv', '--python', '3.10', '--seed', venv], env)
    run([python, '-m', 'pip', 'install', *PACKAGES, '--extra-index-url', 'https://download.pytorch.org/whl/cpu'], env)
    run([python, '-m', 'pip', 'install', '--only-binary=mmcv-full', 'mmcv-full==1.7.0', '-f', 'https://download.openmmlab.com/mmcv/dist/cpu/torch1.13.0/index.html'], env)
    run([python, '-m', 'pip', 'install', '--no-build-isolation', 'numpy==1.23.5', 'mmdet==2.26.0'], env)
    run([python, '-c', 'import torch, torchvision, cv2, mmcv, mmdet, tkinter; from mmcv.ops import nms'], env)
    marker.write_text(json.dumps({'folder': str(ROOT), 'version': 1}), encoding='utf-8')
    return python

import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent
NUTRIENT_LABELS = {'energy_kcal': ('에너지', 'kcal'), 'carbohydrate_g': ('탄수화물', 'g'), 'protein_g': ('단백질', 'g'), 'fat_g': ('지방', 'g'), 'sugar_g': ('당류', 'g'), 'fiber_g': ('식이섬유', 'g'), 'sodium_mg': ('나트륨', 'mg'), 'cholesterol_mg': ('콜레스테롤', 'mg'), 'saturated_fat_g': ('포화지방', 'g'), 'trans_fat_g': ('트랜스지방', 'g')}

def print_nutrients(values, title):
    print(f'  {title}')
    for key, (name, unit) in NUTRIENT_LABELS.items():
        if key not in values:
            continue
        value = values[key]
        text = '데이터 없음' if value is None else f'{value:.2f} {unit}'
        print(f'    {name}: {text}')

def select_files():
    import tkinter as tk
    from tkinter import filedialog
    window = tk.Tk()
    window.withdraw()
    try:
        image = filedialog.askopenfilename(title='음식 사진 또는 Sample.zip 선택', initialdir=str(ROOT / 'samples') if (ROOT / 'samples').is_dir() else str(ROOT), filetypes=[('사진 또는 샘플 ZIP', '*.jpg *.jpeg *.png *.bmp *.zip'), ('모든 파일', '*.*')])
        if not image:
            return (None, None)
        if Path(image).suffix.lower() == '.zip':
            print('샘플 ZIP의 사진과 JSON을 가져오는 중...', flush=True)
            folder = import_sample_zip(image)
            source_folder = folder / 'Sample' / '01.원천데이터'
            image = filedialog.askopenfilename(title='가져온 Sample 폴더에서 사진 선택', initialdir=str(source_folder if source_folder.is_dir() else folder), filetypes=[('사진', '*.jpg *.jpeg *.png *.bmp')])
            if not image:
                return (None, None)
        automatic = find_label(image)
        if automatic:
            print(f'대응 JSON 자동 연결: {automatic}', flush=True)
            return (Path(image), automatic)
        return (Path(image), None)
    finally:
        window.destroy()

def automatic_image():
    for name in ('food.jpg', 'food.png'):
        path = ROOT / name
        if path.is_file():
            return path
    raise FileNotFoundError('main.py와 같은 폴더에 food.jpg 또는 food.png를 넣어주세요. 둘 다 있으면 food.jpg를 사용합니다.')

def automatic_cuboid(image):
    import cv2
    import numpy as np
    import torch
    from torchvision.models import resnet18
    # 좌표 모델은 무게를 직접 출력하지 않는다. x/너비, y/높이로 정규화된 좌표 16개를 출력한다.
    checkpoint = torch.load(str(ROOT/'cuboid_model.pth'), map_location='cpu', weights_only=False, pickle_module=RESTRICTED_PICKLE)
    if checkpoint.get('architecture') != 'resnet18_cuboid_v1' or checkpoint.get('input') != 'opencv_oriented_RGB_resize224_imagenet':
        raise ValueError('지원하지 않는 좌표 모델 형식입니다.')
    if checkpoint.get('smoke_test'):
        raise ValueError('실행 점검용 모델은 실사용할 수 없습니다. 정식 학습을 완료하세요.')
    model = resnet18(weights=None)
    model.fc = torch.nn.Linear(512,16)
    model.load_state_dict(checkpoint['state_dict'],strict=True); model.eval()
    rgb = cv2.imdecode(np.fromfile(image,dtype=np.uint8),cv2.IMREAD_COLOR)
    if rgb is None: raise ValueError('사진을 읽지 못했습니다.')
    h,w = rgb.shape[:2]
    rgb = cv2.cvtColor(rgb,cv2.COLOR_BGR2RGB)
    # train_cuboid.py와 같은 전처리를 유지한다.
    a = cv2.resize(rgb,(224,224),interpolation=cv2.INTER_LINEAR).astype(np.float32)/255
    a = (a-np.array([.485,.456,.406],dtype=np.float32))/np.array([.229,.224,.225],dtype=np.float32)
    with torch.inference_mode():
        points = model(torch.from_numpy(a.transpose(2,0,1).copy()).unsqueeze(0)).numpy().reshape(8,2)
    if not np.isfinite(points).all() or np.max(np.abs(points))>=10:
        raise ValueError('예측한 상자 좌표가 비정상입니다.')
    # 8쌍의 상대 좌표를 픽셀 좌표로 바꾸어 원본 라벨과 같은 구조로 전달한다.
    return {'data':{'image_info':{'file_name':image.name,'width':w,'height':h},'3d_annotation':{'x':(points[:,0]*w).tolist(),'y':(points[:,1]*h).tolist()}}}

def print_portion(output, grams, source):
    items = output.get('detections', [])
    if len(items) != 1:
        print('  중량별 탄단지 환산에는 확정된 음식 1개가 필요합니다. 여러 음식에 전체 중량을 나누어 적용하지 않습니다.')
        return
    item = items[0]
    values = item.get('nutrition', {}).get('per_100g')
    if not values or not any(v is not None for v in values.values()):
        print('  해당 음식의 영양정보가 없습니다.')
        return
    portion = {k: None if v is None else v * grams / 100 for k, v in values.items()}
    output['portion_nutrition'] = {'food': item['food'], 'grams': grams, 'weight_source': source, 'values': portion}
    print_nutrients(portion, f"{item['food']} / {source} {grams:.1f}g 기준 영양정보")

def app_main():
    import warnings
    # 결과와 무관한 라이브러리 안내 두 개만 숨긴다. 다른 경고와 오류는 그대로 표시한다.
    warnings.filterwarnings('ignore', message='On January 1, 2023, MMCV.*', category=UserWarning)
    warnings.filterwarnings('ignore', message='"ImageToTensor" pipeline is replaced.*', category=UserWarning)
    parser = argparse.ArgumentParser()
    parser.add_argument('image', nargs='?', type=Path)
    parser.add_argument('--json', type=Path)
    parser.add_argument('--weight-only', action='store_true')
    parser.add_argument('--grams', type=float)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.grams is not None and (not math.isfinite(args.grams) or args.grams <= 0):
        raise ValueError('중량은 0보다 큰 유한한 숫자여야 합니다.')
    image = args.image or automatic_image()
    if not image.is_file(): raise FileNotFoundError(image)
    output = {'image': str(image.resolve())}
    detection = predict(image) if not args.weight_only else {'detections': []}
    output['detections'] = detection['detections']
    items = output['detections']
    if not items and not args.weight_only:
        candidates = []
        seen = set()
        for item in sorted(detection.get('candidates', []), key=lambda x: x['confidence'], reverse=True):
            if item['food'] not in seen:
                candidates.append(item); seen.add(item['food'])
            if len(candidates) == 3: break
        output['candidates'] = candidates
        print('음식 탐지 결과')
        for item in candidates:
            print(f"  {item['food']} | 신뢰도 {item['confidence']:.2%}")
        if not candidates: print('  탐지된 음식이 없습니다.')
    else:
        values = None
        error_message = None
        grams = args.grams
        if len(items) == 1 or args.weight_only:
            try:
                label = args.json or find_label(image)
                # 중량을 직접 지정하지 않았다면 대응 라벨을 우선 사용하고, 없으면 좌표 모델로 생성한다.
                if grams is None:
                    if not label and (ROOT/'cuboid_model.pth').is_file() and not args.weight_only:
                        label = automatic_cuboid(image)
                        output['cuboid_source'] = 'predicted_by_experimental_model'
                    if not label:
                        raise ValueError('중량 모델용 좌표가 없습니다. cuboid_model.pth 또는 대응 라벨이 필요합니다.')
                    weight = predict_weight(image, label)
                    output['weight'] = weight
                    grams = weight['predicted_g']
                    if weight.get('nutrition'):
                        values = weight['nutrition']['estimated_portion']
                # 라벨에 영양정보가 없으면 탐지된 음식의 100g 성분표를 사용한다. 각 성분에 중량/100을 곱한다.
                if values is None and items:
                    per100 = items[0].get('nutrition', {}).get('per_100g', {})
                    values = {k: None if v is None else v*grams/100 for k,v in per100.items()}
                output['portion_nutrition'] = {'grams':grams, 'weight_source':'user_input' if args.grams is not None else 'model_prediction', 'values':values}
            # 입력값·파일 오류만 화면에 안내한다. 모델 실행 오류는 원래 예외를 유지해 원인을 확인한다.
            except (ValueError, OSError) as error:
                error_message = str(error)
                output['weight_error'] = error_message
        else:
            # 전체 사진에서 얻은 하나의 중량을 여러 음식에 각각 적용하면 영양소가 중복 계산된다.
            error_message = '여러 음식의 개별 중량을 알 수 없어 영양소를 환산할 수 없습니다.'
        if args.weight_only:
            if error_message: print(f'무게 추정 실패: {error_message}')
            else: print(f'추정 중량: {grams:.1f} g')
        else:
            print('음식 탐지 결과')
            for item in items:
                print(f"  {item['food']} | 신뢰도 {item['confidence']:.2%}")
                if error_message:
                    print(f'    영양소 계산 불가: {error_message}')
                    continue
                # 화면에는 에너지와 탄단지만 표시한다. 추정 중량과 상세 결과는 --output JSON에 남는다.
                for key in ('energy_kcal','carbohydrate_g','protein_g','fat_g'):
                    name, unit = NUTRIENT_LABELS[key]
                    value = (values or {}).get(key)
                    formatted = '데이터 없음' if value is None else f'{value:.2f} {unit}'
                    print(f'    {name}: {formatted}')
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    try:
        if '--internal-worker' in sys.argv:
            sys.argv.remove('--internal-worker')
            app_main()
        else:
            python = ensure_environment()
            env = os.environ.copy()
            env['PYTHONDONTWRITEBYTECODE'] = '1'
            run([python, Path(__file__).resolve(), '--internal-worker', *sys.argv[1:]], env)
    except KeyboardInterrupt:
        print('실행을 중단했습니다.', flush=True)
