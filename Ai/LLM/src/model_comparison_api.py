"""Routes inherit the existing loopback, origin, and development middleware."""
import json
import subprocess
import uuid
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from .character_lab_schema import CharacterState, Session
from .character_lab_models import response_context
from .persona_generation import Generation, Memory
from .model_comparison import compare_models
from .model_registry import ROOT, read_registry, cleanup_inventory

CRITERIA = ('naturalness', 'personality', 'continuity', 'non_repetition', 'memory',
            'identity', 'analysis', 'compatibility')


class Compare(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=1500)
    model_ids: list[str] = Field(default=['baseline-expanded', 'natural-v1'], min_length=2, max_length=4)
    state: CharacterState = Field(default_factory=CharacterState)
    session: Session = Field(default_factory=Session)
    memories: list[Memory] = Field(default_factory=list, max_length=3)
    recent: list[dict[str, str]] = Field(default_factory=list, max_length=6)
    generation: Generation = Field(default_factory=Generation)
    speech_level: Literal['casual', 'formal'] = 'casual'
    mode: Literal['qwen', 'dummy'] = 'qwen'
    case_id: str = Field(default='manual-synthetic', max_length=100)


class Feedback(BaseModel):
    model_config = ConfigDict(extra='forbid')
    evaluation_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    preferred_model: str = Field(max_length=100)
    scores: dict[str, dict[str, int | None]]
    note: str = Field(default='', max_length=2000)


def install(application):
    folder = ROOT / 'runs/model-comparisons'

    @application.get('/api/models')
    def models():
        return {**read_registry(), 'criteria': CRITERIA, 'cleanup': cleanup_inventory()}

    @application.get('/api/model-cases')
    def cases():
        return json.loads((ROOT / 'data/natural_eval_v1/cases.json').read_text(encoding='utf-8'))

    @application.post('/api/model-comparison')
    def comparison(body: Compare):
        try:
            if len(set(body.model_ids)) != len(body.model_ids):
                raise ValueError('Choose distinct model IDs')
            if any(set(row) != {'user', 'assistant'} or any(len(v) > 1500 for v in row.values()) for row in body.recent):
                raise ValueError('Recent dialogue requires bounded user/assistant pairs')
            context = response_context(body.session.model_dump(mode='json'), body.state.model_dump(mode='json'),
                        body.text, [m.model_dump() for m in body.memories], body.speech_level)
            context['recent'] = body.recent
            result = compare_models(application.state.runtime, context, body.text,
                                    body.model_ids, body.generation.model_dump(), body.mode)
            result['evaluation_id'] = uuid.uuid4().hex
            result['case_id'] = body.case_id
            result['git_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
            folder.mkdir(parents=True, exist_ok=True)
            (folder / (result['evaluation_id'] + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            return result
        except (ValueError, RuntimeError) as error:
            raise HTTPException(422, str(error))

    @application.post('/api/model-feedback')
    def feedback(body: Feedback):
        path = folder / (body.evaluation_id + '.json')
        if not path.is_file():
            raise HTTPException(404, 'Unknown saved evaluation')
        evaluation = json.loads(path.read_text(encoding='utf-8'))
        ids = {row['model_id'] for row in evaluation['results']}
        if evaluation['mode'] != 'qwen':
            raise HTTPException(422, 'Dummy output cannot be rated as model quality')
        if body.preferred_model not in ids | {'tie'} or set(body.scores) != ids:
            raise HTTPException(422, 'Scores must match the saved comparison')
        for values in body.scores.values():
            if set(values) != set(CRITERIA) or any(v is not None and (type(v) is not int or not 1 <= v <= 5) for v in values.values()):
                raise HTTPException(422, 'Each criterion accepts 1..5 or null for not assessed')
        review = {'evaluation_id': body.evaluation_id, 'case_id': evaluation['case_id'],
                  'context_sha256': evaluation['context_sha256'], 'git_commit': evaluation['git_commit'],
                  **body.model_dump(), 'human_review': True, 'automatic_selection': False}
        # Each review is immutable; ratings never overwrite raw generations or select a model.
        review_path = folder / (body.evaluation_id + '.review.' + uuid.uuid4().hex + '.json')
        review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding='utf-8')
        return {'saved': True, 'review_id': review_path.stem, 'automatic_selection': False}
