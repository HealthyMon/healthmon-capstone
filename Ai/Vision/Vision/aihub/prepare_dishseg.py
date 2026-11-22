"""Read-only source archive -> bounded-resolution images and food-box manifests."""
import argparse
import gc
import hashlib
import io
import json
import math
import tarfile
from pathlib import Path
from PIL import Image

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--replay',type=Path,required=True)
    p.add_argument('--resume',action='store_true',help='Reuse images written by interrupted preparation')
    a=p.parse_args()
    if a.output.exists() and not a.resume:p.error('Use a new output directory or --resume after interruption')
    if (a.output/'provenance.json').exists():p.error('Completed dataset must not be overwritten')
    index={};summary={}
    for split in ('train','test'):
        source=a.source/f'annotations/instances_{split}.json'
        data=json.loads(source.read_text(encoding='utf-8'))
        rows={im['id']:{'file_name':im['file_name'],'size':[im['width'],im['height']],'boxes':[], 'skip':False} for im in data['images']}
        for obj in data['annotations']:
            row=rows[obj['image_id']]
            if obj.get('iscrowd',0) or obj.get('ignore',0):
                row['skip']=True
                continue
            x,y,w,h=map(float,obj['bbox'])
            if not all(math.isfinite(v) for v in (x,y,w,h)) or min(w,h)<=0:raise ValueError('Invalid source bbox')
            iw,ih=row['size'];box=[max(0,x),max(0,y),min(iw,x+w),min(ih,y+h)]
            if box[2]>box[0] and box[3]>box[1]:row['boxes'].append(box)
        summary[split]={'source_images':len(rows),'source_annotations':len(data['annotations']),
                        'skipped_crowd_or_ignore_images':sum(r['skip'] for r in rows.values())}
        for row in rows.values():
            if row['skip']:continue
            name=row['file_name']
            if name in index:raise ValueError('Official split filename overlap')
            index[name]=dict(row,split='train' if split=='train' else 'eval')
        del data,rows;gc.collect()
    a.output.mkdir(parents=True,exist_ok=a.resume)
    directory=a.output/'images';directory.mkdir(exist_ok=a.resume)
    manifests={'train':[],'eval':[]};seen={};found=set();size_mismatches=[]
    with tarfile.open(a.source/'archives/DishSeg24k_images.tar') as archive:
        for member in archive:
            name=Path(member.name).name
            if not member.isfile() or name not in index or '/._' in member.name:continue
            if name in found:raise ValueError(f'Duplicate archive image {name}')
            found.add(name);row=index[name]
            payload=archive.extractfile(member).read();digest=hashlib.sha256(payload).hexdigest()
            seen.setdefault(digest,set()).add(row['split'])
            with Image.open(io.BytesIO(payload)) as source:
                if list(source.size)!=row['size']:
                    size_mismatches.append({'file':name,'annotation_size':row['size'],'actual_size':list(source.size)})
                    continue
                if (directory/name).exists():
                    with Image.open(directory/name) as prepared:prepared_size=prepared.size
                else:
                    image=source.convert('RGB')
                    image.thumbnail((960,960),Image.Resampling.LANCZOS)
                    image.save(directory/name,quality=95)
                    prepared_size=image.size
            sx,sy=prepared_size[0]/row['size'][0],prepared_size[1]/row['size'][1]
            boxes=[[x1*sx,y1*sy,x2*sx,y2*sy] for x1,y1,x2,y2 in row['boxes']]
            manifests[row['split']].append({'image':str((directory/name).resolve()),'boxes':boxes,
                                            'source_sha256':digest,'source_file':name})
    if set(index)!=found:raise ValueError(f'Missing {len(set(index)-found)} source images')
    summary['excluded_annotation_resolution_mismatches']=size_mismatches
    replay=json.loads(a.replay.read_text(encoding='utf-8'))
    forbidden={r['source_sha256'] for r in manifests['train']}|{r['source_sha256'] for r in replay if r.get('source_sha256')}
    summary['excluded_eval_overlap_with_train_or_replay']=sum(r['source_sha256'] in forbidden for r in manifests['eval'])
    manifests['eval']=[r for r in manifests['eval'] if r['source_sha256'] not in forbidden]
    for split in manifests:
        unique={}
        for row in manifests[split]:unique.setdefault(row['source_sha256'],row)
        summary[split+'_within_split_exact_duplicates_removed']=len(manifests[split])-len(unique)
        manifests[split]=list(unique.values())
    for split,rows in manifests.items():
        rows.sort(key=lambda r:r['source_file'])
        (a.output/f'{split}.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
        summary[split+'_prepared']={'images':len(rows),'boxes':sum(len(r['boxes']) for r in rows),'multi_images':sum(len(r['boxes'])>1 for r in rows)}
    manifests['train'].extend(replay*4)
    (a.output/'train.json').write_text(json.dumps(manifests['train'],indent=2),encoding='utf-8')
    summary.update(replay_unique_images=len(replay),replay_repetitions=4,source=str(a.source.resolve()),
                   labels='COCO instance boxes, category-agnostic; ignored/crowd images excluded',
                   resize='long side <=960; boxes scaled identically',evaluation='official test only, no selection using test results')
    (a.output/'provenance.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
