from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 'healthmon.v1'
RULES_VERSION = 'rules.v1'

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Evidence(Strict):
    kind: Literal['message', 'activity']
    id: str
    revision: int = Field(ge=1)

class PersonalityUpdate(Strict):
    delta: dict[str, float]
    evidence_refs: list[Evidence] = Field(min_length=3)

class Action(Strict):
    type: Literal['none', 'offer_quest', 'show_progress'] = 'none'
    target_id: str | None = None

    @model_validator(mode='after')
    def target(self):
        if (self.type == 'none') != (self.target_id is None):
            raise ValueError('none requires null; other actions require a target')
        return self

class ModelOutput(Strict):
    speech: str = Field(min_length=1, max_length=500)
    emotion: Literal['neutral','happy','encouraging','sad','tired','grumpy','playful']
    animation: Literal['idle','wave','cheer','encourage','rest','pout','laugh']
    action: Action
    memory_ids: list[str] = Field(max_length=3)
    personality_update: PersonalityUpdate | None = None

class ChatInput(Strict):
    request_id: str = Field(min_length=8, max_length=100)
    text: str = Field(min_length=1, max_length=1500)
    state_version: int | None = Field(default=None, ge=0)

class ActivityInput(Strict):
    event_id: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=1)
    occurred_at: datetime
    kind: Literal['walk','food']
    amount: float = Field(ge=0, le=200000, allow_inf_nan=False)
    unit: Literal['steps','serving']
    source: Literal['user','sensor','backend','photo']
    confirmed: bool = False
    label: str = Field(default='', max_length=100)

    @model_validator(mode='after')
    def units(self):
        if self.occurred_at.tzinfo is None:
            raise ValueError('Timezone required')
        if self.unit != {'walk':'steps','food':'serving'}[self.kind]:
            raise ValueError('Invalid kind/unit')
        if self.source == 'photo' and self.confirmed:
            raise ValueError('A photo is not confirmed consumption')
        return self

class MemoryInput(Strict):
    source_id: str
    revision: int = Field(ge=1)
    slot: Literal['preference','goal','experience']

class SourceEdit(Strict):
    expected_revision: int = Field(ge=1)
    text: str = Field(min_length=1,max_length=1500)

class Decision(Strict):
    decision: Literal['accept','reject']

class SettingsInput(Strict):
    name: str = Field(default='몽글이', min_length=1,max_length=20)
    profanity: Literal['none','mild'] = 'mild'
    speech_level: Literal['formal','casual'] = 'casual'
    timezone: str = 'Asia/Seoul'
