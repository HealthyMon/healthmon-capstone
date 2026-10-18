import argparse,json,os,sys,uuid
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
import httpx
p=argparse.ArgumentParser(description='Synthetic local producer; not a real wearable measurement')
p.add_argument('--pet',required=True);p.add_argument('--steps',type=int,required=True);p.add_argument('--event-id',default=None)
p.add_argument('--revision',type=int,default=1);args=p.parse_args()
headers={'Authorization':'Bearer '+list(json.loads(os.environ['DEV_TOKENS']))[0],'X-Producer-Token':os.environ['PRODUCER_TOKEN']}
data={'event_id':args.event_id or uuid.uuid4().hex,'revision':args.revision,'occurred_at':datetime.now(timezone.utc).isoformat(),
      'kind':'walk','amount':args.steps,'unit':'steps','source':'backend','confirmed':True,'label':'local synthetic test'}
r=httpx.post(f'http://127.0.0.1:8000/pets/{args.pet}/activities',json=data,headers=headers,timeout=30)
print(r.status_code,r.text)
