"""Train locator only. No validation during training; one final evaluation is separate."""
import argparse
import json
import random
from pathlib import Path
import torch
from torch.utils.data import Dataset,DataLoader
from PIL import Image
from torchvision.transforms.functional import to_tensor
from region_model import build,load,ARCHITECTURE

class Foods(Dataset):
    def __init__(self,path):
        self.rows=json.loads(Path(path).read_text(encoding='utf-8'))
    def __len__(self): return len(self.rows)
    def __getitem__(self,index):
        row=self.rows[index]
        with Image.open(row['image']) as im: image=im.convert('RGB')
        boxes=torch.tensor(row['boxes'],dtype=torch.float32).reshape(-1,4)
        if random.random()<.5:
            image=image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            boxes[:,[0,2]]=image.width-boxes[:,[2,0]]
        return to_tensor(image),{'boxes':boxes,'labels':torch.ones(len(boxes),dtype=torch.int64)}

def collate(batch):return tuple(zip(*batch))

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--epochs',type=int,default=3)
    p.add_argument('--batch',type=int,default=4)
    p.add_argument('--init',type=Path)
    p.add_argument('--short-side',type=int,default=320)
    p.add_argument('--max-side',type=int,default=640)
    p.add_argument('--lr',type=float,default=.0025)
    p.add_argument('--workers',type=int,default=0)
    p.add_argument('--amp',action='store_true')
    a=p.parse_args()
    if a.output.exists():p.error('Output must be new')
    if min(a.epochs,a.batch)<1:p.error('epochs and batch must be positive')
    random.seed(42);torch.manual_seed(42)
    device='cuda:0' if torch.cuda.is_available() else 'cpu'
    train_rows=json.loads((a.data/'train.json').read_text(encoding='utf-8'))
    eval_rows=json.loads((a.data/'eval.json').read_text(encoding='utf-8'))
    train_hashes={r['source_sha256'] for r in train_rows if r.get('source_sha256')}
    eval_hashes={r['source_sha256'] for r in eval_rows if r.get('source_sha256')}
    if train_hashes & eval_hashes:
        p.error('Exact source-image leakage between training/replay and final evaluation')
    torch.set_num_threads(4)
    model=load(a.init,device) if a.init else build(pretrained=True).to(device)
    model.transform.min_size=(a.short_side,);model.transform.max_size=a.max_side
    optimizer=torch.optim.SGD([p for p in model.parameters() if p.requires_grad],lr=a.lr,momentum=.9,weight_decay=.0001)
    loader=DataLoader(Foods(a.data/'train.json'),batch_size=a.batch,shuffle=True,num_workers=a.workers,
                      collate_fn=collate,pin_memory=device.startswith('cuda'),persistent_workers=a.workers>0)
    scaler=torch.cuda.amp.GradScaler(enabled=a.amp and device.startswith('cuda'))
    scheduler=torch.optim.lr_scheduler.StepLR(optimizer,step_size=max(1,a.epochs-1),gamma=.2)
    if not len(loader):p.error('Empty training data')
    a.output.mkdir(parents=True)
    log=[]
    for epoch in range(a.epochs):
        model.train();total=0
        for step,(images,targets) in enumerate(loader):
            images=[x.to(device) for x in images]
            targets=[{k:v.to(device) for k,v in t.items()} for t in targets]
            with torch.cuda.amp.autocast(enabled=scaler.is_enabled()):
                losses=model(images,targets)
                loss=sum(losses.values())
            if not torch.isfinite(loss):raise RuntimeError('Non-finite training loss')
            optimizer.zero_grad();scaler.scale(loss).backward();scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(),10)
            scaler.step(optimizer);scaler.update();total+=float(loss.detach())
        row={'epoch':epoch+1,'training_loss':total/len(loader)}
        log.append(row);print(row,flush=True)
        scheduler.step()
        torch.save({'architecture':ARCHITECTURE,'state_dict':model.state_dict(),'epochs':epoch+1,
                    'source':str(a.data.resolve()),'min_size':a.short_side,'max_size':a.max_side,
                    'initial_checkpoint':str(a.init) if a.init else 'torchvision COCO','validation_performed':False},a.output/'food_regions.pth')
        (a.output/'training.json').write_text(json.dumps(log,indent=2))

if __name__=='__main__':main()
