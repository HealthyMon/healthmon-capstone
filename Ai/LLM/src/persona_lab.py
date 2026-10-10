"""Opt-in, loopback-only development application, independent of the legacy DB."""
import copy
import ipaddress
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .persona_runtime import PersonaRuntime, DEFAULT_GENERATION, prepare_context
from .persona_store import LabStore
from .persona_engine import RULES
from .persona_lifestyle import LifestyleInput
from .persona_generation import Generation, Memory

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo('Asia/Seoul')
AXES = ('curiosity', 'affection', 'activity', 'confidence')
PRESETS = {
    'reserved': {'label': '소극적 초기형', 'personality': dict.fromkeys(AXES, 30), 'character_voice': 'default'},
    'warm': {'label': '다정한 안정형', 'personality': dict(zip(AXES, [50, 80, 45, 60])), 'character_voice': 'default'},
    'active': {'label': '활발한 도전형', 'personality': dict(zip(AXES, [70, 55, 85, 75])), 'character_voice': 'default'},
    'curious': {'label': '호기심형', 'personality': dict(zip(AXES, [90, 50, 60, 55])), 'character_voice': 'default'},
    'sassy': {'label': '싸가지형 · 말투만 변경', 'character_voice': 'sassy'},
    'tired': {'label': '지친 상태 · 성격 유지', 'short_term': {'mood': 'tired', 'energy': 20}},
    'proud': {'label': '퀘스트 성공 직후 · 성격 유지', 'short_term': {'mood': 'proud', 'energy': 65}},
}


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Personality(Strict):
    curiosity: float = Field(default=RULES['initial']['curiosity'], ge=0, le=100)
    affection: float = Field(default=RULES['initial']['affection'], ge=0, le=100)
    activity: float = Field(default=RULES['initial']['activity'], ge=0, le=100)
    confidence: float = Field(default=RULES['initial']['confidence'], ge=0, le=100)


class ShortTerm(Strict):
    mood: Literal['neutral', 'happy', 'low', 'tired', 'proud', 'stressed', 'calm', 'content', 'sad'] = RULES['short_term_initial']['mood']
    energy: float = Field(default=RULES['short_term_initial']['energy'], ge=0, le=100)
    recent_motivation: float = Field(default=RULES['short_term_initial']['recent_motivation'], ge=0, le=100)
    recent_stress: float = Field(default=RULES['short_term_initial']['recent_stress'], ge=0, le=100)


class StateInput(Strict):
    personality: Personality = Field(default_factory=Personality)
    short_term: ShortTerm = Field(default_factory=ShortTerm)
    stages: dict[str, Literal['very_low', 'low', 'medium', 'high', 'very_high']] | None = None
    character_voice: Literal['default', 'sassy'] = 'default'


class Preview(Strict):
    a: StateInput = Field(default_factory=StateInput)
    b: StateInput = Field(default_factory=StateInput)
    text: str = Field(default='오늘은 무엇을 해볼까?', min_length=1, max_length=1500)
    mode: Literal['qwen', 'dummy'] = 'qwen'
    repetitions: Literal[1, 5] = 1
    generation: Generation = Field(default_factory=Generation)
    memories: list[Memory] = Field(default_factory=list, max_length=3)
    events: list[dict] = Field(default_factory=list, max_length=2500)
    events_a: list[dict] | None = Field(default=None, max_length=2500)
    events_b: list[dict] | None = Field(default=None, max_length=2500)
    now: datetime = Field(default_factory=lambda: datetime.now(TZ))
    now_a: datetime | None = None
    now_b: datetime | None = None
    speech_level: Literal['formal', 'casual'] = 'casual'

    @field_validator('now', 'now_a', 'now_b')
    @classmethod
    def aware(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError('Timezone required')
        return value


class Simulation(Strict):
    scenario: str | None = None
    days: Literal[1, 7, 14, 30] = 30
    start: datetime = datetime(2026, 10, 1, tzinfo=TZ)
    initial: StateInput = Field(default_factory=StateInput)
    events: list[dict] = Field(default_factory=list, max_length=2500)
    commit: bool = False
    character_id: str | None = None

    @field_validator('start')
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError('Timezone required')
        return value


class CommitEvents(Strict):
    events: list[dict] = Field(max_length=2500)
    now: datetime


class LifestyleSimulation(Strict):
    records: LifestyleInput = Field(default_factory=LifestyleInput)
    start: datetime = datetime(2026, 10, 1, tzinfo=TZ)
    initial: StateInput = Field(default_factory=StateInput)

    @field_validator('initial')
    @classmethod
    def fresh_initial_state(cls, value):
        if value.stages is not None:
            raise ValueError('Lifestyle starts a fresh dry-run; initial.stages must be null, not a historical hysteresis snapshot')
        return value

    @field_validator('start')
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError('Timezone required')
        if value.hour or value.minute or value.second or value.microsecond:
            raise ValueError('Lifestyle start must be local midnight for daily limits')
        if value.utcoffset() != timedelta(hours=9):
            raise ValueError('Lifestyle calendar uses Asia/Seoul (+09:00)')
        return value


class LifestyleComparison(LifestyleSimulation):
    text: str = Field(default='오늘은 뭘 해볼까?', min_length=1, max_length=1500)
    mode: Literal['qwen', 'dummy'] = 'qwen'
    generation: Generation = Field(default_factory=Generation)
    memories: list[Memory] = Field(default_factory=list, max_length=3)
    speech_level: Literal['casual', 'formal'] = 'casual'


def checked_events(events):
    from .persona_engine import GrowthEvent
    parsed = [GrowthEvent.model_validate(x).model_dump(mode='json') for x in events]
    if any(x['source'] != 'simulation' for x in parsed):
        raise ValueError('Persona Lab accepts explicitly synthetic source=simulation events only')
    return parsed


def state_input(value, now, events=()):
    from .persona_engine import replay_events
    from .persona_engine import personality_stages
    # Audit history for selector eligibility, then apply explicit FINAL preview state.
    state = replay_events(list(events), now=now)
    state['personality'] = value.personality.model_dump()
    state['short_term'] = value.short_term.model_dump()
    state['stages'] = personality_stages(state['personality'], value.stages)
    state['character_voice'] = value.character_voice
    return state


def simulate(body):
    from .persona_engine import replay_events
    from .persona_ledger import summarize_ledger
    from .persona_quests import select_quests
    from .persona_scenarios import scenario_events, SCENARIOS
    if body.scenario is not None and body.scenario not in SCENARIOS:
        raise ValueError('Unknown simulation scenario')
    events = scenario_events(body.scenario, days=body.days, start=body.start) if body.scenario else []
    events += checked_events(body.events)
    if any(not body.start <= datetime.fromisoformat(x['occurred_at']) < body.start + timedelta(days=body.days) for x in events):
        raise ValueError('Simulation events must fall within the selected start date and duration')
    if not any(x.get('payload', {}).get('anchor_only') and x['occurred_at'] == body.start.isoformat() for x in events):
        events = [{'event_id': 'lab-anchor', 'user_id': 'persona-lab', 'character_id': 'lab-preview',
                   'event_type': 'inactivity_period', 'occurred_at': body.start.isoformat(), 'source': 'simulation',
                   'verification_status': 'verified', 'confidence': 1, 'payload': {'anchor_only': True}, 'idempotency_key': 'lab-anchor'}] + events
    # One test stream. IDs/references stay unchanged; owners cannot address production objects.
    events = [dict(x, user_id='persona-lab', character_id='lab-preview') for x in checked_events(events)]
    initial = body.initial.personality.model_dump()
    short = body.initial.short_term.model_dump()
    timeline = []
    for day in range(body.days + 1):
        at = body.start if day == 0 else body.start + timedelta(days=day) - timedelta(microseconds=1)
        visible = [x for x in events if datetime.fromisoformat(x['occurred_at']) <= at]
        state = replay_events(visible, now=at, initial=initial, short_term=short)
        quests = select_quests(state, visible, at, limit=1, user_text='오늘 할 수 있는 작은 퀘스트를 골라 줘.')
        if day and quests:
            quest = quests[0]
            ident = f'lab-recommend:{day}:{quest["quest_id"]}'
            proposal = {'event_id': ident, 'user_id': 'persona-lab', 'character_id': 'lab-preview',
                        'event_type': 'quest_proposed', 'occurred_at': at.isoformat(), 'source': 'simulation',
                        'verification_status': 'verified', 'confidence': 1, 'idempotency_key': ident,
                        'payload': {'quest_id': quest['quest_id'], 'quest_instance_id': ident,
                                    'selection_reason': quest['selection_reason']}}
            events.append(proposal)
            state = replay_events(visible + [proposal], now=at, initial=initial, short_term=short)
        timeline.append({'day': day, 'date': at.isoformat(), 'state': state, 'quests': quests})
    return {'scenario': body.scenario, 'days': body.days, 'timeline': timeline, 'events': events,
            'ledger': timeline[-1]['state']['ledger'], 'synthetic': True, 'model_generated': False,
            'ledger_summary': summarize_ledger(initial, timeline[-1]['state']['personality'], timeline[-1]['state']['ledger']),
            'dry_run': not body.commit, 'production_write': False}


def create_app(runtime=None, store=None):
    application = FastAPI(title='Healthmon Persona Lab · development only', docs_url=None, redoc_url=None, openapi_url=None)
    application.state.runtime = runtime or PersonaRuntime()
    application.state.store = store or LabStore()

    @application.middleware('http')
    async def development_only(request, call_next):
        environments = [os.getenv(key, '').lower() for key in ('APP_ENV', 'ENVIRONMENT', 'NODE_ENV')]
        if os.getenv('PERSONA_LAB_ENABLED') != '1' or os.getenv('APP_ENV') != 'development' or any(x in ('production', 'prod') for x in environments):
            return JSONResponse(status_code=404, content={'detail': 'Persona Lab is disabled'})
        try:
            if not ipaddress.ip_address(request.client.host).is_loopback:
                raise ValueError()
            parsed = urlsplit(str(request.url))
            if parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
                raise ValueError()
            if request.method not in ('GET', 'HEAD'):
                if request.headers.get('origin') != f'{parsed.scheme}://{parsed.netloc}' or request.headers.get('x-persona-lab') != '1':
                    raise ValueError()
        except (ValueError, AttributeError):
            return JSONResponse(status_code=403, content={'detail': 'Same-origin local development requests only'})
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        return response

    @application.get('/')
    def index():
        return FileResponse(ROOT / 'web/persona-lab/index.html')

    @application.get('/lab/{filename}')
    def static_file(filename: str):
        if filename not in ('app.js', 'styles.css', 'lifestyle.js', 'character.js', 'character.css'):
            raise HTTPException(404)
        return FileResponse(ROOT / 'web/persona-lab' / filename)

    @application.get('/api/health')
    def health():
        backend = application.state.runtime.backend if hasattr(application.state.runtime, 'backend') else None
        return {'status': 'ok', 'development_only': True, 'model_loaded': bool(backend and backend.model is not None),
                'baseline': json.loads((ROOT / 'config/serving.json').read_text(encoding='utf-8'))['adapter_path'],
                'storage': 'separate synthetic test store; legacy PostgreSQL is never connected'}

    @application.get('/api/config')
    def config():
        from .persona_scenarios import SCENARIOS
        from .persona_lifestyle import LIFESTYLE_PRESETS
        from .persona_lifestyle_service import TEST_QUESTIONS
        return {'presets': PRESETS, 'scenarios': SCENARIOS, 'generation': DEFAULT_GENERATION,
                'lifestyle_presets': LIFESTYLE_PRESETS, 'lifestyle_questions': TEST_QUESTIONS,
                'voices': json.loads((ROOT / 'config/persona_voices.json').read_text(encoding='utf-8')),
                'rules': json.loads((ROOT / 'config/persona_rules.json').read_text(encoding='utf-8')),
                'catalog': json.loads((ROOT / 'config/quest_catalog.json').read_text(encoding='utf-8'))}

    @application.post('/api/lifestyle/simulate')
    def lifestyle_simulate(body: LifestyleSimulation):
        from .persona_lifestyle_service import lifestyle_projection
        try:
            return lifestyle_projection(body)
        except ValueError as error:
            raise HTTPException(422, str(error))

    @application.get('/api/lifestyle/evaluation')
    def lifestyle_evaluation():
        directory = ROOT / 'runs/persona-lifestyle'
        def read(name, default):
            path = directory / name
            return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
        cases = read('actual-model-comparisons.json', [])
        review = read('model-review.json', {'cases': [], 'summary': {}})
        return {'saved_evaluation': True, 'generated_now': False, 'cases': cases, 'review': review,
                'completed_pairs': len(cases), 'planned_pairs': 54,
                'summary': read('verification-summary.json', {}),
                'scope': 'Saved actual LoRA evaluation with its original input/memory/settings; independent of current form values.'}

    @application.post('/api/lifestyle/compare')
    def lifestyle_compare(body: LifestyleComparison):
        from .persona_lifestyle_service import lifestyle_projection, lifestyle_contexts
        from .persona_comparison import build_comparison_observations
        try:
            projection = lifestyle_projection(body)
            contexts = lifestyle_contexts(body, projection)
            result = application.state.runtime.compare(contexts, body.text, body.generation.model_dump(), 1, body.mode)
            result['comparison_observations'] = build_comparison_observations(result)
            result['lifestyle'] = {'records': projection['compiled']['requested'], 'days': projection['days'],
                                   'dry_run': True, 'database_write': False,
                                   'assumptions': projection['compiled']['assumptions'],
                                   'scope': 'Record history, derived personality/short-term state and quest candidates change together; not a LoRA-only causal test.'}
            return result
        except ValueError as error:
            raise HTTPException(422, str(error))
        except RuntimeError as error:
            raise HTTPException(503, 'Local Qwen unavailable: ' + str(error))

    @application.post('/api/preview')
    def preview(body: Preview):
        try:
            shared = checked_events(body.events)
            histories = {'a': checked_events(body.events_a) if body.events_a is not None else shared,
                         'b': checked_events(body.events_b) if body.events_b is not None else shared}
            memories = [x.model_dump() for x in body.memories]
            dates = {'a': body.now_a or body.now, 'b': body.now_b or body.now}
            contexts = {key: prepare_context(state_input(value, dates[key], histories[key]), histories[key], dates[key], body.text, memories, body.speech_level)
                        for key, value in (('a', body.a), ('b', body.b))}
            return application.state.runtime.compare(contexts, body.text, body.generation.model_dump(), body.repetitions, body.mode)
        except ValueError as error:
            raise HTTPException(422, str(error))
        except RuntimeError as error:
            raise HTTPException(503, 'Local Qwen unavailable: ' + str(error))

    @application.post('/api/simulate')
    def simulation(body: Simulation):
        try:
            if body.commit:
                existing = application.state.store.read(body.character_id or '')
                if existing['initial'] != body.initial.personality.model_dump() or existing['short_term'] != body.initial.short_term.model_dump():
                    raise ValueError('Simulation initial state must match the selected test character')
            result = simulate(body)
            if body.commit:
                result['commit_result'] = application.state.store.append(body.character_id, result['events'], datetime.fromisoformat(result['timeline'][-1]['date']))
            return result
        except ValueError as error:
            raise HTTPException(422, str(error))

    @application.post('/api/characters')
    def create_character(body: StateInput):
        return {'character_id': application.state.store.create(body.personality.model_dump(), body.short_term.model_dump()),
                'scope': 'separate synthetic test character only'}

    @application.get('/api/characters/{character_id}')
    def read_character(character_id: str):
        try:
            return application.state.store.read(character_id)
        except ValueError as error:
            raise HTTPException(404, str(error))

    @application.post('/api/characters/{character_id}/events')
    def add_events(character_id: str, body: CommitEvents):
        try:
            if body.now.tzinfo is None:
                raise ValueError('Timezone required')
            return application.state.store.append(character_id, checked_events(body.events), body.now)
        except ValueError as error:
            raise HTTPException(422, str(error))

    from .character_lab_api import install
    install(application)
    return application


app = create_app()
