"""The shared CPU FastAPI application. Run uvicorn with --factory."""
import asyncio
import base64
import json
import logging
import re
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import timedelta
import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from psycopg.types.json import Jsonb
from .config import Settings
from .contracts import Chat, ConfirmFood, Decision, Evolution, Goal, LegacyActivity, Meal, Memory, PetSettings, Proposal, ProposalControl, Session, SourceEdit, Workout
from .db import Database
from .gateway import AIUnavailable, Gateway
from . import rules, service


def create_app(settings=None, database=None):
    settings = settings or Settings.from_env()
    db = database or Database(settings)
    gateway = Gateway(settings)

    @asynccontextmanager
    async def lifespan(application):
        db.ready()  # The separate migration service must succeed first.
        if settings.starter_manifest is not None:
            from . import starters
            with db.connect() as c:
                starters.ensure_default(c,settings.starter_manifest)
        task = None
        if settings.worker_enabled:
            from .worker import run_once
            async def loop():
                while True:
                    try:
                        await asyncio.to_thread(run_once, db, settings, gateway)
                    except Exception as error:
                        # Keep the supervisor alive without logging credentials, records or AI bodies.
                        logging.getLogger(__name__).error('background_reconciliation_failed:%s', type(error).__name__)
                    await asyncio.sleep(5)
            task = asyncio.create_task(loop())
        yield
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title='HEALTHMON common server', version='2.2.0', lifespan=lifespan)
    app.state.clock = service.utcnow
    app.state.db, app.state.settings, app.state.gateway = db, settings, gateway

    def now():
        return app.state.clock()

    def identity(authorization: str = Header(default='')):
        if not authorization.startswith('Bearer '):
            raise HTTPException(401, 'Bearer authentication required')
        owner = settings.owner(authorization[7:])
        if not owner:
            raise HTTPException(401, 'Invalid or expired bearer token')
        return owner

    def ai(owner):
        info = db.ready()
        gateway.assert_available(owner, info['environment'] == 'test')
        return info['environment'] == 'test'

    @app.exception_handler(psycopg.Error)
    async def database_error(request, error):
        return JSONResponse(status_code=503, content={'detail': {'code': 'database_unavailable', 'retry_same_id': True}})

    @app.exception_handler(AIUnavailable)
    async def ai_error(request, error):
        return JSONResponse(status_code=503, content={'detail': {'code': error.code, 'retryable': error.retryable, 'ai_mode': settings.ai_mode}})

    @app.get('/health/live')
    def live():
        return {'status': 'ok'}

    @app.get('/health/ready')
    @app.get('/health')
    def ready():
        try:
            info = db.ready()
        except RuntimeError as exc:
            raise HTTPException(503, 'Database migration/environment is not ready') from exc
        return {'status': 'ok', 'ready': True, 'ai_mode': settings.ai_mode, **info}

    @app.get('/server-info')
    def server_info():
        info = db.ready()
        return {'server_instance_id': info['instance_id'], 'environment': info['environment'], 'rule_version': rules.RULE_VERSION,
                'public_base_url': settings.public_base_url or None}

    @app.get('/identity')
    def get_identity(owner=Depends(identity)):
        return {'owner_id': owner, 'authentication': 'provisioned_bearer', 'development_auth': settings.environment != 'production'}

    @app.get('/ecosystem/health')
    @app.get('/health/dependencies')
    def dependencies(owner=Depends(identity)):
        return {'ai_mode': settings.ai_mode, 'schema_version': 'healthmon.ecosystem.v1',
                'vision': {'available': False if settings.ai_mode == 'disabled' else True if settings.ai_mode == 'mock' else None,
                           'status': 'disabled' if settings.ai_mode == 'disabled' else 'synthetic' if settings.ai_mode == 'mock' else 'configured_unverified', 'backend': settings.ai_mode},
                'model_runtime': {'location': 'remote_gateway', 'local_gpu_required': False},
                'food_api': 'healthmon.food.v1', 'consumption_requires_confirmation': True,
                'note': 'Configured remote mode does not imply a successful external GPU connection'}

    @app.post('/pets')
    def create_pet(body: PetSettings, owner=Depends(identity)):
        pet, timestamp = uuid.uuid4().hex, now()
        with db.connect() as c:
            c.execute('INSERT INTO pets(id,owner_id,settings,created_at) VALUES(%s,%s,%s,%s)', (pet, owner, Jsonb(body.model_dump()), timestamp))
            service.seed_goals(c, pet, timestamp)
            p = service.owned(c, owner, pet, True)
            state, _ = service.refresh(c, p, timestamp, settings.chat_available(owner))
            from . import starters
            p=service.owned(c,owner,pet,True)
            if starters.bind_default(c,p,timestamp,settings.chat_available(owner)):
                state,_=service.refresh(c,service.owned(c,owner,pet,True),timestamp,settings.chat_available(owner))
        return {'pet_id': pet, 'state_version': state['state_version'], 'state': state}

    @app.get('/pets')
    def list_pets(owner=Depends(identity)):
        with db.connect() as c:
            rows = c.execute("SELECT id AS pet_id,settings,settings->>'name' AS name,version AS state_version FROM pets WHERE owner_id=%s ORDER BY created_at,id", (owner,)).fetchall()
        return {'pets': rows}

    @app.get('/pets/{pet}/state')
    def get_state(pet: str, owner=Depends(identity)):
        with db.connect() as c:
            p = service.owned(c, owner, pet, True)
            timestamp, available = now(), settings.chat_available(owner)
            state, _ = service.refresh(c, p, timestamp, available)
            # Pets created before packaged starters existed also need a visible
            # stage0 asset. Never replace a published model or reset progression.
            if state['published_model_stage'] == 0 and not state.get('model_reference'):
                from . import starters
                if starters.bind_default(c, p, timestamp, available):
                    state, _ = service.refresh(c, service.owned(c, owner, pet, True), timestamp, available)
        return state

    @app.put('/pets/{pet}/settings')
    def set_settings(pet: str, body: PetSettings, owner=Depends(identity)):
        with db.connect() as c:
            p = service.owned(c, owner, pet, True)
            c.execute('UPDATE pets SET settings=%s WHERE id=%s', (Jsonb(body.model_dump()), pet))
            p['settings'] = body.model_dump()
            state, _ = service.refresh(c, p, now(), settings.chat_available(owner))
        return state

    @app.get('/pets/{pet}/history')
    def history(pet: str, owner=Depends(identity)):
        with db.connect() as c:
            service.owned(c, owner, pet)
            rows = c.execute('SELECT version,state,created_at FROM state_snapshots WHERE pet_id=%s ORDER BY version DESC LIMIT 100', (pet,)).fetchall()
        return {'history': rows}

    @app.get('/pets/{pet}/goals')
    def goals(pet: str, owner=Depends(identity)):
        with db.connect() as c:
            service.owned(c, owner, pet)
            rows = c.execute('SELECT * FROM workout_goals WHERE pet_id=%s ORDER BY effective_at DESC,id', (pet,)).fetchall()
        return {'goals': rows}

    @app.post('/pets/{pet}/goals')
    def set_goal(pet: str, body: Goal, owner=Depends(identity)):
        exercise = service.normalized_exercise(body.exercise_type)
        default = rules.DEFAULT_GOALS.get(exercise)
        if default and body.unit != default['unit']:
            raise HTTPException(422, 'Unit must match the representative exercise metric')
        if default and body.body_part != default['body_part']:
            raise HTTPException(422, 'Known exercise body part is fixed by the game rule')
        ident = uuid.uuid4().hex
        with db.connect() as c:
            service.owned(c, owner, pet, True)
            row = c.execute('INSERT INTO workout_goals(pet_id,id,exercise_type,target,unit,body_part,effective_at) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *',
                            (pet, ident, exercise, body.target, body.unit, body.body_part, now())).fetchone()
        return row

    @app.post('/pets/{pet}/workouts')
    def workout(pet: str, body: Workout, owner=Depends(identity)):
        raw = body.model_dump()
        with db.connect() as c:
            p = service.owned(c, owner, pet, True)
            payload = service.normalize_workout(c, pet, raw)
            result = service.store_event(c, p, 'workout', raw, payload, now(), settings)
        return result

    @app.post('/pets/{pet}/meals')
    def meal(pet: str, body: Meal, owner=Depends(identity)):
        with db.connect() as c:
            result = service.store_event(c, service.owned(c, owner, pet, True), 'meal', body.model_dump(), body.model_dump(mode='json'), now(), settings)
        return result

    def record_list(pet, owner, kind):
        with db.connect() as c:
            service.owned(c, owner, pet)
            rows = c.execute("SELECT id AS event_id,revision,occurred_at,received_at,evaluation_status,synthetic,payload->'data' AS record FROM sources WHERE pet_id=%s AND valid AND payload->>'_game_kind'=%s ORDER BY occurred_at DESC,id LIMIT 200", (pet, kind)).fetchall()
        return {'records': rows}

    @app.get('/pets/{pet}/workouts')
    def workouts(pet: str, owner=Depends(identity)):
        return record_list(pet, owner, 'workout')

    @app.get('/pets/{pet}/food/records')
    @app.get('/pets/{pet}/meals')
    def meals(pet: str, owner=Depends(identity)):
        return record_list(pet, owner, 'meal')

    @app.get('/pets/{pet}/activities')
    def legacy_records(pet: str, owner=Depends(identity)):
        with db.connect() as c:
            service.owned(c, owner, pet)
            rows = c.execute("SELECT id,revision,occurred_at,payload FROM sources WHERE pet_id=%s AND kind='activity' AND valid ORDER BY occurred_at DESC,id LIMIT 100", (pet,)).fetchall()
        return {'records': rows, 'activities': rows, 'limit': 100, 'compatibility': 'shared_sources_v2.2'}

    @app.post('/pets/{pet}/activities')
    def legacy_activity(pet: str, body: LegacyActivity, owner=Depends(identity)):
        if body.kind == 'walk' and body.unit == 'steps':
            return workout(pet, Workout(event_id=body.event_id, revision=body.revision, occurred_at=body.occurred_at,
                                      source=body.source, synthetic=body.synthetic, workout_type='walking', actual=body.amount, unit='steps'), owner)
        if body.kind == 'food' and body.unit == 'serving':
            # Legacy serving counts do not prove a measured food quantity or nutrition.
            return meal(pet, Meal(event_id=body.event_id, revision=body.revision, occurred_at=body.occurred_at, source=body.source,
                                  synthetic=body.synthetic, food_name=body.label, meal_type='snack', confirmed=body.confirmed), owner)
        raise HTTPException(422, 'Legacy kind/unit mismatch')

    @app.get('/pets/{pet}/quests')
    def quests(pet: str, owner=Depends(identity)):
        timestamp = now()
        day = rules._day(timestamp)
        with db.connect() as c:
            state, _ = service.refresh(c, service.owned(c, owner, pet, True), timestamp, settings.chat_available(owner))
            # Current slots and actionable optional offers must survive a long
            # history. Proposals have no period_start; NULLS LAST hid all of
            # them once a pet accumulated 100 basic quest records.
            rows = c.execute("""SELECT * FROM quest_offers WHERE pet_id=%s
                ORDER BY CASE
                    WHEN (slot IN ('easy','medium') AND period_start=%s)
                         OR (slot='weekly' AND period_start=%s) THEN 0
                    WHEN is_proposal AND status IN ('offered','active','accepted')
                         AND NOT excluded AND cancelled_at IS NULL THEN 1
                    ELSE 2 END,
                    coalesce(shown_at,created_at) DESC,period_start DESC NULLS LAST,id
                LIMIT 100""", (pet, day, rules._monday(day))).fetchall()
        return {'quests': rows, 'offers': rows, 'state_version': state['state_version'], 'reward_balance': state['coin'],
                'current_day': day.isoformat(), 'current_week_start': rules._monday(day).isoformat()}

    @app.post('/pets/{pet}/quests/{offer_id}/decision')
    def decision(pet: str, offer_id: str, body: Decision, owner=Depends(identity)):
        from .quests import quest_decision
        with db.connect() as c:
            p = service.owned(c, owner, pet, True)
            result = quest_decision(c, p, offer_id, body.decision, now())
            state, _ = service.refresh(c, p, now(), settings.chat_available(owner))
        return dict(result, state_version=state['state_version'])

    @app.post('/pets/{pet}/chat-session')
    def session(pet: str, body: Session, owner=Depends(identity)):
        with db.connect() as c:
            service.owned(c, owner, pet)
            c.execute('INSERT INTO common_chat_sessions(pet_id,session_id,active,expires_at) VALUES(%s,%s,%s,%s) ON CONFLICT(pet_id,session_id) DO UPDATE SET active=excluded.active,expires_at=excluded.expires_at',
                      (pet, body.session_id, body.active, now() + timedelta(minutes=5)))
        available = settings.ai_mode != 'disabled' and (settings.ai_mode != 'mock' or owner in settings.test_owners)
        return {'active': body.active, 'ready': bool(body.active and available), 'status': 'active' if body.active else 'closed',
                'session_id': body.session_id, 'ai_mode': settings.ai_mode, 'local_model_loaded': False, 'heartbeat_timeout_seconds': 300}

    @app.post('/pets/{pet}/chat-session/heartbeat')
    def heartbeat(pet: str, body: Session, owner=Depends(identity)):
        with db.connect() as c:
            service.owned(c, owner, pet)
            row = c.execute('UPDATE common_chat_sessions SET expires_at=%s WHERE pet_id=%s AND session_id=%s AND active AND expires_at>%s RETURNING session_id',
                            (now() + timedelta(minutes=5), pet, body.session_id, now())).fetchone()
            if not row:
                raise HTTPException(409, 'Conversation session is not active')
        return {'active': True, 'ready': settings.ai_mode != 'disabled' and (settings.ai_mode != 'mock' or owner in settings.test_owners), 'session_id': body.session_id}

    @app.post('/pets/{pet}/chat')
    def chat(pet: str, body: Chat, owner=Depends(identity)):
        control_action = ('stop_7_days' if re.search(r'제안\s*(?:을\s*)?(?:중단|그만)|추천\s*(?:을\s*)?그만', body.text) else
                          'rest_today' if re.search(r'쉬고\s*싶|오늘\s*(?:은\s*)?쉴', body.text) else
                          'resume' if re.search(r'제안\s*(?:을\s*)?(?:재개|다시)|다시\s*제안', body.text) else None)
        is_test = db.ready()['environment'] == 'test' if control_action else ai(owner)
        key = service.fingerprint({'text': body.text})
        lease_token = uuid.uuid4().hex
        with db.connect() as c:
            p = service.owned(c, owner, pet, True)
            prior = c.execute('SELECT * FROM requests WHERE pet_id=%s AND id=%s', (pet, body.request_id)).fetchone()
            if prior:
                if prior['fingerprint'] != key:
                    raise HTTPException(409, 'Request ID content conflict')
                if prior['status'] == 'done':
                    return prior['result']
                if prior['status'] == 'invalidated':
                    raise HTTPException(410, 'Request was invalidated by source deletion/correction')
                if prior['status'] == 'running' and prior.get('lease_until') and prior['lease_until'] > now():
                    raise HTTPException(409, 'Request is in progress')
            state, _ = service.refresh(c, p, now(), settings.chat_available(owner))
            if body.state_version is not None and body.state_version > state['state_version']:
                raise HTTPException(409, 'State version is from another server or future state')
            started = prior['started_at'] if prior else now()
            c.execute("INSERT INTO requests(pet_id,id,fingerprint,status,started_at,lease_until,lease_token) VALUES(%s,%s,%s,'running',%s,%s,%s) ON CONFLICT(pet_id,id) DO UPDATE SET status='running',lease_until=excluded.lease_until,lease_token=excluded.lease_token", (pet, body.request_id, key, started, now() + timedelta(seconds=max(60, settings.ai_timeout * 3)), lease_token))
            memory_rows = c.execute('SELECT m.id,m.content,m.source_id,m.source_revision FROM memories m JOIN sources s ON s.pet_id=m.pet_id AND s.id=m.source_id WHERE m.pet_id=%s AND m.valid AND s.valid AND s.revision=m.source_revision AND m.embedding_model=%s ORDER BY m.created_at DESC LIMIT 3', (pet, gateway.space)).fetchall()
            c.execute('UPDATE requests SET dependency_source_ids=%s,dependency_memory_ids=%s WHERE pet_id=%s AND id=%s',
                      (Jsonb([r['source_id'] for r in memory_rows]), Jsonb([r['id'] for r in memory_rows]), pet, body.request_id))
            recent = c.execute('SELECT speech,source_id FROM exchanges WHERE pet_id=%s AND valid ORDER BY created_at DESC LIMIT 6', (pet,)).fetchall()
            context = {'state': state, 'personality': {k: state[k] for k in ('activity', 'affinity', 'initiative')}, 'settings': p['settings'], 'memories': memory_rows, 'recent': recent,
                       'classification_policy': {'target_priority': ['direct_character_expression', 'actual_proposal_decision', 'exercise', 'food', 'other'],
                       'exercise_complaints_are_not_character_dislike': True, 'proposal_requires_valid_visible_id': True, 'never_invent_memory_or_exercise_completion': True}}
            frozen_input = prior.get('ai_input') if prior else None
            if frozen_input:
                context = frozen_input['context']
                state = context['state']
                memory_rows = context['memories']
                recent = context['recent']
            else:
                frozen_input = {'text': body.text, 'context': context}
            dependencies = {r['source_id'] for r in memory_rows} | {r['source_id'] for r in recent}
            # Earlier cached replies may depend on older user sources through their own context.
            if dependencies:
                dependencies.update(source for row in c.execute('SELECT r.dependency_source_ids FROM requests r JOIN exchanges e ON e.pet_id=r.pet_id AND e.request_id=r.id WHERE e.pet_id=%s AND e.source_id=ANY(%s::text[])', (pet, list(dependencies))) for source in row['dependency_source_ids'])
            c.execute('UPDATE requests SET ai_input=%s,dependency_source_ids=%s,dependency_memory_ids=%s WHERE pet_id=%s AND id=%s',
                      (Jsonb(frozen_input), Jsonb(sorted(dependencies)), Jsonb([r['id'] for r in memory_rows]), pet, body.request_id))
        try:
            if control_action:
                speech = {'rest_today': '오늘은 쉬는 날로 설정했어요. 오늘이 끝날 때까지 제안을 멈출게요.',
                          'stop_7_days': '제안을 7일 동안 중단했어요. 원하면 직접 다시 켤 수 있어요.',
                          'resume': '제안을 다시 활성화했어요. 오늘 휴식 설정은 유지해요.'}[control_action]
                result = {'speech': speech, 'emotion': 'neutral', 'animation': 'idle', 'memory_ids': [],
                          'classification': {'target': 'other', 'sentiment': 'neutral', 'motivation': 'neutral', 'character_affection': 'neutral', 'acceptance': 'none', 'confidence': 0}}
                provenance = 'server_rule'
            else:
                result, provenance = gateway.call('chat', body.request_id, pet, frozen_input, owner, is_test)
            with db.connect() as c:
                p = service.owned(c, owner, pet, True)
                request_row = c.execute('SELECT * FROM requests WHERE pet_id=%s AND id=%s FOR UPDATE', (pet, body.request_id)).fetchone()
                if request_row['status'] == 'done':
                    return request_row['result']
                if request_row['status'] != 'running':
                    raise HTTPException(410, 'Request invalidated while AI was running')
                if request_row['lease_token'] != lease_token:
                    raise HTTPException(409, 'Request claim changed; retry the same ID')
                if control_action:
                    from .quests import set_proposal_control
                    set_proposal_control(c, pet, control_action, now())
                cls = result['classification']
                proposal_id = cls.get('proposal_id')
                proposal = c.execute('SELECT * FROM quest_offers WHERE pet_id=%s AND id=%s AND is_proposal AND shown_at>=%s AND expires_at>=%s AND NOT excluded',
                                     (pet, proposal_id, now() - timedelta(hours=24), now())).fetchone() if proposal_id else None
                cls['proposal_valid'] = bool(proposal)
                if cls['target'] == 'proposal' and not proposal:
                    cls['acceptance'] = 'none'
                if proposal and cls['confidence'] >= 0.60 and cls['acceptance'] in ('accept', 'reject'):
                    from .quests import quest_decision
                    quest_decision(c, p, proposal_id, cls['acceptance'], now())
                allowed_memories = {r['id'] for r in memory_rows}
                if not set(result['memory_ids']).issubset(allowed_memories):
                    raise AIUnavailable('ai_fabricated_memory_reference')
                payload = {'text': body.text, 'normal': True, 'classification': cls, 'proposal_valid': bool(proposal),
                           'actual_memory_reference': bool(result['memory_ids']), 'response_provenance': provenance}
                raw = dict(event_id='message:' + body.request_id, revision=1, occurred_at=started, source='user', synthetic=provenance == 'synthetic', text=body.text)
                applied = service.store_event(c, p, 'chat', raw, payload, now(), settings)
                output = {'schema_version': 'healthmon.v1', 'request_id': body.request_id,
                          'response': {k: v for k, v in result.items() if k != 'classification'}, 'state_used': state, 'state_after': applied['state'],
                          'state_version': applied['state_version'], 'execution': {}, 'metrics': {'fallback': False, 'synthetic': provenance == 'synthetic', 'backend': settings.ai_mode}, 'provenance': provenance}
                output['response'].update(action={'type': 'none', 'target_id': None}, personality_update=None)
                c.execute('INSERT INTO exchanges(pet_id,request_id,source_id,speech,memory_ids,state_used,state_after) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                          (pet, body.request_id, raw['event_id'], result['speech'], Jsonb(result['memory_ids']), Jsonb(state), Jsonb(applied['state'])))
                c.execute("UPDATE requests SET status='done',result=%s WHERE pet_id=%s AND id=%s", (Jsonb(output), pet, body.request_id))
            return output
        except Exception:
            with db.connect() as c:
                c.execute("UPDATE requests SET status='failed' WHERE pet_id=%s AND id=%s AND status='running' AND lease_token=%s", (pet, body.request_id, lease_token))
            raise

    @app.post('/pets/{pet}/food/analyze')
    async def analyze_food(pet: str, request: Request, x_request_id: str | None = Header(default=None), owner=Depends(identity)):
        is_test = ai(owner)
        with db.connect() as c:
            service.owned(c, owner, pet)
        image = bytearray()
        async for chunk in request.stream():
            image.extend(chunk)
            if len(image) > 12 * 1024 * 1024:
                raise HTTPException(413, 'Image exceeds 12 MiB')
        mime = 'image/jpeg' if image.startswith(b'\xff\xd8\xff') else 'image/png' if image.startswith(b'\x89PNG\r\n\x1a\n') else None
        if mime is None:
            raise HTTPException(422, 'Send raw JPEG or PNG bytes')
        ident = x_request_id or uuid.uuid4().hex
        if not 8 <= len(ident) <= 100:
            raise HTTPException(422, 'Invalid request ID')
        image_hash = service.fingerprint({'image': base64.b64encode(image).decode()})
        with db.connect() as c:
            previous = c.execute('SELECT * FROM food_analyses WHERE id=%s AND pet_id=%s', (ident, pet)).fetchone()
            if previous:
                if previous.get('erased_at') or previous['result'].get('_privacy_erased'):
                    raise HTTPException(410, 'Food analysis was erased')
                if previous['result'].get('image_hash') != image_hash:
                    raise HTTPException(409, 'Analysis ID content conflict')
                return previous['result']
        result, provenance = await asyncio.to_thread(gateway.call, 'food', ident, pet,
                                                     {'image_base64': base64.b64encode(image).decode(), 'content_type': mime}, owner, is_test)
        candidates = []
        for index, item in enumerate(result['candidates']):
            candidates.append({'candidate_id': index, 'food': item['food'], 'confidence': item['confidence'],
                               'per_100g': {k: {'available': v is not None, 'value': v} for k, v in item['per_100g'].items()},
                               'has_estimated_grams': item['estimated_grams'] is not None, 'estimated_grams': item['estimated_grams'], 'weight_warning': ''})
        output = {'schema_version': 'healthmon.food.v1', 'analysis_id': ident, 'backend': settings.ai_mode, 'provenance': provenance,
                  'synthetic': provenance == 'synthetic', 'candidates': candidates, 'consumption_confirmed': False, 'image_hash': image_hash}
        with db.connect() as c:
            service.owned(c, owner, pet, True)
            prior = c.execute('SELECT pet_id,result FROM food_analyses WHERE id=%s', (ident,)).fetchone()
            if prior:
                if prior['result'].get('_privacy_erased'):
                    raise HTTPException(410, 'Food analysis was erased')
                if prior['pet_id'] != pet or prior['result']['image_hash'] != image_hash:
                    raise HTTPException(409, 'Analysis ID already exists')
                return prior['result']
            c.execute('INSERT INTO food_analyses(id,pet_id,result) VALUES(%s,%s,%s)', (ident, pet, Jsonb(output)))
        return output

    @app.post('/pets/{pet}/food/confirm')
    def confirm_food(pet: str, body: ConfirmFood, owner=Depends(identity)):
        with db.connect() as c:
            p = service.owned(c, owner, pet, True)
            analysis = c.execute('SELECT * FROM food_analyses WHERE id=%s AND pet_id=%s FOR UPDATE', (body.analysis_id, pet)).fetchone()
            if not analysis:
                raise HTTPException(404, 'Food analysis not found')
            if analysis.get('erased_at') or analysis['result'].get('_privacy_erased'):
                raise HTTPException(410, 'Food analysis was erased')
            if analysis['confirmation']:
                original = c.execute('SELECT valid FROM sources WHERE pet_id=%s AND id=%s', (pet, analysis['confirmation']['source_id'])).fetchone()
                if not original or not original['valid']:
                    raise HTTPException(410, 'Confirmed food record was erased')
                prior_input = dict(analysis['confirmation']['input'])
                prior_input.setdefault('synthetic', False)  # Earlier confirmations predate this optional fixture flag.
                if prior_input != body.model_dump():
                    raise HTTPException(409, 'Food was already confirmed with different contents')
                return dict(analysis['confirmation'], duplicate=True)
            candidates = analysis['result']['candidates']
            if body.candidate_id >= len(candidates):
                raise HTTPException(422, 'Choose a returned candidate')
            candidate = candidates[body.candidate_id]
            nutrients = {k: v['value'] * body.grams / 100 if v['available'] and body.grams is not None else None for k, v in candidate['per_100g'].items()}
            nutrients['vegetable_fruit_g'] = body.vegetable_fruit_g
            event_id = body.event_id or ('food-image-' + analysis['result']['image_hash'])
            existing = c.execute('SELECT occurred_at,payload FROM sources WHERE pet_id=%s AND id=%s', (pet, event_id)).fetchone()
            original_analysis = existing['payload'].get('data', {}).get('analysis_id') if existing else None
            record = Meal(event_id=event_id, revision=body.revision, occurred_at=existing['occurred_at'] if existing else now(), food_name=candidate['food'], meal_type=body.meal_type,
                          confirmed=True, grams=body.grams, quantity_confirmed=body.grams is not None,
                          carbohydrate_g=nutrients.get('carbohydrate_g'), protein_g=nutrients.get('protein_g'), fat_g=nutrients.get('fat_g'),
                          vegetable_fruit_g=body.vegetable_fruit_g, kcal=nutrients.get('energy_kcal'), kcal_reconfirmed=body.kcal_reconfirmed,
                          analysis_id=original_analysis or body.analysis_id, synthetic=body.synthetic or analysis['result']['synthetic'])
            applied = service.store_event(c, p, 'meal', record.model_dump(), record.model_dump(mode='json'), now(), settings)
            output = dict(applied, input=body.model_dump(), analysis_id=body.analysis_id, source_id=record.event_id, candidate_id=body.candidate_id, grams=body.grams,
                          record={'food': record.food_name, 'grams': body.grams, 'nutrition': {k: {'available': v is not None, 'value': v} for k, v in nutrients.items()}})
            c.execute('UPDATE food_analyses SET confirmation=%s WHERE id=%s', (Jsonb(output), body.analysis_id))
        return output

    @app.post('/pets/{pet}/memories')
    def remember(pet: str, body: Memory, owner=Depends(identity)):
        is_test = ai(owner)
        with db.connect() as c:
            service.owned(c, owner, pet)
            source = c.execute('SELECT * FROM sources WHERE pet_id=%s AND id=%s AND valid AND revision=%s', (pet, body.source_id, body.revision)).fetchone()
            if not source:
                raise HTTPException(409, 'Valid source revision required')
            text = source['payload'].get('data', {}).get('text') or source['payload'].get('text')
            if not text:
                raise HTTPException(422, 'Memory source must be a user message')
        ident = service.fingerprint({'source': body.source_id, 'revision': body.revision, 'slot': body.slot})[:32]
        embedded, provenance = gateway.call('embedding', ident, pet, {'text': text}, owner, is_test)
        with db.connect() as c:
            service.owned(c, owner, pet, True)
            current = c.execute('SELECT revision,valid FROM sources WHERE pet_id=%s AND id=%s', (pet, body.source_id)).fetchone()
            if not current or not current['valid'] or current['revision'] != body.revision:
                raise HTTPException(409, 'Source changed during embedding')
            space = f"{embedded['model_id']}:{embedded['model_version']}:{embedded['dimension']}"
            c.execute('INSERT INTO memories(pet_id,id,source_id,source_revision,slot,content,embedding,embedding_revision,embedding_model,synthetic) VALUES(%s,%s,%s,%s,%s,%s,%s::vector,%s,%s,%s) ON CONFLICT(pet_id,id) DO UPDATE SET valid=true,embedding=excluded.embedding,embedding_model=excluded.embedding_model',
                      (pet, ident, body.source_id, body.revision, body.slot, text, json.dumps(embedded['vector']), str(body.revision), space, provenance == 'synthetic'))
        return {'memory_id': ident, 'source_id': body.source_id, 'revision': body.revision, 'provenance': provenance}

    @app.get('/pets/{pet}/memories')
    def memories(pet: str, query: str = Query(min_length=1, max_length=1500), owner=Depends(identity)):
        is_test = ai(owner)
        with db.connect() as c:
            service.owned(c, owner, pet)
        embedded, provenance = gateway.call('embedding', service.fingerprint({'query': query})[:32], pet, {'text': query}, owner, is_test)
        space = f"{embedded['model_id']}:{embedded['model_version']}:{embedded['dimension']}"
        with db.connect() as c:
            service.owned(c, owner, pet)
            rows = c.execute('SELECT m.id,m.content,m.source_id,m.source_revision,1-(m.embedding <=> %s::vector) AS similarity FROM memories m JOIN sources s ON s.pet_id=m.pet_id AND s.id=m.source_id WHERE m.pet_id=%s AND m.valid AND s.valid AND s.revision=m.source_revision AND m.embedding_model=%s AND m.synthetic=%s ORDER BY m.embedding <=> %s::vector LIMIT 3',
                             (json.dumps(embedded['vector']), pet, space, provenance == 'synthetic', json.dumps(embedded['vector']))).fetchall()
        return {'memories': rows, 'provenance': provenance}

    @app.post('/pets/{pet}/evolutions')
    def evolution(pet: str, body: Evolution, owner=Depends(identity)):
        from .worker import enqueue_evolution, job_view
        with db.connect() as c:
            p = service.owned(c, owner, pet, True)
            state, _ = service.refresh(c, p, now(), settings.chat_available(owner))
            job = enqueue_evolution(c, p, state, body.request_id, now())
        return job_view(job, state['state_version'])

    @app.get('/pets/{pet}/evolutions/{job_id}')
    def evolution_job(pet: str, job_id: str, owner=Depends(identity)):
        from .worker import job_view
        with db.connect() as c:
            p = service.owned(c, owner, pet)
            if job_id.startswith('starter-'):
                from . import starters
                initial=starters.manifest(c,p,job_id)
                if not initial:raise HTTPException(404,'Starter model not bound to this pet')
                return initial
            job = c.execute("SELECT * FROM ai_jobs WHERE pet_id=%s AND id=%s AND kind='evolution'", (pet, job_id)).fetchone()
            if not job:
                raise HTTPException(404, 'Job not found')
        return job_view(job, p['version'])

    @app.get('/pets/{pet}/assets/{job_id}')
    def asset(pet: str, job_id: str, owner=Depends(identity)):
        with db.connect() as c:
            service.owned(c, owner, pet)
            row = c.execute('SELECT data,sha256 FROM model_assets WHERE pet_id=%s AND job_id=%s', (pet, job_id)).fetchone()
            if not row and job_id.startswith('starter-'):
                from . import starters
                row=starters.asset(c,pet,job_id)
            if not row:
                raise HTTPException(404, 'Published asset not found')
        return Response(bytes(row['data']), media_type='model/gltf-binary', headers={'ETag': row['sha256'], 'Cache-Control': 'private, no-cache'})

    @app.post('/pets/{pet}/proposals')
    def new_proposal(pet: str, body: Proposal, owner=Depends(identity)):
        from .quests import create_proposal
        if body.candidate == 'chat1' and not settings.chat_available(owner):
            raise HTTPException(409, 'Chat proposal is unavailable')
        with db.connect() as c:
            p = service.owned(c, owner, pet, True)
            state, _ = service.refresh(c, p, now(), settings.chat_available(owner))
            return create_proposal(c, p, body.model_dump(), now(), state)

    @app.post('/pets/{pet}/activity-suggestions/{event_id}')
    def activity_suggestion(pet: str, event_id: str, revision: int, owner=Depends(identity)):
        is_test = ai(owner)
        with db.connect() as c:
            p = service.owned(c, owner, pet, True)
            source = c.execute("SELECT * FROM sources WHERE pet_id=%s AND id=%s AND valid AND revision=%s", (pet, event_id, revision)).fetchone()
            if not source:
                raise HTTPException(409, 'Valid activity source revision required')
            state, _ = service.refresh(c, p, now(), settings.chat_available(owner))
            context = {'state': state, 'event': source['payload'], 'personality': {k: state[k] for k in ('activity', 'affinity', 'initiative')}}
        ident = 'suggestion-' + service.fingerprint({'pet': pet, 'event': event_id, 'revision': revision})[:32]
        result, provenance = gateway.call('chat', ident, pet, {'text': '기록된 활동을 사실대로 짧게 안내해 주세요.', 'context': context}, owner, is_test)
        return {'schema_version': 'healthmon.v1', 'request_id': ident, 'response': dict({k: v for k, v in result.items() if k != 'classification'},
                action={'type': 'none', 'target_id': None}, personality_update=None), 'state_version': state['state_version'], 'provenance': provenance,
                'metrics': {'fallback': False, 'synthetic': provenance == 'synthetic'}, 'execution': {}}

    @app.post('/pets/{pet}/proposals/{offer_id}/shown')
    def shown_proposal(pet: str, offer_id: str, owner=Depends(identity)):
        from .quests import mark_proposal_shown
        with db.connect() as c:
            p = service.owned(c, owner, pet, True)
            state, _ = service.refresh(c, p, now(), settings.chat_available(owner))
            return mark_proposal_shown(c, p, offer_id, now(), state)

    @app.post('/pets/{pet}/proposal-control')
    def control_proposals(pet: str, body: ProposalControl, owner=Depends(identity)):
        from .quests import set_proposal_control
        with db.connect() as c:
            service.owned(c, owner, pet, True)
            return set_proposal_control(c, pet, {'rest': 'rest_today', 'stop': 'stop_7_days', 'resume': 'resume'}[body.action], now())

    @app.delete('/pets/{pet}/sources/{source_id}')
    def delete_source(pet: str, source_id: str, expected_revision: int, owner=Depends(identity)):
        from .privacy import delete_source as erase
        with db.connect() as c:
            return erase(c, service.owned(c, owner, pet, True), source_id, expected_revision, now(), settings)

    @app.delete('/pets/{pet}/memories/{memory_id}')
    def delete_memory(pet: str, memory_id: str, expected_revision: int, owner=Depends(identity)):
        from .privacy import delete_memory as erase
        with db.connect() as c:
            p = service.owned(c, owner, pet, True)
            row = c.execute('SELECT source_revision FROM memories WHERE pet_id=%s AND id=%s', (pet, memory_id)).fetchone()
            if not row:
                raise HTTPException(404, 'Memory not found')
            if row['source_revision'] != expected_revision:
                raise HTTPException(409, 'Memory revision conflict')
            result = erase(c, p, memory_id, now())
            state, _ = service.refresh(c, p, now(), settings.chat_available(owner), True, 'memory_erased')
            return dict(result, state_version=state['state_version'])

    @app.delete('/pets/{pet}')
    def delete_pet(pet: str, owner=Depends(identity)):
        from .privacy import delete_pet as erase
        with db.connect() as c:
            return erase(c, service.owned(c, owner, pet, True), now())

    @app.patch('/pets/{pet}/sources/{source_id}')
    def edit_source(pet: str, source_id: str, body: SourceEdit, owner=Depends(identity)):
        with db.connect() as c:
            p = service.owned(c, owner, pet, True)
            original = c.execute('SELECT * FROM sources WHERE pet_id=%s AND id=%s AND valid', (pet, source_id)).fetchone()
            if not original:
                raise HTTPException(404, 'Source not found')
            if original['kind'] != 'message':
                raise HTTPException(422, 'Use the versioned workout or meal endpoint')
            if original['revision'] != body.expected_revision:
                raise HTTPException(409, 'Source revision conflict')
            raw = dict(event_id=source_id, revision=body.expected_revision + 1, occurred_at=original['occurred_at'],
                       source='user', synthetic=original['synthetic'], text=body.text)
            return service.store_event(c, p, 'chat', raw, {'text': body.text, 'normal': False, 'classification': None}, now(), settings)

    @app.get('/pets/{pet}/messages')
    def messages(pet: str, limit: int = Query(default=30, ge=1, le=100), owner=Depends(identity)):
        with db.connect() as c:
            p = service.owned(c, owner, pet)
            rows = c.execute("SELECT s.id AS source_id,s.revision AS source_revision,s.occurred_at AS created_at,coalesce(s.payload->'data'->>'text',s.payload->>'text') AS text,e.request_id,e.speech,r.result FROM sources s LEFT JOIN exchanges e ON e.pet_id=s.pet_id AND e.source_id=s.id AND e.valid LEFT JOIN requests r ON r.pet_id=e.pet_id AND r.id=e.request_id AND r.status='done' WHERE s.pet_id=%s AND s.kind='message' AND s.valid ORDER BY s.occurred_at DESC,s.id DESC LIMIT %s", (pet, limit + 1)).fetchall()
        result = []
        for row in reversed(rows[:limit]):
            cached = row['result'] or {}
            result.append({'request_id': row['request_id'] or row['source_id'].removeprefix('message:'), 'source_id': row['source_id'],
                           'source_revision': row['source_revision'], 'user': row['text'], 'assistant': row['speech'] if cached else None,
                           'created_at': row['created_at'], 'response': cached.get('response'), 'execution': cached.get('execution', {}), 'metrics': cached.get('metrics')})
        return {'pet_id': pet, 'state_version': p['version'], 'limit': limit, 'has_more': len(rows) > limit, 'messages': result}

    return app
