"""LAN inference service for Unity. Run with Start-VisionServer.ps1."""
import asyncio
import base64
import csv
import io
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import uuid
import hmac

from fastapi import FastAPI, File, HTTPException, UploadFile, Request
from PIL import Image, UnidentifiedImageError

ROOT = Path(__file__).resolve().parent
PYTHON = ROOT/'.venv-aihub/Scripts/python.exe'
CSV = ROOT/'음식 탐지/noisyvit_food2k_nutrition_all2000.csv'
app = FastAPI(title='HealthMon Multi Food Vision', version='1.0')
analysis_lock = asyncio.Lock()
MAX_BYTES = 8*1024*1024
MAX_PIXELS = 16_000_000
RUNTIME = ROOT/'outputs/unity_api'


def numeric(value):
    try:
        x=float(value)
        return x if math.isfinite(x) and x>=0 else None
    except (TypeError,ValueError):return None


def nutrients(values):
    result={}
    for target,source in [('calories','energy_kcal_100g'),('carbs','carbohydrate_g_100g'),
                          ('protein','protein_g_100g'),('fat','fat_g_100g')]:
        value=numeric(values.get(source))
        result[target]=value if value is not None else 0
        result['has_'+target]=value is not None
    return result


def catalog():
    with CSV.open(encoding='utf-8-sig',newline='') as stream:
        return [{'class_id':int(r['food2k_class_id']),'name':r['food_name_en'],
                 'per100':nutrients(dict(r,energy_kcal_100g=r['estimated_energy_kcal_100g'])),
                 'nutrition_source':r.get('reference_food_name',''),
                 'nutrition_confidence':r.get('confidence','')} for r in csv.DictReader(stream)]


@app.get('/health')
def health():return {'status':'ok','service':'healthmon-multifood','schema_version':1}


@app.get('/vision/catalog')
def find_food(q:str='',limit:int=30):
    query=q.strip().casefold()
    return {'items':[r for r in catalog() if query in r['name'].casefold()][:max(1,min(limit,50))]}


def encode(path):return base64.b64encode(path.read_bytes()).decode('ascii')


def build_response(payload,folder):
    foods=[]
    for f in payload['foods']:
        mass=numeric(f.get('weight_g'))
        n=f.get('nutrition') or {}
        foods.append({'id':f['id'],'class_id':f['class_id'],'name':f['name'],
                      'grams':mass or 0,'has_weight':mass is not None and mass>0,
                      'weight_status':f.get('weight_status',''),
                      'name_confidence':f.get('name_confidence',0),
                      'bbox':f['bbox_normalized_xyxy'],
                      'per100':nutrients(n.get('per_100g',{})),
                      'nutrition_source':n.get('matched_food_name',''),
                      'nutrition_confidence':n.get('reference_confidence',''),
                      'crop_base64':encode(folder/f['crop_file']),
                      'name_edited':False,'weight_edited':False})
    return {'schema_version':1,'analysis_id':uuid.uuid4().hex,
            'image_width':payload['image_size']['width'],'image_height':payload['image_size']['height'],
            'annotated_base64':encode(folder/'annotated.jpg'),
            'original_base64':encode(folder/'input_upright.jpg'),'foods':foods}


def inference(data):
    RUNTIME.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='request_',dir=RUNTIME) as temporary:
        folder=Path(temporary); image=folder/'input.jpg';image.write_bytes(data)
        command=[str(PYTHON),str(ROOT/'aihub/detect.py'),str(image),'--regions',
                 str(ROOT/'runs/food_regions_dishseg/food_regions.pth'),
                 '--classifier','food2k','--class-order','csv','--weight-backend','fpb',
                 '--device',os.environ.get('VISION_DEVICE','cuda:0'),'--output',str(folder)]
        with (folder/'process.log').open('wb') as log:
            process=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=log)
            try:process.wait(timeout=300)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                process.wait()
                raise HTTPException(504,'AI 분석 시간이 초과되었습니다.')
        if process.returncode:
            # Keep only a bounded diagnostic, not the user's photo.
            with (folder/'process.log').open('rb') as log:
                log.seek(max(0,(folder/'process.log').stat().st_size-6000))
                (RUNTIME/'last_error.log').write_bytes(log.read())
            raise HTTPException(500,'AI 실행 실패. 서버 outputs/unity_api/last_error.log를 확인하세요.')
        return build_response(json.loads((folder/'result.json').read_text(encoding='utf-8')),folder)


@app.post('/vision/analyze')
async def analyze(image:UploadFile=File(...)):
    data=await image.read(MAX_BYTES+1)
    await image.close()
    if not data:raise HTTPException(400,'사진이 비어 있습니다.')
    if len(data)>MAX_BYTES:raise HTTPException(413,'사진은 8MB 이하여야 합니다.')
    try:
        with Image.open(io.BytesIO(data)) as photo:
            if photo.width*photo.height>MAX_PIXELS:raise HTTPException(413,'사진은 1600만 화소 이하여야 합니다.')
            if photo.format not in ('JPEG','PNG'):raise HTTPException(415,'JPG 또는 PNG 사진이 필요합니다.')
            photo.verify()
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError):
        raise HTTPException(400,'사진 파일을 읽을 수 없습니다.')
    if analysis_lock.locked():raise HTTPException(503,'다른 사진을 분석 중입니다. 잠시 후 다시 시도하세요.')
    async with analysis_lock:
        return await asyncio.to_thread(inference,data)


@app.post('/v1/food')
async def common_server_food(request:Request):
    # Same server-to-server credential as the common API; never return it to Unity.
    config=ROOT.parents[2]/'.env'
    expected=os.environ.get('AI_SERVER_TOKEN','')
    if not expected and config.exists():
        for line in config.read_text(encoding='utf-8-sig').splitlines():
            if line.startswith('AI_SERVER_TOKEN='):
                expected=line.split('=',1)[1].strip().strip('\"\'')
    supplied=request.headers.get('authorization','')
    if not expected or not hmac.compare_digest(supplied,'Bearer '+expected):
        raise HTTPException(401,'Invalid gateway credential')
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>12*1024*1024:raise HTTPException(413,'Request too large')
    try:
        body=json.loads(raw)
        if body['contract_version']!='healthmon.ai.v1':raise ValueError()
        request_id=body['request_id']
        if not isinstance(request_id,str) or not 8<=len(request_id)<=100:raise ValueError()
        data=base64.b64decode(body['input']['image_base64'],validate=True)
    except (ValueError,KeyError,TypeError):raise HTTPException(422,'Invalid food request')
    upload=UploadFile(file=io.BytesIO(data),filename='food.jpg')
    result=await analyze(upload)
    candidates=[]
    for food in result['foods'][:3]:
        n=food['per100'];mass=food['grams'] if food['has_weight'] and food['grams']<=10000 else None
        candidates.append({'food':food['name'],'confidence':food['name_confidence'],
                           'estimated_grams':mass,
                           'per_100g':{key:n[source] if n['has_'+source] else None for key,source in
                                       [('energy_kcal','calories'),('carbohydrate_g','carbs'),('protein_g','protein'),('fat_g','fat')]}})
    if not candidates:raise HTTPException(422,'No food detected')
    return {'contract_version':'healthmon.ai.v1','request_id':request_id,'provenance':'real',
            'result':{'candidates':candidates,'vision':result}}
