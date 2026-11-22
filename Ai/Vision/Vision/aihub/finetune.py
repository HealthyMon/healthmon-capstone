"""Fine-tune Faster R-CNN/Swin on prepared multi-food COCO data."""
import argparse
import json
from pathlib import Path
from detect import ROOT, DEFAULT_WEIGHT, checkpoint

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,required=True)
    p.add_argument('--model',type=Path,default=DEFAULT_WEIGHT)
    p.add_argument('--epochs',type=int,default=12)
    p.add_argument('--batch',type=int,default=1)
    p.add_argument('--lr',type=float,default=.0001)
    p.add_argument('--short-side',type=int,default=640)
    p.add_argument('--work-dir',type=Path,required=True)
    p.add_argument('--check-only',action='store_true')
    a=p.parse_args()
    from mmcv import Config
    from mmdet.models import build_detector
    from mmdet.datasets import build_dataset
    from mmdet.apis import train_detector,set_random_seed
    if a.work_dir.exists():
        p.error('Use a new work directory to preserve prior runs')
    if min(a.epochs,a.batch,a.short_side)<=0 or a.lr<=0:
        p.error('Training parameters must be positive')
    classes=tuple(json.loads((a.data/'classes.json').read_text(encoding='utf-8')))
    old=checkpoint(a.model)
    old_classes=tuple(old['meta']['CLASSES'])
    if classes[:len(old_classes)]!=old_classes:
        p.error('Prepared class ordering must preserve checkpoint class IDs')
    cfg=Config.fromfile(str(ROOT/'detector_config.py'))
    cfg.model.init_cfg=None
    cfg.model.backbone.init_cfg=None
    cfg.model.backbone.pretrained=None
    cfg.model.roi_head.bbox_head.num_classes=len(classes)
    cfg.model.backbone.with_cp=True
    cfg.model.backbone.frozen_stages=1
    cfg.data=dict(samples_per_gpu=a.batch,workers_per_gpu=0)
    for split in ('train','val'):
        pipeline=cfg.train_pipeline if split=='train' else cfg.test_pipeline
        for transform in pipeline:
            if transform['type'] in ('Resize','MultiScaleFlipAug'):
                transform['img_scale']=(1333,a.short_side)
        cfg.data[split]=dict(type='CocoDataset',ann_file=(a.data/f'{split}.json').resolve().as_posix(),
                            img_prefix=(a.data/split).resolve().as_posix()+'/',classes=classes,
                            pipeline=pipeline,filter_empty_gt=False)
    cfg.data.test=cfg.data.val.copy()
    cfg.optimizer=dict(type='AdamW',lr=a.lr,weight_decay=.05)
    cfg.optimizer_config=dict(grad_clip=dict(max_norm=10,norm_type=2))
    cfg.lr_config=dict(policy='step',warmup='linear',warmup_iters=50,warmup_ratio=.1,
                       step=sorted(set([max(1,a.epochs*2//3)])))
    cfg.runner=dict(type='EpochBasedRunner',max_epochs=a.epochs)
    cfg.workflow=[('train',1)]
    cfg.evaluation=dict(interval=1,metric='bbox',save_best='bbox_mAP',rule='greater')
    cfg.checkpoint_config=dict(interval=1,max_keep_ckpts=2,create_symlink=False)
    cfg.log_config=dict(interval=10,hooks=[dict(type='TextLoggerHook')])
    cfg.work_dir=a.work_dir.resolve().as_posix()
    cfg.load_from=None
    cfg.resume_from=None
    cfg.gpu_ids=[0]
    cfg.seed=42
    cfg.device='cuda'
    cfg.mp_start_method='spawn'
    set_random_seed(42,deterministic=True)
    dataset=build_dataset(cfg.data.train)
    validation=build_dataset(cfg.data.val)
    if not len(dataset) or not len(validation):
        p.error('Empty train/validation dataset')
    model=build_detector(cfg.model)
    model.init_weights()
    state=old['state_dict']
    # Preserve pretrained existing categories when appending new ones; leave new rows initialized.
    if len(classes)!=len(old_classes):
        current=model.state_dict()
        prefix='roi_head.bbox_head.'
        for name in ('fc_cls.weight','fc_cls.bias'):
            key=prefix+name
            current[key][:len(old_classes)]=state[key][:-1]
            current[key][-1]=state[key][-1]
            state[key]=current[key]
        for name in ('fc_reg.weight','fc_reg.bias'):
            key=prefix+name
            current[key][:len(old_classes)*4]=state[key]
            state[key]=current[key]
    model.load_state_dict(state,strict=True)
    model.CLASSES=classes
    a.work_dir.mkdir(parents=True)
    cfg.dump(str(a.work_dir/'config.py'))
    if a.check_only:
        print(f'Checked: {len(dataset)} train, {len(validation)} val, {len(classes)} classes; no training performed')
        return
    cfg.checkpoint_config.meta=dict(CLASSES=classes,config=cfg.pretty_text)
    # Evaluation is an explicit final step, not repeated at each epoch.
    train_detector(model,dataset,cfg,distributed=False,validate=False,meta={'CLASSES':classes})

if __name__=='__main__':
    main()
