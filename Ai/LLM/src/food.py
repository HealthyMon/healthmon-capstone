"""A photo is a proposal. Explicit confirmation creates one user-reported meal."""
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import Depends, HTTPException, Request
from pydantic import Field
from psycopg.types.json import Jsonb
from starlette.concurrency import run_in_threadpool
from .contracts import Strict
from .db import connect, owned
from .vision_service import vision_service, ROOT
from .model_runtime import runtime as model_runtime

NUTRIENTS = ('energy_kcal', 'carbohydrate_g', 'protein_g', 'fat_g', 'sugar_g', 'fiber_g', 'sodium_mg')
MAX_IMAGE_BYTES = 12 * 1024 * 1024


class ConfirmFood(Strict):
    analysis_id: str = Field(min_length=32, max_length=32, pattern='^[0-9a-f]+$')
    candidate_id: int = Field(ge=0, le=2)
    grams: float | None = Field(default=None, gt=0, le=10000, allow_inf_nan=False)


def nutrients(values, scale=1):
    output = {}
    for key in NUTRIENTS:
        value = values.get(key)
        available = isinstance(value, (float, int)) and math.isfinite(value) and value >= 0
        output[key] = {'available': available, 'value': round(value * scale, 3) if available else 0}
    return output


def normalize(result, ident):
    candidates = []
    for item in result['candidates'][:3]:
        grams = item.get('estimated_grams')
        has_weight = isinstance(grams, (float, int)) and math.isfinite(grams) and 0 < grams <= 10000
        candidates.append({'candidate_id': len(candidates), 'food': item['food'],
                           'confidence': item['confidence'], 'per_100g': nutrients(item['per_100g']),
                           'has_estimated_grams': has_weight, 'estimated_grams': round(grams, 1) if has_weight else 0,
                           'weight_warning': item.get('weight_warning', '')})
    return {'schema_version': 'healthmon.food.v1', 'analysis_id': ident,
            'backend': result['backend'], 'candidates': candidates,
            'consumption_confirmed': False}


def install_food(app, identity, refreshed, reconcile_quests, current):
    @app.get('/ecosystem/health')
    def ecosystem_health(user=Depends(identity)):
        return {'schema_version': 'healthmon.ecosystem.v1', 'vision': vision_service.status(),
                'model_runtime': model_runtime.status(),
                'food_api': 'healthmon.food.v1', 'consumption_requires_confirmation': True}

    @app.post('/pets/{pet}/food/analyze')
    async def analyze_food(pet: str, request: Request, user=Depends(identity)):
        with connect() as c:
            owned(c, user, pet)
        image = bytearray()
        async for chunk in request.stream():
            if len(image) + len(chunk) > MAX_IMAGE_BYTES:
                raise HTTPException(413, 'Image exceeds 12 MiB')
            image.extend(chunk)
        if not (image.startswith(b'\xff\xd8\xff') or image.startswith(b'\x89PNG\r\n\x1a\n')):
            raise HTTPException(422, 'Send raw JPEG or PNG bytes')
        ident = uuid.uuid4().hex
        directory = ROOT / 'runtime/vision-inputs'
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (ident + '.image')
        try:
            path.write_bytes(image)
            result = await run_in_threadpool(vision_service.analyze, path)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        except RuntimeError as error:
            raise HTTPException(503, str(error)) from error
        finally:
            path.unlink(missing_ok=True)
        output = normalize(result, ident)
        with connect() as c:
            owned(c, user, pet)
            c.execute('INSERT INTO food_analyses(id,pet_id,result) VALUES(%s,%s,%s)', (ident, pet, Jsonb(output)))
        return output

    @app.post('/pets/{pet}/food/confirm')
    def confirm_food(pet: str, body: ConfirmFood, user=Depends(identity)):
        with connect() as c:
            p = owned(c, user, pet, True)
            analysis = c.execute('SELECT * FROM food_analyses WHERE id=%s AND pet_id=%s FOR UPDATE',
                                 (body.analysis_id, pet)).fetchone()
            if not analysis:
                raise HTTPException(404, 'Food analysis not found')
            if analysis['confirmation']:
                saved = analysis['confirmation']
                if saved['candidate_id'] != body.candidate_id or saved['grams'] != body.grams:
                    raise HTTPException(409, 'This photo was already confirmed with different food or quantity')
                source = c.execute('SELECT valid FROM sources WHERE pet_id=%s AND id=%s', (pet, saved['source_id'])).fetchone()
                if not source or not source['valid']:
                    raise HTTPException(410, 'Food record was deleted; analyze again for a new record')
                return {**saved, 'duplicate': True, 'state_version': p['version'], 'state': current(c, p)}
            choices = analysis['result']['candidates']
            if body.candidate_id >= len(choices):
                raise HTTPException(422, 'Choose a returned food candidate')
            selected = choices[body.candidate_id]
            values = {key: item['value'] if item['available'] else None for key, item in selected['per_100g'].items()}
            portion = nutrients(values, body.grams / 100) if body.grams is not None else nutrients({})
            record = {'analysis_id': body.analysis_id, 'food': selected['food'], 'grams': body.grams,
                      'confidence': selected['confidence'], 'nutrition': portion,
                      'quantity_source': 'user_confirmed' if body.grams is not None else 'not_provided',
                      'vision_backend': analysis['result']['backend']}
            source_id = 'activity:food-' + body.analysis_id
            payload = {'event_id': 'food-' + body.analysis_id, 'revision': 1,
                       'occurred_at': datetime.now(timezone.utc).isoformat(), 'kind': 'food',
                       'amount': 1, 'unit': 'serving', 'source': 'user', 'confirmed': True,
                       'label': selected['food'], 'food_record': record}
            c.execute("INSERT INTO sources(pet_id,id,kind,revision,occurred_at,payload) VALUES(%s,%s,'activity',1,%s,%s)",
                      (pet, source_id, payload['occurred_at'], Jsonb(payload)))
            state, version = refreshed(c, p)
            reconcile_quests(c, p)
            output = {'analysis_id': body.analysis_id, 'candidate_id': body.candidate_id, 'grams': body.grams,
                      'source_id': source_id, 'record': record, 'state': state, 'state_version': version, 'duplicate': False}
            c.execute('UPDATE food_analyses SET confirmation=%s WHERE id=%s', (Jsonb(output), body.analysis_id))
            return output

    @app.get('/pets/{pet}/food/records')
    def food_records(pet: str, user=Depends(identity)):
        with connect() as c:
            owned(c, user, pet)
            rows = c.execute("SELECT id AS source_id,occurred_at,payload->'food_record' AS record FROM sources "
                             "WHERE pet_id=%s AND valid AND kind='activity' AND payload ? 'food_record' "
                             'ORDER BY occurred_at DESC,id DESC LIMIT 50', (pet,)).fetchall()
        return {'records': rows}
