"""Explicitly register verified existing stage0 files in the selected common DB."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from Server.healthmon.config import Settings
from Server.healthmon.db import Database
from Server.healthmon import service,starters


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--set-default',action='store_true')
    parser.add_argument('--attach-pet')
    parser.add_argument('--owner-id')
    args=parser.parse_args()
    if bool(args.attach_pet)!=bool(args.owner_id):parser.error('Attach requires both pet ID and owner ID')
    settings=Settings.from_env();db=Database(settings);db.ready()
    with db.connect() as c:
        result=starters.register(c,args.manifest,set_default=args.set_default)
        if args.attach_pet:
            p=service.owned(c,args.owner_id,args.attach_pet,True)
            bound=starters.bind_default(c,p,service.utcnow(),settings.chat_available(args.owner_id))
            if not bound or bound['job_id']!=result['starter_id']:
                raise ValueError('Selected default differs from the requested starter; no changes committed')
            result['attached_pet']=args.attach_pet
    print(json.dumps(result))


if __name__=='__main__':main()
