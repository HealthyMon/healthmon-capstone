"""Convert official semantic masks into weak food-instance boxes for a locator.

No UEC class names are mapped onto the existing 800-class recognizer.
Same-class touching food regions cannot be separated reliably from semantic masks.
"""
import argparse
import hashlib
import io
import json
import random
import tarfile
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

def boxes_from_mask(mask):
    if mask.ndim==3:
        mask=mask[:,:,0]
    h,w=mask.shape
    boxes=[]
    for label in np.unique(mask):
        if label==0:
            continue
        binary=(mask==label).astype(np.uint8)
        # Reconnect small annotation gaps without joining distant plates.
        closed=cv2.morphologyEx(binary,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
        count,_,stats,_=cv2.connectedComponentsWithStats(closed,8)
        for x,y,bw,bh,area in stats[1:]:
            if area<max(64,h*w*.001) or min(bw,bh)<8:
                continue
            boxes.append([int(x),int(y),int(x+bw),int(y+bh)])
    return boxes

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--train-count',type=int,default=600)
    p.add_argument('--eval-count',type=int,default=96)
    a=p.parse_args()
    if a.output.exists():
        p.error('Output directory must be new')
    rng=random.Random(42)
    records={'train':[],'test':[]}
    with tarfile.open(a.archive) as archive:
        files={m.name:m for m in archive.getmembers() if m.isfile()}
        for name,member in files.items():
            split=next((s for s in records if f'/{s}/mask/' in '/'+name),None)
            if split is None or not name.lower().endswith('.png'):
                continue
            with Image.open(archive.extractfile(member)) as source:
                mask=np.asarray(source)
            boxes=boxes_from_mask(mask)
            img_name=name.replace('/mask/','/img/').rsplit('.',1)[0]+'.jpg'
            if not boxes or img_name not in files:
                continue
            records[split].append({'member':img_name,'boxes':boxes,'width':mask.shape[1],'height':mask.shape[0]})
        a.output.mkdir(parents=True)
        seen=set()
        summary={}
        for split,limit in [('train',a.train_count),('test',a.eval_count)]:
            multi=[r for r in records[split] if len(r['boxes'])>1]
            single=[r for r in records[split] if len(r['boxes'])==1]
            rng.shuffle(multi); rng.shuffle(single)
            selected=multi[:int(limit*.75)]+single[:limit-min(len(multi),int(limit*.75))]
            result=[]
            target_split='train' if split=='train' else 'eval'
            directory=a.output/target_split
            directory.mkdir()
            for r in selected:
                payload=archive.extractfile(files[r['member']]).read()
                digest=hashlib.sha256(payload).hexdigest()
                if digest in seen:
                    continue
                seen.add(digest)
                with Image.open(io.BytesIO(payload)) as source:
                    image=source.convert('RGB')
                if image.size!=(r['width'],r['height']):
                    raise ValueError(f'Mask/image resolution mismatch: {r["member"]}')
                name=f'{Path(r["member"]).stem}.jpg'
                image.save(directory/name,quality=95)
                result.append({'image':str((directory/name).resolve()),'boxes':r['boxes'],
                               'source_member':r['member'],'source_sha256':digest})
            (a.output/f'{target_split}.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            summary[target_split]={'images':len(result),'multi_region_images':sum(len(x['boxes'])>1 for x in result),
                                   'regions':sum(len(x['boxes']) for x in result),'source_split':split}
        summary.update(source='https://mm.cs.uec.ac.jp/uecfoodpix/',license='non-commercial research only',
                       annotation='weak instance boxes derived from semantic mask connected components',seed=42)
        (a.output/'provenance.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        print(json.dumps(summary,indent=2))

if __name__=='__main__':
    main()
