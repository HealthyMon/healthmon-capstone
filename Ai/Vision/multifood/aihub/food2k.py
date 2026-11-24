"""NoisyViT-B/16 checkpoint adapter and user-supplied nutrition lookup.

Official inference math: https://github.com/Tonmoy-Ghosh/NoisyViT_Food
Use independent single-crop inference: OptimalQ is identity at batch size 1.
Torchvision ViT supplies the equivalent inference layers; no remote code executes.
"""
import csv
import math
from pathlib import Path
import torch
from torchvision.models.vision_transformer import VisionTransformer
from torchvision import transforms
from detect import checkpoint, ROOT

ASSETS = ROOT.parent
DEFAULT_CSV = ASSETS / 'nutrition.csv'
DEFAULT_MODEL = ASSETS / 'models/classifier.pkl'


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError):
        return None


class FoodTable:
    def __init__(self, path=DEFAULT_CSV, order='auto'):
        self.source = str(Path(path).resolve())
        with Path(path).open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        self.rows = {}
        explicit = 'noisyvit_prediction_index' in rows[0] if rows else False
        output_ids = {}
        for row in rows:
            if explicit:
                row = dict(row, Index=row['food2k_class_id'], Category=row['food_name_en'])
                output_id = int(row['noisyvit_prediction_index'])
                if output_id in output_ids:
                    raise ValueError('Duplicate model output index in CSV')
                output_ids[output_id] = int(row['Index'])
            key = int(row['Index'])
            if key in self.rows or not row['Category'].strip():
                raise ValueError('Duplicate index or empty food name in CSV')
            self.rows[key] = row
        if set(self.rows) != set(range(2000)):
            raise ValueError('Expected exactly Food2K indices 0..1999')
        # Official README uses unpadded class directory names; ImageFolder sorts strings.
        # A checkpoint state_dict does not itself contain the training class_to_idx.
        if explicit:
            if order not in ('auto','csv'):
                raise ValueError('This CSV includes explicit output indices; use class order auto or csv')
            if set(output_ids) != set(range(2000)):
                raise ValueError('CSV output indices must cover 0..1999')
            self.ids = [output_ids[i] for i in range(2000)]
            order = 'csv'
        elif order in ('auto','imagefolder'):
            self.ids = sorted(self.rows, key=lambda key: str(key))
            order = 'imagefolder'
        elif order == 'numeric':
            self.ids = sorted(self.rows)
        else:
            raise ValueError('Unknown class order')
        self.order = order

    def candidate(self, logit_index, score):
        food_id = self.ids[logit_index]
        return {'class_id': food_id, 'model_output_index': logit_index,
                'name': self.rows[food_id]['Category'], 'confidence': float(score)}

    def nutrition(self, food_id):
        row = self.rows[food_id]
        values = {key: number(value) for key, value in row.items() if key.endswith('_100g')}
        if 'estimated_energy_kcal_100g' in values:
            values['energy_kcal_100g'] = values.pop('estimated_energy_kcal_100g')
        return {'basis_g': 100, 'type': 'csv_usda_reference_not_measured',
                'per_100g': values, 'portion': None,
                'review_required': row.get('review_required', '').lower() != 'false',
                'matched_food_name': row.get('reference_food_name', row.get('usda_food_name')),
                'matched_food_id': row.get('reference_ndb_no', row.get('usda_ndb_no')),
                'match_method': row.get('matching_method', row.get('match_method')),
                'match_score': number(row.get('match_score')),
                'reference_confidence': row.get('confidence'),
                'data_type': row.get('data_type'),
                'estimation_note': row.get('estimation_note'),
                'source_url': row.get('source_url'),
                'source': self.source}


def convert_state(source):
    """Map timm-style names to torchvision; consume every source tensor exactly once."""
    mapping = {'cls_token': 'class_token', 'pos_embed': 'encoder.pos_embedding',
               'patch_embed.proj.weight': 'conv_proj.weight', 'patch_embed.proj.bias': 'conv_proj.bias',
               'norm.weight': 'encoder.ln.weight', 'norm.bias': 'encoder.ln.bias',
               'head.weight': 'heads.head.weight', 'head.bias': 'heads.head.bias'}
    for i in range(12):
        for old, new in [('norm1', 'ln_1'), ('norm2', 'ln_2'),
                         ('attn.proj', 'self_attention.out_proj'),
                         ('mlp.fc1', 'mlp.0'), ('mlp.fc2', 'mlp.3')]:
            for suffix in ('weight', 'bias'):
                mapping[f'blocks.{i}.{old}.{suffix}'] = f'encoder.layers.encoder_layer_{i}.{new}.{suffix}'
        for suffix in ('weight', 'bias'):
            mapping[f'blocks.{i}.attn.qkv.{suffix}'] = f'encoder.layers.encoder_layer_{i}.self_attention.in_proj_{suffix}'
    if set(source) != set(mapping):
        raise ValueError(f'Unsupported checkpoint keys: {set(source) ^ set(mapping)}')
    return {mapping[key]: value for key, value in source.items()}


class FoodClassifier:
    def __init__(self, model_path=DEFAULT_MODEL, csv_path=DEFAULT_CSV, device='cuda:0', order='auto'):
        self.table = FoodTable(csv_path, order)
        self.csv_path = str(Path(csv_path).resolve())
        self.model_path = str(Path(model_path).resolve())
        self.device = device
        self.model = VisionTransformer(image_size=384, patch_size=16, num_layers=12,
                                       num_heads=12, hidden_dim=768, mlp_dim=3072,
                                       num_classes=2000)
        self.model.load_state_dict(convert_state(checkpoint(model_path)), strict=True)
        self.model.to(device).eval()
        # Actual official get_test_loader uses ImageNet normalization, not unused
        # transform_test in Inference.py. Preserve the complete crop (no center crop).
        self.transform = transforms.Compose([
            transforms.Resize((384, 384)), transforms.ToTensor(),
            transforms.Normalize([.485, .456, .406], [.229, .224, .225])])

    @torch.inference_mode()
    def classify(self, crop):
        scores = self.model(self.transform(crop.convert('RGB')).unsqueeze(0).to(self.device)).softmax(-1)[0]
        values, indices = scores.topk(5)
        return [self.table.candidate(int(i), float(v)) for i, v in zip(indices, values)]


def add_portions(payload):
    """Scale only when the existing weight pipeline actually supplies a mass."""
    for food in payload['foods']:
        nutrition = food.get('nutrition')
        if nutrition:
            nutrition['portion'] = None
        mass = number(food.get('weight_g'))
        if nutrition and mass is not None and mass > 0:
            nutrition['portion'] = {
                'weight_g': mass, 'type': 'estimated_from_weight_and_csv',
                'values': {key.removesuffix('_100g'): None if value is None else value * mass / 100
                           for key, value in nutrition['per_100g'].items()}}


def predict_food2k(classifier, locator, path, region_threshold=.5, name_threshold=.5):
    from PIL import Image, ImageOps
    from region_model import locate
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert('RGB')
    foods = []
    for proposal in locate(locator, image, region_threshold):
        box = proposal['bbox_xyxy']
        crop_box = [max(0, math.floor(box[0])), max(0, math.floor(box[1])),
                    min(image.width, math.ceil(box[2])), min(image.height, math.ceil(box[3]))]
        if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
            continue
        candidates = classifier.classify(image.crop(crop_box))
        best = candidates[0]
        food = dict(best, id=len(foods), name_confidence=best['confidence'],
                    confidence=proposal['confidence'], localization_confidence=proposal['confidence'],
                    name_status='predicted_closed_set' if best['confidence'] >= name_threshold else 'low_confidence_candidate',
                    candidates=candidates, bbox_xyxy=box, classification_crop_xyxy=crop_box,
                    bbox_normalized_xyxy=[box[0]/image.width, box[1]/image.height, box[2]/image.width, box[3]/image.height],
                    weight_g=None, weight_status='requires_existing_cuboid_pipeline',
                    nutrition=classifier.table.nutrition(best['class_id']))
        food['nutrition']['conditional_on_predicted_class'] = True
        foods.append(food)
    return {'schema_version': 3, 'image_size': {'width': image.width, 'height': image.height},
            'coordinate_system': 'exif_corrected_image_pixels_xyxy', 'region_type': 'food_not_plate',
            'pipeline': 'dishseg_locator_then_noisyvit_food2k',
            'classifier': {'checkpoint': classifier.model_path, 'nutrition_csv': classifier.csv_path,
                           'class_order': classifier.table.order,
                           'class_order_status': {'imagefolder':'assumed_official_imagefolder_convention',
                                                  'csv':'explicit_user_csv_mapping',
                                                  'numeric':'user_selected_numeric'}[classifier.table.order],
                           'score_type': 'uncalibrated_softmax', 'input_size': 384,
                           'normalization': 'imagenet', 'inference_batch_size': 1},
            'foods': foods}, image
