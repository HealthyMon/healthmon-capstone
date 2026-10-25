from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class PetSettings(Strict):
    name: str = Field(default='몽글이', min_length=1, max_length=20)
    profanity: Literal['none', 'mild'] = 'mild'
    speech_level: Literal['formal', 'casual'] = 'casual'
    timezone: Literal['Asia/Seoul'] = 'Asia/Seoul'


class Event(Strict):
    event_id: str = Field(min_length=1, max_length=100)
    revision: int = Field(default=1, ge=1)
    occurred_at: datetime
    source: Literal['user', 'watch', 'sensor', 'backend', 'photo'] = 'user'
    synthetic: bool = False

    @model_validator(mode='after')
    def timezone_required(self):
        if self.occurred_at.tzinfo is None:
            raise ValueError('Timezone required')
        return self


class Workout(Event):
    workout_type: str = Field(min_length=1, max_length=40)
    started_at: datetime | None = None
    actual: float | None = Field(default=None, ge=0, le=1000000)
    target: float | None = Field(default=None, gt=0, le=1000000)
    unit: Literal['steps', 'minutes', 'repetitions'] | None = None
    body_part: Literal['upper', 'lower', 'full'] | None = None
    goal_id: str | None = None
    confirmed_nonperformance: bool = False
    # Optional watch measurements. None means not measured/unsupported (not zero).
    duration_seconds: int | None = Field(default=None, ge=0)
    average_heart_rate_bpm: float | None = Field(default=None, ge=0, le=300)
    max_heart_rate_bpm: float | None = Field(default=None, ge=0, le=300)
    calories_kcal: float | None = Field(default=None, ge=0)
    steps: int | None = Field(default=None, ge=0)
    distance_km: float | None = Field(default=None, ge=0)

    @model_validator(mode='after')
    def start_time(self):
        if self.started_at is not None and (self.started_at.tzinfo is None or self.started_at > self.occurred_at):
            raise ValueError('started_at must be timezone aware and no later than occurred_at')
        if self.confirmed_nonperformance and self.source != 'user':
            raise ValueError('Explicit nonperformance confirmation requires user input')
        return self


class Meal(Event):
    food_name: str = Field(max_length=200)
    meal_type: Literal['breakfast', 'lunch', 'dinner', 'snack']
    confirmed: bool = False
    quantity_confirmed: bool = False
    grams: float | None = Field(default=None, gt=0, le=10000)
    carbohydrate_g: float | None = Field(default=None, ge=0, le=10000)
    protein_g: float | None = Field(default=None, ge=0, le=10000)
    fat_g: float | None = Field(default=None, ge=0, le=10000)
    vegetable_fruit_g: float | None = Field(default=None, ge=0, le=10000)
    kcal: float | None = Field(default=None, ge=0, le=100000)
    kcal_reconfirmed: bool = False
    analysis_id: str | None = None


class Goal(Strict):
    exercise_type: str = Field(min_length=1, max_length=40)
    target: float = Field(gt=0, le=1000000)
    unit: Literal['steps', 'minutes', 'repetitions']
    body_part: Literal['upper', 'lower', 'full']


class Chat(Strict):
    request_id: str = Field(min_length=8, max_length=100)
    text: str = Field(min_length=1, max_length=1500)
    state_version: int | None = Field(default=None, ge=0)


class Decision(Strict):
    decision: Literal['accept', 'reject']


class Evolution(Strict):
    request_id: str = Field(min_length=8, max_length=100)


class Session(Strict):
    session_id: str = Field(min_length=1, max_length=100)
    active: bool = True


class ConfirmFood(Strict):
    analysis_id: str = Field(min_length=1, max_length=100)
    candidate_id: int = Field(ge=0, le=2)
    grams: float | None = Field(default=None, gt=0, le=10000)
    meal_type: Literal['breakfast', 'lunch', 'dinner', 'snack'] = 'snack'
    vegetable_fruit_g: float | None = Field(default=None, ge=0, le=10000)
    kcal_reconfirmed: bool = False
    event_id: str | None = Field(default=None, min_length=1, max_length=100)
    revision: int = Field(default=1, ge=1)
    synthetic: bool = False


class Memory(Strict):
    source_id: str
    revision: int = Field(ge=1)
    slot: Literal['preference', 'goal', 'experience']


class LegacyActivity(Event):
    kind: Literal['walk', 'food']
    amount: float = Field(ge=0, le=200000)
    unit: Literal['steps', 'serving']
    confirmed: bool = False
    label: str = Field(default='', max_length=100)


class Proposal(Strict):
    request_id: str = Field(min_length=8, max_length=100)
    candidate: Literal['meal1', 'workout1', 'chat1', 'meal2', 'workout70', 'meal_workout']


class ProposalControl(Strict):
    action: Literal['rest', 'stop', 'resume']


class SourceEdit(Strict):
    expected_revision: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=1500)
