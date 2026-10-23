"""Versioned remote AI protocol. No model or GPU imports are permitted here."""
import hashlib
import math
from typing import Literal
from urllib.parse import urljoin, urlparse
import httpx
from pydantic import Field, ValidationError
from .contracts import Strict

MAX_EVOLUTION_ASSET_BYTES = 64 * 1024 * 1024


class AIUnavailable(Exception):
    def __init__(self, code='ai_unavailable', retryable=False):
        self.code, self.retryable = code, retryable
        super().__init__(code)


class Classification(Strict):
    target: Literal['character', 'proposal', 'exercise', 'food', 'other']
    sentiment: Literal['positive', 'neutral', 'negative']
    motivation: Literal['high', 'neutral', 'low']
    character_affection: Literal['positive', 'neutral', 'negative']
    acceptance: Literal['accept', 'reject', 'none']
    confidence: float = Field(ge=0, le=1)
    proposal_id: str | None = None


class Speech(Strict):
    speech: str = Field(min_length=1, max_length=500)
    emotion: Literal['neutral', 'happy', 'encouraging', 'sad', 'tired', 'grumpy', 'playful']
    animation: Literal['idle', 'wave', 'cheer', 'encourage', 'rest', 'pout', 'laugh']
    memory_ids: list[str] = Field(default_factory=list, max_length=3)
    classification: Classification


class Nutrients(Strict):
    energy_kcal: float | None = Field(default=None, ge=0)
    carbohydrate_g: float | None = Field(default=None, ge=0)
    protein_g: float | None = Field(default=None, ge=0)
    fat_g: float | None = Field(default=None, ge=0)
    vegetable_fruit_g: float | None = Field(default=None, ge=0)


class FoodCandidate(Strict):
    food: str = Field(min_length=1, max_length=200)
    confidence: float = Field(ge=0, le=1)
    per_100g: Nutrients
    estimated_grams: float | None = Field(default=None, gt=0, le=10000)


class FoodResult(Strict):
    candidates: list[FoodCandidate] = Field(min_length=1, max_length=3)


class EmbeddingResult(Strict):
    model_id: str
    model_version: str
    dimension: int
    vector: list[float]


class EvolutionResult(Strict):
    job_id: str
    stage: int = Field(ge=0, le=3)
    status: Literal['queued', 'running', 'succeeded', 'failed', 'unsupported']
    model_url: str | None = None
    model_sha256: str | None = Field(default=None, pattern='^[0-9a-f]{64}$')
    size_bytes: int | None = Field(default=None, gt=0, le=MAX_EVOLUTION_ASSET_BYTES)
    error: str | None = Field(default=None, max_length=200)


class Envelope(Strict):
    contract_version: str
    request_id: str
    provenance: Literal['real', 'synthetic']
    result: dict


class Gateway:
    def __init__(self, settings):
        self.settings = settings

    def assert_available(self, owner, database_is_test):
        if self.settings.ai_mode == 'disabled':
            raise AIUnavailable()
        if self.settings.ai_mode == 'mock' and not (database_is_test and owner in self.settings.test_owners):
            raise AIUnavailable('mock_requires_test_owner_and_database')

    @property
    def space(self):
        if self.settings.ai_mode == 'mock':
            return 'mock.embedding:1:1024'
        return f'{self.settings.embedding_model}:{self.settings.embedding_version}:1024'

    def call(self, capability, request_id, pet_id, payload, owner, database_is_test, method='POST'):
        try:
            result, provenance = self._call(capability, request_id, pet_id, payload, owner, database_is_test, method)
        except AIUnavailable as exc:
            if capability == 'chat':
                self.settings.record_remote_chat(False, exc.code)
            raise
        if capability == 'chat' and provenance == 'real':
            self.settings.record_remote_chat(True, 'validated_real_chat')
        return result, provenance

    def _call(self, capability, request_id, pet_id, payload, owner, database_is_test, method='POST'):
        self.assert_available(owner, database_is_test)
        schema = {'chat': Speech, 'food': FoodResult, 'embedding': EmbeddingResult, 'evolutions': EvolutionResult}[capability]
        if self.settings.ai_mode == 'mock':
            if capability == 'chat':
                result = {'speech': '합성 테스트 응답입니다. 생활 기록은 서버 상태로 확인합니다.', 'emotion': 'neutral', 'animation': 'idle', 'memory_ids': [],
                          'classification': {'target': 'other', 'sentiment': 'neutral', 'motivation': 'neutral', 'character_affection': 'neutral', 'acceptance': 'none', 'confidence': 1}}
            elif capability == 'food':
                result = {'candidates': [{'food': '합성 테스트 음식', 'confidence': 1, 'per_100g': {'energy_kcal': 200, 'carbohydrate_g': 25, 'protein_g': 15, 'fat_g': 4, 'vegetable_fruit_g': None}, 'estimated_grams': None}]}
            elif capability == 'embedding':
                result = {'model_id': 'mock.embedding', 'model_version': '1', 'dimension': 1024, 'vector': [1.] + [0.] * 1023}
            else:
                # Synthetic jobs validate control flow; never invent a completed rigged model.
                result = {'job_id': request_id, 'stage': payload['stage'], 'status': 'unsupported', 'error': 'synthetic_fixture_has_no_model_asset'}
            envelope = Envelope(contract_version=self.settings.contract_version, request_id=request_id, provenance='synthetic', result=result)
        else:
            path = '/v1/' + capability + ('/' + request_id if capability == 'evolutions' else '')
            body = {'contract_version': self.settings.contract_version, 'request_id': request_id, 'pet_id': pet_id, 'input': payload}
            try:
                with httpx.Client(timeout=httpx.Timeout(self.settings.ai_timeout, connect=min(5, self.settings.ai_timeout)), trust_env=False, follow_redirects=False) as client:
                    response = client.request(method, self.settings.ai_base_url + path,
                                              json=body if method != 'GET' else None,
                                              headers={'Authorization': 'Bearer ' + self.settings.ai_token})
                    if response.status_code >= 400:
                        raise AIUnavailable('ai_authentication_failed' if response.status_code in (401, 403) else 'ai_http_error', response.status_code >= 500 or response.status_code == 429)
                    if len(response.content) > 2 * 1024 * 1024:
                        raise AIUnavailable('ai_response_too_large')
                    envelope = Envelope.model_validate(response.json())
            except httpx.TimeoutException as exc:
                raise AIUnavailable('ai_timeout', True) from exc
            except httpx.HTTPError as exc:
                raise AIUnavailable('ai_connection_failed', True) from exc
            except (ValueError, ValidationError) as exc:
                raise AIUnavailable('ai_invalid_json_or_envelope') from exc
        if envelope.contract_version != self.settings.contract_version or envelope.request_id != request_id:
            raise AIUnavailable('ai_contract_or_request_id_mismatch')
        if envelope.provenance == 'synthetic' and not (database_is_test and owner in self.settings.test_owners):
            raise AIUnavailable('synthetic_result_rejected')
        try:
            result = schema.model_validate(envelope.result).model_dump(mode='json')
        except ValidationError as exc:
            raise AIUnavailable('ai_invalid_result') from exc
        if capability == 'chat':
            allowed = {item['id'] for item in payload.get('context', {}).get('memories', [])}
            if not set(result['memory_ids']).issubset(allowed):
                raise AIUnavailable('ai_fabricated_memory_reference')
        if capability == 'embedding':
            expected = ('mock.embedding', '1') if envelope.provenance == 'synthetic' else (self.settings.embedding_model, self.settings.embedding_version)
            if (result['model_id'], result['model_version']) != expected or result['dimension'] != 1024 or len(result['vector']) != 1024:
                raise AIUnavailable('embedding_space_mismatch')
            if not all(math.isfinite(v) for v in result['vector']) or not any(result['vector']):
                raise AIUnavailable('invalid_embedding_vector')
        if capability == 'evolutions' and (result['job_id'] != request_id or result['stage'] != payload['stage']):
            raise AIUnavailable('evolution_job_identity_mismatch')
        if capability == 'evolutions' and result['status'] == 'succeeded' and not all(result.get(k) for k in ('model_url', 'model_sha256', 'size_bytes')):
            raise AIUnavailable('evolution_asset_metadata_required')
        return result, envelope.provenance

    def asset(self, url, expected_sha, expected_size):
        origin = urlparse(self.settings.ai_base_url)
        target = urlparse(urljoin(self.settings.ai_base_url + '/', url))
        if (target.scheme, target.netloc) != (origin.scheme, origin.netloc) or target.username or target.password or target.fragment:
            raise AIUnavailable('asset_origin_rejected')
        if not expected_sha or not expected_size:
            raise AIUnavailable('asset_integrity_metadata_required')
        if expected_size < 1 or expected_size > MAX_EVOLUTION_ASSET_BYTES:
            raise AIUnavailable('asset_size_mismatch')
        output = bytearray()
        with httpx.Client(timeout=self.settings.ai_timeout, trust_env=False, follow_redirects=False) as client:
            try:
                with client.stream('GET', target.geturl(), headers={'Authorization': 'Bearer ' + self.settings.ai_token}) as response:
                    response.raise_for_status()
                    for chunk in response.iter_bytes():
                        output.extend(chunk)
                        if len(output) > expected_size:
                            raise AIUnavailable('asset_size_mismatch')
            except httpx.HTTPError as exc:
                raise AIUnavailable('asset_download_failed', True) from exc
        if len(output) != expected_size or hashlib.sha256(output).hexdigest() != expected_sha:
            raise AIUnavailable('asset_integrity_failed')
        return bytes(output)
