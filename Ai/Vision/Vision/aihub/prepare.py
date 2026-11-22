"""Normalize COCO labels to checkpoint classes; optional train-only multi-food grids."""
import argparse
import hashlib
import json
import math
import random
import shutil
from pathlib import Path
from PIL import Image, ImageOps
from detect import ROOT, DEFAULT_WEIGHT, checkpoint

def read_split(annotation, images, classes):
    data=json.loads(Path(annotation).read_text(encoding='utf-8-sig'))
    categories={x['id']:x['name'] for x in data['categories']}
    if len(categories)!=len(data['categories']):
        raise ValueError('Duplicate category IDs')
    unknown=set(categories.values())-set(classes)
    if unknown:
        raise ValueError(f'Unknown class names: {sorted(unknown)}. Use --allow-new-classes deliberately.')
    records={}
    for item in data['images']:
        if item['id'] in records:
            raise ValueError('Duplicate image ID')
        path=(Path(images)/item['file_name']).resolve()
        if not path.is_relative_to(Path(images).resolve()):
            raise ValueError('Image path escapes image directory')
        with Image.open(path) as im:
            if im.getexif().get(274,1)!=1:
                raise ValueError(f'Normalize EXIF and labels before training: {path}')
            if im.size!=(item['width'],item['height']):
                raise ValueError(f'Image size mismatch: {path}')
        records[item['id']]={'path':path,'width':item['width'],'height':item['height'],
                             'hash':hashlib.sha256(path.read_bytes()).hexdigest(),'objects':[],
                             'group_id':str(item.get('group_id',item['file_name']))}
    seen=set()
    for a in data['annotations']:
        if a['id'] in seen:
            raise ValueError('Duplicate annotation ID')
        seen.add(a['id'])
        r=records[a['image_id']]
        x,y,w,h=map(float,a['bbox'])
        if not all(math.isfinite(v) for v in (x,y,w,h)) or min(x,y)<0 or min(w,h)<=0 or x+w>r['width']+.01 or y+h>r['height']+.01:
            raise ValueError(f'Invalid bbox: {a}')
        r['objects'].append({'category_id':classes.index(categories[a['category_id']])+1,
                             'bbox':[x,y,w,h],'iscrowd':int(a.get('iscrowd',0))})
    return list(records.values())

def write_split(records, output, split, classes, grids=0, seed=42):
    directory=output/split
    directory.mkdir(parents=True,exist_ok=True)
    data={'images':[],'annotations':[],'categories':[{'id':i+1,'name':n} for i,n in enumerate(classes)]}
    def add(name,width,height,objects,group):
        iid=len(data['images'])+1
        data['images'].append({'id':iid,'file_name':name,'width':width,'height':height,'group_id':group})
        for obj in objects:
            data['annotations'].append(dict(obj,id=len(data['annotations'])+1,image_id=iid,
                                            area=obj['bbox'][2]*obj['bbox'][3]))
    for index,r in enumerate(records):
        name=f'{index:06d}{r["path"].suffix.lower()}'
        shutil.copyfile(r['path'],directory/name)
        add(name,r['width'],r['height'],r['objects'],r['group_id'])
    rng=random.Random(seed)
    eligible=[r for r in records if r['objects'] and not any(x['iscrowd'] for x in r['objects'])]
    if grids and len(eligible)<4:
        raise ValueError('At least four labeled training images are required for grids')
    for i in range(grids):
        canvas=Image.new('RGB',(1024,1024),(114,114,114))
        objects=[]
        chosen=rng.sample(eligible,4)
        for j,r in enumerate(chosen):
            with Image.open(r['path']) as src:
                img=src.convert('RGB')
            img.thumbnail((488,488),Image.Resampling.LANCZOS)
            ox=(j%2)*512+(512-img.width)//2
            oy=(j//2)*512+(512-img.height)//2
            canvas.paste(img,(ox,oy))
            sx,sy=img.width/r['width'],img.height/r['height']
            for obj in r['objects']:
                x,y,w,h=obj['bbox']
                objects.append(dict(obj,bbox=[ox+x*sx,oy+y*sy,w*sx,h*sy]))
        name=f'grid_{i:06d}.jpg'
        canvas.save(directory/name)
        add(name,1024,1024,objects,'synthetic_train_only')
    # pycocotools on Windows opens with locale encoding; ASCII escapes preserve Korean labels portably.
    (output/f'{split}.json').write_text(json.dumps(data,ensure_ascii=True,indent=2),encoding='utf-8')
    return {'images':len(data['images']),'objects':len(data['annotations']),
            'multi_object_images':sum(sum(a['image_id']==im['id'] and not a['iscrowd'] for a in data['annotations'])>1 for im in data['images'])}

def main():
    p=argparse.ArgumentParser()
    for split in ('train','val'):
        p.add_argument(f'--{split}-json',type=Path,required=True)
        p.add_argument(f'--{split}-images',type=Path,required=True)
    p.add_argument('--model',type=Path,default=DEFAULT_WEIGHT)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--grids',type=int,default=0)
    p.add_argument('--allow-new-classes',action='store_true')
    a=p.parse_args()
    if a.output.exists():
        p.error('Output must be a new directory to prevent stale data or overwrite')
    if a.grids<0:
        p.error('grids must be nonnegative')
    classes=list(checkpoint(a.model)['meta']['CLASSES'])
    if a.allow_new_classes:
        for path in (a.train_json,a.val_json):
            for c in json.loads(path.read_text(encoding='utf-8-sig'))['categories']:
                if c['name'] not in classes:
                    classes.append(c['name'])
    train=read_split(a.train_json,a.train_images,classes)
    val=read_split(a.val_json,a.val_images,classes)
    if not train or not val:
        p.error('Both splits must contain images')
    if {r['hash'] for r in train}&{r['hash'] for r in val}:
        p.error('Exact image leakage between train and val')
    if {r['group_id'] for r in train}&{r['group_id'] for r in val}:
        p.error('Capture group leakage: keep the same meal/view group in one split')
    a.output.mkdir(parents=True)
    report={'train':write_split(train,a.output,'train',classes,a.grids),
            'val':write_split(val,a.output,'val',classes)}
    (a.output/'classes.json').write_text(json.dumps(classes,ensure_ascii=False,indent=2),encoding='utf-8')
    (a.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(report)

if __name__=='__main__':
    main()
