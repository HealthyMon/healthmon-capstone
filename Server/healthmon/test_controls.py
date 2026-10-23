"""Explicit controls for authenticated test owners; ordinary game APIs stay authoritative."""
import uuid
from typing import Literal

from fastapi import Depends, HTTPException
from psycopg.types.json import Jsonb
from pydantic import Field

from . import rules, service
from .contracts import Strict


class TestPetState(Strict):
    level: int = Field(ge=1, le=100)
    coin: int = Field(ge=0, le=1000000)
    upper_body: float = Field(ge=0, le=100)
    lower_body: float = Field(ge=0, le=100)
    nutrition: float = Field(ge=0, le=100)
    energy_balance: float = Field(ge=-100, le=100)
    activity: float = Field(ge=0, le=100)
    affinity: float = Field(ge=0, le=100)
    initiative: float = Field(ge=0, le=100)


class TestWorkout(Strict):
    request_id: str = Field(min_length=8, max_length=80)
    exercise: Literal['walking', 'running', 'pushup', 'squat', 'lunge', 'dumbbell']
    actual: float = Field(ge=0, le=1000000)


class TestQuest(Strict):
    slot: Literal['easy', 'medium', 'weekly']
    candidate: Literal['meal1', 'workout1', 'chat1', 'meal2', 'workout70', 'meal_workout', 'workout_days3', 'meal_days5', 'daily6']


def register(app, settings, db, identity, now):
    def allowed(owner):
        if settings.environment != 'test' or owner not in settings.test_owners or db.ready()['environment'] != 'test':
            raise HTTPException(403, 'Test controls require an isolated test database and a provisioned test owner')

    @app.put('/pets/{pet}/test-controls/state')
    def update_state(pet: str, body: TestPetState, owner=Depends(identity)):
        allowed(owner)
        with db.connect() as c:
            p = service.owned(c, owner, pet, True)
            timestamp = now()
            state, projection = service.refresh(c, p, timestamp, settings.chat_available(owner))
            level_exp = state['total_exp'] if body.level == state['level'] else sum(rules.required_exp(level) for level in range(1, body.level))
            if rules.exp_progress(level_exp)['evolution_target_stage'] < state['published_model_stage']:
                raise HTTPException(409, 'The selected level cannot undo a published evolution')
            ledger = c.execute('SELECT coalesce(sum(exp),0) AS exp,coalesce(sum(coin),0) AS coin FROM game_ledger WHERE pet_id=%s', (pet,)).fetchone()
            state['_test_controls'] = {
                'offsets': {axis: getattr(body, axis) - projection['state'][axis] for axis in
                            ('upper_body', 'lower_body', 'nutrition', 'energy_balance', 'activity', 'affinity', 'initiative')},
                'exp_offset': level_exp - ledger['exp'], 'coin_offset': body.coin - ledger['coin']}
            c.execute('UPDATE game_states SET state=%s WHERE pet_id=%s', (Jsonb(state), pet))
            updated, _ = service.refresh(c, service.owned(c, owner, pet, True), timestamp, settings.chat_available(owner), True, 'test_controls_changed')
        return updated

    @app.delete('/pets/{pet}/test-controls/state')
    def clear_state(pet: str, owner=Depends(identity)):
        allowed(owner)
        with db.connect() as c:
            p = service.owned(c, owner, pet, True)
            c.execute("UPDATE game_states SET state=state-'_test_controls' WHERE pet_id=%s", (pet,))
            state, _ = service.refresh(c, p, now(), settings.chat_available(owner), True, 'test_controls_cleared')
            if state['evolution_target_stage'] < state['published_model_stage']:
                raise HTTPException(409, 'Test values must be retained while their evolved model is published')
        return state

    @app.post('/pets/{pet}/test-controls/workout')
    def workout(pet: str, body: TestWorkout, owner=Depends(identity)):
        allowed(owner)
        with db.connect() as c:
            p = service.owned(c, owner, pet, True)
            ident = 'admin-workout-' + body.request_id
            existing = c.execute('SELECT occurred_at FROM sources WHERE pet_id=%s AND id=%s', (pet, ident)).fetchone()
            timestamp = now()
            occurred = existing['occurred_at'] if existing else timestamp
            raw = dict(event_id=ident, revision=1, occurred_at=occurred, source='user', synthetic=True,
                       workout_type=body.exercise, actual=body.actual, unit=rules.DEFAULT_GOALS[body.exercise]['unit'])
            result = service.store_event(c, p, 'workout', raw, service.normalize_workout(c, pet, raw), timestamp, settings)
        return result['state']

    @app.put('/pets/{pet}/test-controls/quests')
    def quest(pet: str, body: TestQuest, owner=Depends(identity)):
        from . import quests
        allowed(owner)
        if body.candidate not in quests._SPECS[body.slot]['candidates']:
            raise HTTPException(422, 'Quest candidate does not belong to the selected slot')
        if body.candidate == 'chat1' and not settings.chat_available(owner):
            raise HTTPException(409, 'Conversation is unavailable; choose another quest')
        with db.connect() as c:
            p = service.owned(c, owner, pet, True)
            timestamp = now()
            service.refresh(c, p, timestamp, settings.chat_available(owner))
            day = rules._day(timestamp)
            start = rules._monday(day) if body.slot == 'weekly' else day
            row = c.execute('SELECT id,template FROM quest_offers WHERE pet_id=%s AND slot=%s AND period_start=%s FOR UPDATE', (pet, body.slot, start)).fetchone()
            if not row:
                raise HTTPException(409, 'This quest slot is unavailable today')
            template = dict(row['template'], candidate=body.candidate, target=quests._TARGETS[body.candidate], test_selected=True)
            # Reuse the same slot and reward key: changing a test quest cannot pay it twice.
            c.execute("UPDATE quest_offers SET template=%s,status='active',progress=0,completed_at=NULL WHERE pet_id=%s AND id=%s", (Jsonb(template), pet, row['id']))
            state, _ = service.refresh(c, service.owned(c, owner, pet, True), timestamp, settings.chat_available(owner), True, 'test_quest_changed')
        return state
