"""Strict, bounded contracts for synthetic Character Lab sessions."""
from datetime import date as CalendarDate
from typing import Literal
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator
import yaml
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = yaml.safe_load((ROOT / 'config/character_lab_rules.yaml').read_text(encoding='utf-8'))


def canonical_json(value):
    """JSON numeric spelling survives browser round trips (1.0 becomes 1)."""
    def normalize(item):
        if isinstance(item, float) and item.is_integer():
            return int(item)
        if isinstance(item, dict):
            return {k: normalize(v) for k, v in item.items()}
        if isinstance(item, list):
            return [normalize(v) for v in item]
        return item
    return json.dumps(normalize(value), ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class CharacterState(Strict):
    level: int = 1
    exp: float = 0
    growth_stage: str = Field(default='initial', max_length=80)
    upper_body: float = 50
    lower_body: float = 50
    nutrition: float = 50
    energy_balance: float = 0
    activity: float = 50
    affection: float = Field(default=50, validation_alias=AliasChoices('affection', 'affinity'))
    initiative: float = 50
    curiosity: float = 50
    confidence: float = 50
    roughness: float = 10
    bluntness: float = 20
    courtesy: float = 60
    mood: float = 0
    body_type: str = Field(default='initial', max_length=80)
    evolution_stage: int = Field(default=0, ge=0, le=3)
    previous_evolution: dict = Field(default_factory=dict)
    virtual_test_date: CalendarDate = CalendarDate(2026, 10, 4)
    last_upper_exercise: CalendarDate | None = None
    last_lower_exercise: CalendarDate | None = None

    @field_validator(*RULES['ranges'].keys(), mode='after')
    @classmethod
    def clamp(cls, value, info):
        lo, hi = RULES['ranges'][info.field_name]
        return min(hi, max(lo, value))

    @field_validator('previous_evolution')
    @classmethod
    def previous(cls, value):
        if set(value) - {'evolution_stage', 'final_body_type'}:
            raise ValueError('previous_evolution accepts evolution_stage and final_body_type only')
        stage = value.get('evolution_stage', 0)
        body = value.get('final_body_type', 'initial')
        if isinstance(stage, bool) or not isinstance(stage, int) or not 0 <= stage <= 3:
            raise ValueError('Previous evolution stage must be an integer 0..3')
        if not isinstance(body, str) or not 1 <= len(body) <= 80:
            raise ValueError('Previous body type must be a bounded string')
        return value


class ConversationLabel(Strict):
    target: Literal['exercise', 'food', 'character', 'quest', 'other']
    sentiment: Literal['positive', 'neutral', 'negative']
    motivation: Literal['high', 'medium', 'low', 'none']
    character_affection: Literal['positive', 'neutral', 'negative']
    acceptance: Literal['accept', 'reject', 'none']
    analysis_confidence: float = Field(ge=0, le=1)


class FoodLabel(Strict):
    protein: Literal['low', 'proper', 'high', 'unknown'] = 'unknown'
    carbohydrate: Literal['low', 'proper', 'high', 'unknown'] = 'unknown'
    fat: Literal['low', 'proper', 'high', 'unknown'] = 'unknown'
    vegetable: Literal['low', 'proper', 'unknown'] = 'unknown'
    amount: Literal['low', 'proper', 'high', 'unknown'] = 'unknown'
    analysis_confidence: float = Field(default=0, ge=0, le=1)


class Session(Strict):
    state: CharacterState = Field(default_factory=CharacterState)
    initial_date: CalendarDate = CalendarDate(2026, 10, 4)
    events: list[dict] = Field(default_factory=list, max_length=5000)
    logs: list[dict] = Field(default_factory=list, max_length=10000)
    quests: dict = Field(default_factory=dict)
    budgets: dict = Field(default_factory=dict)
    weeks: list[str] = Field(default_factory=list, max_length=1000)
    processed: dict = Field(default_factory=dict)
    decay_dates: list[str] = Field(default_factory=list, max_length=4000)
    quest_audit: list[dict] = Field(default_factory=list, max_length=10000)


class Exercise(Strict):
    exercise_type: str = Field(default='squat', min_length=1, max_length=80)
    category: Literal['upper', 'lower', 'full'] = 'lower'
    actual: float = Field(default=50, ge=0, le=1000000)
    target: float = Field(default=50, gt=0, le=1000000)
    unit: Literal['step', 'count', 'minute'] = 'count'
    date: CalendarDate | None = None
    verification_status: Literal['verified', 'user_reported', 'unverified'] = 'verified'
    quest_id: str | None = Field(default=None, max_length=100)
    explicit_goal: bool = False
    due_date: CalendarDate | None = None


class Food(Strict):
    raw_text: str = Field(default='', max_length=1500)
    analysis: FoodLabel
    model_prediction: FoodLabel | None = None
    model_identifier: str | None = Field(default=None, max_length=300)
    prompt_version: str | None = Field(default=None, max_length=100)
    amount_severity: Literal['normal', 'extreme'] = 'normal'
    date: CalendarDate | None = None


class Conversation(Strict):
    text: str = Field(min_length=1, max_length=1500)
    analysis: ConversationLabel
    model_prediction: ConversationLabel | None = None
    model_identifier: str | None = Field(default=None, max_length=300)
    prompt_version: str | None = Field(default=None, max_length=100)
    date: CalendarDate | None = None


class Quest(Strict):
    action: Literal['create', 'accept', 'reject', 'progress', 'complete', 'fail', 'expire'] = 'create'
    quest_id: str = Field(min_length=1, max_length=100)
    quest_type: Literal['exercise', 'food', 'interaction'] = 'exercise'
    title: str = Field(default='테스트 운동', min_length=1, max_length=200)
    target: str = Field(default='squat', min_length=1, max_length=80)
    target_value: float = Field(default=50, gt=0, le=1000000)
    unit: Literal['step', 'count', 'minute', 'record'] = 'count'
    reward_exp: float = Field(default=5, ge=0, le=RULES['exp']['max_quest_reward'])
    start_date: CalendarDate | None = None
    due_date: CalendarDate | None = None
    verification_method: Literal['exercise_record', 'food_record', 'admin_verified'] = 'exercise_record'
    progress: Literal[0.25, 0.5, 0.75] = 0.25
    admin_verified: bool = False
    character_proposal: bool = True
    quest_scope: Literal['custom', 'daily', 'mini'] = 'custom'
    catalog_id: str | None = Field(default=None, max_length=100)


class Time(Strict):
    action: Literal['advance', 'weekly', 'decay', 'all_weekly', 'restore_date'] = 'advance'
    days: int = Field(default=1, ge=1, le=366)


class Override(Strict):
    state: CharacterState


class QuestTick(Strict):
    pass


class Evolution(Strict):
    apply: bool = False


PAYLOADS = {'exercise': Exercise, 'food': Food, 'conversation': Conversation,
            'quest': Quest, 'quest_tick': QuestTick, 'time': Time, 'manual_override': Override, 'evolution': Evolution}


class Command(Strict):
    kind: Literal['exercise', 'food', 'conversation', 'quest', 'quest_tick', 'time', 'manual_override', 'evolution']
    event_id: str = Field(min_length=1, max_length=100)
    payload: dict

    @field_validator('payload')
    @classmethod
    def payload_schema(cls, value, info):
        kind = info.data.get('kind')
        if kind in PAYLOADS:
            return PAYLOADS[kind].model_validate(value).model_dump(mode='json')
        return value


class Run(Strict):
    session: Session | None = None
    session_id: str | None = Field(default=None, max_length=100)
    expected_revision: int | None = Field(default=None, ge=0)
    dry_run: bool = True
    commands: list[Command] = Field(default_factory=list, max_length=1000)
