"""Shared existing Persona Lab generation and synthetic Memory contracts."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Generation(Strict):
    seed: int = Field(default=20261001, ge=0, le=2**31-10)
    max_new_tokens: int = Field(default=240, ge=80, le=320)
    temperature: float = Field(default=0.7, ge=0.1, le=1.5)
    top_p: float = Field(default=0.9, ge=0.1, le=1)
    repetition_penalty: float = Field(default=1.05, ge=1, le=1.5)
    max_time: int = Field(default=90, ge=10, le=120)


class Memory(Strict):
    id: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=200)
    source_id: str = Field(min_length=1, max_length=100)
    source_revision: int = Field(default=1, ge=1)
    slot: Literal['preference', 'goal', 'experience'] = 'preference'
    verification_status: Literal['user_reported', 'verified'] = 'user_reported'
