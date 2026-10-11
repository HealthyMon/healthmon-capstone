"""Restart ONLY this project's PostgreSQL; compare persistent state and vectors."""
import json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.db import connect
def snapshot():
    with connect() as c:
        return {'pets':c.execute('SELECT id,version,settings FROM pets ORDER BY id').fetchall(),
                'memories':c.execute('SELECT pet_id,id,valid,embedding::text AS embedding FROM memories ORDER BY pet_id,id').fetchall(),
                'rewards':c.execute('SELECT pet_id,offer_id,state_version,amount FROM reward_ledger ORDER BY pet_id,offer_id,state_version').fetchall()}
before=snapshot()
subprocess.run([str(ROOT/'runtime/pgsql/bin/pg_ctl.exe'),'-D',str(ROOT/'runtime/pgdata'),'-m','fast','-w','restart','-l',str(ROOT/'runs/postgres.log')],check=True)
after=snapshot();assert before==after
report={'passed':True,'pets':len(after['pets']),'memories':len(after['memories']),'reward_entries':len(after['rewards']),
        'scope':'real PostgreSQL restart, not Docker restart'}
(ROOT/'runs/restart-check.json').write_text(json.dumps(report,indent=2))
print(report)
