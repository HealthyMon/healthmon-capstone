"""Class-agnostic locator. Food naming remains in the unchanged AI Hub model."""
import os
from pathlib import Path
import torch
from torchvision.models.detection import fasterrcnn_mobilenet_v3_large_320_fpn
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
from torchvision.models.detection import FasterRCNN_MobileNet_V3_Large_320_FPN_Weights
from torchvision.transforms.functional import to_tensor
from detect import ROOT,checkpoint

os.environ.setdefault('TORCH_HOME',str(ROOT.parent/'assets/torch'))
ARCHITECTURE='fasterrcnn_mobilenet_v3_large_320_fpn_food_regions_v1'

def build(pretrained=False):
    model=fasterrcnn_mobilenet_v3_large_320_fpn(
        weights=FasterRCNN_MobileNet_V3_Large_320_FPN_Weights.DEFAULT if pretrained else None,
        weights_backbone=None)
    model.roi_heads.box_predictor=FastRCNNPredictor(model.roi_heads.box_predictor.cls_score.in_features,2)
    return model

def load(path,device='cuda:0'):
    ckpt=checkpoint(path)
    if ckpt.get('architecture')!=ARCHITECTURE:
        raise ValueError('Wrong food locator architecture')
    model=build()
    model.transform.min_size=(int(ckpt.get('min_size',320)),)
    model.transform.max_size=int(ckpt.get('max_size',640))
    model.load_state_dict(ckpt['state_dict'],strict=True)
    return model.to(device).eval()

@torch.inference_mode()
def locate(model,image,threshold=.5):
    device=next(model.parameters()).device
    result=model([to_tensor(image).to(device)])[0]
    return [{'bbox_xyxy':box.tolist(),'confidence':float(score)}
            for box,score in zip(result['boxes'].cpu(),result['scores'].cpu()) if score>=threshold]
