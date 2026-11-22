"""Count correct/missed food instances, separately for multi-food images."""
import argparse
import json
from pathlib import Path
from detect import DEFAULT_WEIGHT,load_model,predict,overlap

def match(foods,targets,iou=.5):
    used=set()
    for food in sorted(foods,key=lambda x:x['confidence'],reverse=True):
        choices=[(overlap(food['bbox_xyxy'],t['box']),i) for i,t in enumerate(targets)
                 if i not in used and food['class_id']==t['class_id']]
        score,index=max(choices,default=(0,-1))
        if score>=iou:
            used.add(index)
    return len(used)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,required=True)
    p.add_argument('--model',type=Path,default=DEFAULT_WEIGHT)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--threshold',type=float,default=.35)
    p.add_argument('--device',default='cuda:0')
    a=p.parse_args()
    data=json.loads((a.data/'val.json').read_text(encoding='utf-8'))
    classes=json.loads((a.data/'classes.json').read_text(encoding='utf-8'))
    model=load_model(a.model,a.device)
    if list(model.CLASSES)!=classes:
        p.error('Checkpoint and dataset classes differ; evaluate with the matching class schema')
    rows=[]
    for image in data['images']:
        annotations=[x for x in data['annotations'] if x['image_id']==image['id']]
        if any(x.get('iscrowd',0) for x in annotations):
            continue # this object-count diagnostic does not implement COCO crowd matching
        targets=[]
        for obj in annotations:
            x,y,w,h=obj['bbox']
            targets.append({'class_id':obj['category_id']-1,'box':[x,y,x+w,y+h]})
        result,_=predict(model,a.data/'val'/image['file_name'],a.threshold)
        tp=match(result['foods'],targets)
        rows.append({'file_name':image['file_name'],'targets':len(targets),'predictions':len(result['foods']),
                     'correct':tp,'missed':len(targets)-tp,'false_positive':len(result['foods'])-tp})
    def summary(items):
        gt=sum(r['targets'] for r in items)
        pred=sum(r['predictions'] for r in items)
        tp=sum(r['correct'] for r in items)
        return {'images':len(items),'ground_truth_objects':gt,'predictions':pred,'correct':tp,
                'recall':tp/gt if gt else None,'precision':tp/pred if pred else None}
    report={'all':summary(rows),'multi_food':summary([r for r in rows if r['targets']>=2]),
            'threshold':a.threshold,'iou':.5,'per_image':rows,
            'note':'Class-aware one-to-one matching; food instances, not physical plates. Crowd images excluded. Not mAP.'}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='per_image'},indent=2))

if __name__=='__main__':
    main()
