"""Immutable operator-provisioned stage0 assets; no inference or per-pet blob copies."""
import hashlib
import base64
import json
from pathlib import Path
import re

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from . import service

PREFIX='starter-'


def ensure_default(c,manifest_path):
    """Bootstrap the packaged game asset without replacing an operator's choice."""
    c.execute("SELECT pg_advisory_xact_lock(hashtext('healthmon.starter.default'))")
    existing=c.execute('SELECT starter_id FROM starter_model_default WHERE singleton').fetchone()
    if existing:return existing['starter_id']
    result=register(c,manifest_path)
    c.execute('INSERT INTO starter_model_default(singleton,starter_id) VALUES(true,%s) ON CONFLICT(singleton) DO NOTHING',
              (result['starter_id'],))
    return c.execute('SELECT starter_id FROM starter_model_default WHERE singleton').fetchone()['starter_id']


def register(c, manifest_path, *, set_default=False):
    from .worker import validate_glb
    path=Path(manifest_path)
    raw=path.read_bytes(); manifest=json.loads(raw.decode('utf-8-sig'))
    if type(manifest.get('stage')) is not int or manifest['stage']!=0:
        raise ValueError('Only an actual stage0 manifest may be provisioned as a starter')
    species=manifest.get('species','lucan')
    if not isinstance(species,str) or re.fullmatch(r'[a-z][a-z0-9_-]{0,63}',species) is None:
        raise ValueError('Invalid starter species')
    model=path.parent/'model.glb'; image=path.parent/'image.png'
    if not 20 <= model.stat().st_size <= 64*1024*1024:
        raise ValueError('Starter model must be at most64MiB; no automatic compression')
    data=model.read_bytes(); digest=hashlib.sha256(data).hexdigest()
    image_data=image.read_bytes()
    image_digest=hashlib.sha256(image_data).hexdigest()
    if not 8<=len(image_data)<=1024*1024 or not image_data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Starter parent must be a PNG of at most1MiB')
    if digest!=manifest.get('model_sha256') or image_digest!=manifest.get('image_sha256'):
        raise ValueError('Starter files differ from their manifest')
    validate_glb(data)
    manifest_digest=hashlib.sha256(raw).hexdigest()
    ident=PREFIX+service.fingerprint({'model':digest,'image':image_digest,'manifest':manifest_digest,'species':species})
    provenance={'source_kind':'verified_existing_stage0','new_generation':False,'stage':0,
                'species':species,'model_sha256':digest,'image_sha256':image_digest,
                'manifest_sha256':manifest_digest}
    if manifest.get('species_contract') is not None:provenance['species_contract']=manifest['species_contract']
    c.execute('INSERT INTO starter_models(id,species,sha256,size_bytes,image_sha256,manifest_sha256,provenance,data,image_data) '
              'VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING',
              (ident,species,digest,len(data),image_digest,manifest_digest,Jsonb(provenance),data,image_data))
    c.execute('UPDATE starter_models SET image_data=%s WHERE id=%s AND image_data IS NULL',(image_data,ident))
    stored=c.execute('SELECT sha256,data,provenance,image_data FROM starter_models WHERE id=%s',(ident,)).fetchone()
    if stored['sha256']!=digest or hashlib.sha256(bytes(stored['data'])).hexdigest()!=digest or stored['provenance']!=provenance:
        raise ValueError('Existing immutable starter asset failed its identity check')
    if bytes(stored['image_data'])!=image_data:raise ValueError('Existing starter parent image was modified')
    if set_default:
        c.execute('INSERT INTO starter_model_default(singleton,starter_id) VALUES(true,%s) '
                  'ON CONFLICT(singleton) DO UPDATE SET starter_id=excluded.starter_id',(ident,))
    return {'starter_id':ident,'species':species,'stage':0,'model_sha256':digest,'size_bytes':len(data),'new_generation':False}


def bind_default(c,p,timestamp,ai_available=False):
    p=service.owned(c,p['owner_id'],p['id'],True)
    default=c.execute('SELECT starter_id FROM starter_model_default WHERE singleton').fetchone()
    if not default:return None
    existing=c.execute('SELECT starter_id FROM pet_starter_models WHERE pet_id=%s',(p['id'],)).fetchone()
    if existing:return manifest(c,p,existing['starter_id'])
    state,_=service.refresh(c,p,timestamp,ai_available)
    if state['published_model_stage']!=0 or state.get('model_reference'):
        raise HTTPException(409,'An existing published model cannot be replaced by a starter')
    ident=default['starter_id']
    c.execute('INSERT INTO pet_starter_models(pet_id,starter_id) VALUES(%s,%s)',(p['id'],ident))
    state.update(model_reference=f"/pets/{p['id']}/assets/{ident}",asset_status='ready')
    c.execute('UPDATE game_states SET state=%s WHERE pet_id=%s',(Jsonb(state),p['id']))
    service.refresh(c,p,timestamp,ai_available,True,'starter_bound')
    return manifest(c,service.owned(c,p['owner_id'],p['id']),ident)


def manifest(c,p,ident):
    row=c.execute('SELECT s.id,s.sha256,s.species FROM starter_models s JOIN pet_starter_models b ON b.starter_id=s.id '
                  'WHERE b.pet_id=%s AND s.id=%s',(p['id'],ident)).fetchone()
    if not row:return None
    reference=f"/pets/{p['id']}/assets/{ident}"
    return {'job_id':ident,'request_id':ident,'stage':0,'status':'succeeded','model_reference':reference,
            'model_url':reference,'model_sha256':row['sha256'],'error':None,'state_version':p['version'],
            'species':row['species'],'provenance':'verified_existing_stage0','new_generation':False}


def asset(c,pet,ident):
    return c.execute('SELECT s.data,s.sha256 FROM starter_models s JOIN pet_starter_models b ON b.starter_id=s.id '
                     'WHERE b.pet_id=%s AND s.id=%s',(pet,ident)).fetchone()


def parent_asset(c,pet):
    row=c.execute('SELECT s.id,s.species,s.sha256,s.image_sha256,s.image_data,s.provenance FROM starter_models s '
                  'JOIN pet_starter_models b ON b.starter_id=s.id WHERE b.pet_id=%s',(pet,)).fetchone()
    if not row or row['image_data'] is None:raise HTTPException(409,'Starter parent image must be provisioned before evolution')
    image=bytes(row['image_data'])
    if hashlib.sha256(image).hexdigest()!=row['image_sha256']:raise HTTPException(409,'Starter parent image identity failed')
    return {'stage':0,'revision':row['id'],'species':row['species'],'species_contract':row['provenance'].get('species_contract'),
            'image_base64':base64.b64encode(image).decode('ascii'),'image_sha256':row['image_sha256'],
            'model_sha256':row['sha256'],'source_kind':'common_server_verified_starter'}
