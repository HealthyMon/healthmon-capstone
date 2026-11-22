"""Run the downloaded FPB fork in its separate modern PyTorch environment."""
import argparse
import json
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--image', type=Path, required=True)
    p.add_argument('--regions', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--device', default='cuda:0')
    a = p.parse_args()
    if not a.model.is_file() or a.model.stat().st_size < 1024:
        raise FileNotFoundError(a.model)
    os.environ.setdefault('YOLO_CONFIG_DIR', str(BASE/'.yolo'))
    os.environ.setdefault('MPLCONFIGDIR', str(BASE/'.matplotlib'))
    os.environ['YOLO_AUTOINSTALL'] = 'false'
    sys.path.insert(0,str(BASE))
    sys.path.insert(0,str(a.repo.resolve()))
    import ultralytics
    if not Path(ultralytics.__file__).resolve().is_relative_to(a.repo.resolve()):
        raise RuntimeError('Wrong ultralytics package; requires downloaded FPB fork')
    import torch
    torch.set_num_threads(4)
    from food_ai import load_model
    from PIL import Image
    import numpy as np
    model = load_model(a.model).model.to(a.device).float().eval()
    regions = json.loads(a.regions.read_text(encoding='utf-8'))
    payload = {'foods': [], 'method': 'per_crop_raw_weight_regression'}
    with Image.open(a.image) as source:
        image = source.convert('RGB')
    for region in regions:
        crop = image.crop(region['crop_xyxy'])
        scale = min(640/crop.width,640/crop.height)
        w,h = max(1,round(crop.width*scale)), max(1,round(crop.height*scale))
        left,top = (640-w)//2,(640-h)//2
        canvas = Image.new('RGB',(640,640),(114,114,114))
        canvas.paste(crop.resize((w,h),Image.Resampling.BILINEAR),(left,top))
        x = torch.from_numpy(np.asarray(canvas).copy()).permute(2,0,1).unsqueeze(0).to(a.device).float()/255
        with torch.inference_mode():
            raw = model(x)
            raw = raw[0] if isinstance(raw,(tuple,list)) else raw
            # FPB decoded head: [cx,cy,w,h,mass_g,class probabilities...].
            if raw.ndim != 3 or raw.shape[1] != len(model.names)+5:
                raise RuntimeError('Unsupported FPB regression output layout')
            proposals = raw[0].transpose(0,1)
            from crop_weight_selection import select_weight
            selected = select_weight(proposals.detach().cpu().numpy(), [left,top,left+w,top+h])
        selected.update(id=region['id'], crop_xyxy=region['crop_xyxy'])
        selected['fpb_name'] = model.names[selected['fpb_class_id']]
        payload['foods'].append(selected)
    payload['model'] = str(a.model.resolve())
    payload['implementation'] = str(Path(ultralytics.__file__).resolve())
    a.output.write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False),encoding='utf-8')


if __name__ == '__main__':
    main()
