import math
import json
from pathlib import Path
from detect import SAFE_PICKLE as RESTRICTED_PICKLE
ROOT = Path(__file__).resolve().parent.parent / '02.중량 예측 모델'
FACES = [[0,1,5,4],[3,2,6,7],[0,1,3,2],[1,3,7,5],[5,7,6,4],[0,4,6,2]]
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