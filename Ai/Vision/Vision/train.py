"""Fine-tune official FPB checkpoint; retain all six annotation columns."""
import argparse
from pathlib import Path
from food_ai import ROOT, DEFAULT_MODEL, load_model
from validate_data import validate

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--data', type=Path, default=ROOT / 'data_full.yaml')
    p.add_argument('--model', type=Path, default=DEFAULT_MODEL)
    p.add_argument('--epochs', type=int, default=50)
    p.add_argument('--batch', type=int, default=4)
    p.add_argument('--imgsz', type=int, default=640)
    p.add_argument('--device', default='0')
    p.add_argument('--name', default='food_finetune')
    args = p.parse_args()
    if not args.data.is_file():
        p.error('Run download.py --full, or supply --data data_sample.yaml for smoke testing')
    print(validate(args.data))
    model = load_model(args.model)
    model.train(data=str(args.data.resolve()), epochs=args.epochs, batch=args.batch, imgsz=args.imgsz,
                device=args.device, workers=0, seed=42, deterministic=True,
                project=str(ROOT / 'runs'), name=args.name, pretrained=True,
                amp=False, plots=False, cache=False, mosaic=0.0, mixup=0.0,
                degrees=0., translate=0., scale=0., shear=0., perspective=0.)

if __name__ == '__main__':
    main()
