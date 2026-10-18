"""Routes integrated into the existing loopback-only Persona Lab application."""
import hashlib
import hmac
import json
import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import Field
from .character_lab_schema import (Strict, CharacterState, Session, Run, ConversationLabel, FoodLabel, RULES, canonical_json)
from .character_lab_engine import execute, fresh
from .character_lab_presets import PRESETS, preview
from .character_lab_models import (ConversationAnalyzer, FoodAnalyzer, PersonaResponder,
                                   ANALYZER_VERSION, RESPONDER_VERSION, response_context)
from .character_lab_store import CharacterLabStore, Conflict
from .character_lab_quests import catalog_candidate_to_payload, mini_quest_id, quest_view
from .persona_generation import Generation, Memory
from .contracts import ModelOutput


def session_digest(session):
    """Bind offers to semantic evidence/state, excluding replay audit timestamps."""
    value = Session.model_validate(session).model_dump(mode='json')
    value.pop('logs')
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def validate_offer_goal_numbers(speech, candidate):
    """Fail closed on explicit conflicting recommendation quantities.

    Missing spoken quantities are allowed: the catalog action owns the goal.
    Multiple differing quantities require review rather than guessing which
    describes the recommendation. This never creates an action from dialogue.
    """
    goal = candidate['goal']
    expected_unit = {'steps': 'step', 'minutes': 'minute'}.get(goal.get('unit'))
    if expected_unit is None:
        return
    recommends = re.search(r'추천|제안|권유|같이|함께|산책|스트레칭|걷(?:자|기|는|고)|걸어|'
                           r'해\s*보|해볼|해보|어때|어떨|도전|시작', speech)
    if not recommends:
        return
    quantities = [(float(number.replace(',', '')), 'minute' if unit == '분' else 'step')
                  for number, unit in re.findall(r'(\d[\d,]*(?:\.\d+)?)\s*(걸음|보|분)', speech)]
    if quantities and any(unit != expected_unit or amount != goal['target'] for amount, unit in quantities):
        raise ValueError('대사의 걸음 수·시간이 선택된 퀘스트 목표와 다르거나 여러 목표가 섞여 있습니다. '
                         '응답을 검수하고 다시 생성하세요. 퀘스트는 생성되지 않았습니다.')


class Analyze(Strict):
    text: str = Field(min_length=1, max_length=1500)
    mode: Literal['qwen', 'dummy', 'manual'] = 'qwen'
    label: ConversationLabel | None = None
    generation: Generation = Field(default_factory=Generation)


class FoodAnalyze(Strict):
    text: str = Field(min_length=1, max_length=1500)
    mode: Literal['qwen', 'dummy'] = 'qwen'
    generation: Generation = Field(default_factory=Generation)


class Respond(Strict):
    text: str = Field(min_length=1, max_length=1500)
    session: Session = Field(default_factory=Session)
    a: CharacterState | None = None
    b: CharacterState | None = None
    memory: list[Memory] = Field(default_factory=list, max_length=3)
    mode: Literal['qwen', 'dummy'] = 'qwen'
    generation: Generation = Field(default_factory=Generation)
    speech_level: Literal['casual', 'formal'] = 'casual'


class Review(Strict):
    draft: dict
    signature: str = Field(max_length=128)
    status: Literal['pending', 'approved', 'corrected', 'excluded'] = 'pending'
    corrected_label: ConversationLabel | None = None
    corrected_response: str | None = Field(default=None, min_length=1, max_length=2000)
    reviewer_note: str = Field(default='', max_length=2000)
    expected_revision: int | None = Field(default=None, ge=0)


class QuestOffer(Strict):
    draft: dict
    signature: str = Field(min_length=64, max_length=64, pattern=r'^[0-9a-f]{64}$')
    event_id: str = Field(min_length=1, max_length=100)
    session: Session | None = None
    session_id: str | None = Field(default=None, max_length=100)
    expected_revision: int | None = Field(default=None, ge=0)
    dry_run: bool = True


class Preset(Strict):
    name: str
    session: Session | None = None


def install(application):
    router = APIRouter(prefix='/dev/character-lab')
    store = CharacterLabStore(application.state.store.path)
    runtime = application.state.runtime
    secret = secrets.token_bytes(32)
    application.state.character_lab_store = store

    def signature(draft):
        return hmac.new(secret, canonical_json(draft).encode(), hashlib.sha256).hexdigest()

    def draft(kind, text, result, **context):
        row = {'id': 'creview-'+uuid.uuid4().hex, 'kind': kind, 'text': text,
               'created_at': datetime.now(timezone.utc).isoformat(), 'reviewer_status': 'pending',
               'rule_version': RULES['version'], **result, **context}
        return {'draft': row, 'signature': signature(row)}

    def run(body):
        try:
            commands = [x.model_dump(mode='json') for x in body.commands]
            if not body.dry_run:
                if not body.session_id or body.session is not None:
                    raise ValueError('Commit requires an explicit saved test session_id and revision; posted session snapshots cannot overwrite saved data')
                return store.run(body.session_id, commands, body.expected_revision)
            if body.session_id:
                if body.session is not None:
                    raise ValueError('Choose either saved session_id or preview snapshot')
                existing = store.read(body.session_id)
                result = execute(existing['session'], commands)
                result.update(target=body.session_id, revision=existing['revision'], session_id=body.session_id)
                return result
            return execute(body.session.model_dump(mode='json') if body.session else fresh(), commands)
        except Conflict as error:
            raise HTTPException(409, str(error))
        except ValueError as error:
            raise HTTPException(422, str(error))

    @router.get('/state')
    def state(session_id: str | None = None):
        if session_id:
            try:
                result = store.read(session_id)
                result['session'] = Session.model_validate(result['session']).model_dump(mode='json')
                result['quests'] = quest_view(result['session'])
                return result
            except ValueError as error:
                raise HTTPException(404, str(error))
        session = fresh()
        return {'session': session, 'quests': quest_view(session), 'dry_run': True, 'database_write': False,
                'field_aliases': {'Affinity': 'affection', 'Activity': 'activity', 'Initiative': 'initiative',
                                  'legacy confidence': 'confidence', 'model reliability': 'analysis_confidence'},
                'rules': RULES}

    @router.post('/sessions')
    def create_session(body: CharacterState):
        result = store.create(body.model_dump(mode='json'))
        result['quests'] = quest_view(result['session'])
        return result

    @router.post('/run')
    def batch(body: Run):
        return run(body)

    for path, allowed in {'state': 'manual_override', 'exercise': 'exercise', 'food': 'food',
                          'conversation': 'conversation', 'quest': 'quest', 'quest/tick': 'quest_tick',
                          'time': 'time', 'evolution': 'evolution'}.items():
        def make_endpoint(kind):
            def endpoint(body: Run):
                if any(x.kind != kind for x in body.commands):
                    raise HTTPException(422, 'Use /run for mixed event batches')
                return run(body)
            return endpoint
        router.add_api_route('/'+path, make_endpoint(allowed), methods=['POST'], name='character_'+path)

    @router.post('/conversation/analyze')
    def analyze(body: Analyze):
        try:
            if body.mode == 'manual':
                if body.label is None:
                    raise ValueError('Manual mode requires an explicit administrator label')
                result = {'prediction': body.label.model_dump(), 'model_identifier': 'manual-admin-label',
                          'prompt_version': ANALYZER_VERSION, 'prompt': [], 'raw_model_output': '',
                          'output_origin': 'manual', 'is_real_model': False, 'review_required': True}
            else:
                if body.label is not None:
                    raise ValueError('Labels are only accepted in explicitly manual mode')
                result = ConversationAnalyzer(runtime).analyze(body.text, body.mode, body.generation.model_dump())
            return {**result, 'review': draft('analyzer', body.text, result), 'dry_run': True, 'database_write': False}
        except ValueError as error:
            raise HTTPException(422, str(error))
        except (RuntimeError, OSError) as error:
            raise HTTPException(503, 'Local Qwen unavailable: '+str(error))

    @router.post('/food/analyze')
    def food_analyze(body: FoodAnalyze):
        try:
            return {**FoodAnalyzer(runtime).analyze(body.text, body.mode, body.generation.model_dump()),
                    'dry_run': True, 'database_write': False}
        except (RuntimeError, OSError) as error:
            raise HTTPException(503, 'Local Qwen unavailable: '+str(error))

    @router.post('/conversation/respond')
    def respond(body: Respond):
        try:
            session = body.session.model_dump(mode='json')
            a = body.a.model_dump(mode='json') if body.a else session['state']
            b = body.b.model_dump(mode='json') if body.b else session['state']
            if a['virtual_test_date'] != session['state']['virtual_test_date'] or b['virtual_test_date'] != a['virtual_test_date']:
                raise ValueError('A/B must share the session virtual date')
            memory = [x.model_dump() for x in body.memory]
            result = PersonaResponder(runtime).compare(session, a, b, body.text, memory,
                            body.generation.model_dump(), body.mode, body.speech_level)
            reviews = {}
            for side in ('a', 'b'):
                output = result['results'][0][side]
                ctx = result['contexts'][side]
                reviews[side] = draft('response', body.text, {
                    'prediction': output['output']['speech'], 'raw_model_output': output['raw_attempts'],
                    'output_origin': output['output_origin'], 'model_identifier': 'qwen3.5-9b:'+str(result['adapter']) if body.mode == 'qwen' else 'dummy-fixed-response',
                    'prompt_version': result['prompt_version'], 'prompt': result['prompts'][side],
                    'response_contract': output['output'],
                    'generation': result['generation'], 'fallback': output['metrics']['fallback']},
                    state=ctx['character_state'], memory=memory,
                    session_digest=session_digest(session), speech_level=body.speech_level,
                    quest_context={'active': ctx['active_quests'], 'candidates': ctx['candidates'], 'agent_policy': ctx['agent_policy']})
            result.update(reviews=reviews, dry_run=True, database_write=False)
            return result
        except ValueError as error:
            raise HTTPException(422, str(error))
        except (RuntimeError, OSError) as error:
            raise HTTPException(503, 'Local Qwen unavailable: '+str(error))

    @router.post('/quest/offer')
    def offer_quest(body: QuestOffer):
        try:
            d = body.draft
            if not hmac.compare_digest(body.signature, signature(d)):
                raise ValueError('Response draft signature invalid')
            if (d.get('kind') != 'response' or d.get('output_origin') != 'qwen'
                    or d.get('fallback') is not False):
                raise ValueError('Only a valid real-model quest offer can become a quest; dummy/fallback outputs cannot execute')
            if d.get('rule_version') != RULES['version'] or d.get('prompt_version') != RESPONDER_VERSION:
                raise ValueError('Response rules changed; generate a new response')
            output = ModelOutput.model_validate(d.get('response_contract'))
            if output.action.type != 'offer_quest':
                raise ValueError('Only structured offer_quest actions create quests; dialogue alone is not an action')
            if body.session_id:
                if body.session is not None:
                    raise ValueError('Choose either saved session_id or preview snapshot')
                if not body.dry_run and body.expected_revision is None:
                    raise ValueError('expected_revision required for explicit test-session writes')
                existing = store.read(body.session_id)
                current = Session.model_validate(existing['session']).model_dump(mode='json')
                if not body.dry_run and existing['revision'] != body.expected_revision:
                    raise Conflict('Saved session changed; reload before committing')
            else:
                if not body.dry_run:
                    raise ValueError('Commit requires an explicit saved test session_id and revision')
                current = body.session.model_dump(mode='json') if body.session else fresh()
            if d.get('session_digest') != session_digest(current):
                raise Conflict('Quest offer is stale: state, date or evidence changed; generate a new response')
            if canonical_json(d.get('state')) != canonical_json(current['state']):
                raise Conflict('Apply the selected A/B character state before generating an executable offer')
            text = d.get('text')
            level = d.get('speech_level')
            if not isinstance(text, str) or level not in ('casual', 'formal'):
                raise ValueError('Incomplete response context; generate a new response')
            memory = [Memory.model_validate(row).model_dump() for row in d.get('memory', [])]
            context = response_context(current, current['state'], text, memory, level)
            offered = next((q for q in d.get('quest_context', {}).get('candidates', [])
                            if q.get('id') == output.action.target_id), None)
            candidate = next((q for q in context['candidates'] if q['id'] == output.action.target_id), None)
            if not candidate or not offered or canonical_json(candidate) != canonical_json(offered):
                raise ValueError('Quest action must identify an exact currently authorized catalog candidate')
            validate_offer_goal_numbers(output.speech, candidate)
            # Validate the complete contract again with authoritative current context.
            from .agent import validate
            validate(output.model_dump_json(), context, text)
            ident = mini_quest_id(candidate['quest_id'], current['state']['virtual_test_date'])
            payload = catalog_candidate_to_payload(candidate, ident, current['state']['virtual_test_date'])
            request = Run(session=body.session, session_id=body.session_id,
                          expected_revision=body.expected_revision, dry_run=body.dry_run,
                          commands=[{'kind': 'quest', 'event_id': body.event_id, 'payload': payload}])
            if body.dry_run:
                # Preview the exact snapshot validated above; a second saved
                # read could otherwise show a different concurrent revision.
                result = execute(current, [command.model_dump(mode='json') for command in request.commands])
                if body.session_id:
                    result.update(target=body.session_id, revision=existing['revision'], session_id=body.session_id)
            else:
                result = run(request)
            result.update(execution={'quest_instance_id': ident, 'catalog_id': candidate['quest_id'],
                                     'status': result['session']['quests'][ident]['status']},
                          command=request.commands[0].model_dump(mode='json'),
                          quests=quest_view(result['session']))
            return result
        except Conflict as error:
            raise HTTPException(409, str(error))
        except ValueError as error:
            raise HTTPException(422, str(error))

    @router.get('/logs')
    def logs(session_id: str):
        try:
            return {'session_id': session_id, 'logs': store.read(session_id)['session']['logs']}
        except ValueError as error:
            raise HTTPException(404, str(error))

    @router.get('/reviews')
    def list_reviews():
        return {'reviews': [{**r, 'signature': signature(r['draft'])} for r in store.reviews()]}

    @router.post('/reviews')
    def save_review(body: Review):
        try:
            if not hmac.compare_digest(body.signature, signature(body.draft)):
                raise ValueError('Draft signature invalid; raw model metadata must remain unchanged. Reload saved reviews after server restart.')
            kind = body.draft['kind']
            if body.status == 'approved' and body.draft['output_origin'] in ('invalid', 'fallback'):
                raise ValueError('Invalid or fallback output needs a corrected target before training export')
            correction = None
            if body.status == 'corrected':
                if kind == 'analyzer':
                    if body.corrected_label is None:
                        raise ValueError('corrected_label is required')
                    correction = body.corrected_label.model_dump()
                else:
                    if body.corrected_response is None or not body.corrected_response.strip():
                        raise ValueError('corrected_response is required')
                    correction = body.corrected_response.strip()
            return store.save_review(body.draft, body.status, correction, body.reviewer_note, body.expected_revision)
        except Conflict as error:
            raise HTTPException(409, str(error))
        except ValueError as error:
            raise HTTPException(422, str(error))

    @router.get('/export')
    def export(kind: Literal['analyzer', 'response']):
        name = 'conversation_analyzer_dataset.jsonl' if kind == 'analyzer' else 'character_response_dataset.jsonl'
        return Response(store.export(kind), media_type='application/x-ndjson',
                        headers={'Content-Disposition': f'attachment; filename="{name}"'})

    @router.get('/presets')
    def presets():
        return {'presets': PRESETS, 'dry_run': True, 'training_data': False}

    @router.post('/presets')
    def preset(body: Preset):
        try:
            return preview(body.name, body.session.model_dump(mode='json') if body.session else None)
        except ValueError as error:
            raise HTTPException(422, str(error))

    application.include_router(router)
