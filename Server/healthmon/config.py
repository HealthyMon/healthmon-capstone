import hashlib
import json
import os
import secrets
import threading
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    database_url: str = field(repr=False)
    environment: str = 'development'
    ai_mode: str = 'disabled'
    ai_base_url: str = ''
    ai_token: str = field(default='', repr=False)
    ai_timeout: float = 30
    contract_version: str = 'healthmon.ai.v1'
    token_hashes: dict = field(default_factory=dict, repr=False)
    test_owners: frozenset = frozenset()
    instance_id: str = ''
    embedding_model: str = 'BAAI/bge-m3'
    embedding_version: str = '1'
    embedding_dimension: int = 1024
    allow_http_ai: bool = False
    worker_enabled: bool = True
    public_base_url: str = ''
    starter_manifest: Path | None = None
    _chat_evidence: tuple | None = field(default=None, init=False, repr=False, compare=False)
    _chat_evidence_lock: object = field(default_factory=threading.Lock, init=False, repr=False, compare=False)

    def _chat_endpoint_key(self):
        return hashlib.sha256(json.dumps([self.ai_base_url, self.contract_version, self.ai_token]).encode()).hexdigest()

    def record_remote_chat(self, available, code):
        """Last completed real chat evidence, shared by this CPU process only.

        No probe or TTL inference is made. A new Settings/process starts unknown;
        remote unknown retains the configured candidate policy until an actual
        request succeeds or fails. This does not block real retry requests.
        """
        if self.ai_mode == 'remote':
            with self._chat_evidence_lock:
                self._chat_evidence = (self._chat_endpoint_key(), bool(available), code)

    def chat_available(self, owner=None):
        if self.ai_mode == 'disabled':
            return False
        if self.ai_mode == 'mock':
            return self.environment == 'test' and owner in self.test_owners
        with self._chat_evidence_lock:
            evidence = self._chat_evidence
            return evidence[1] if evidence and evidence[0] == self._chat_endpoint_key() else True

    def __post_init__(self):
        if self.public_base_url:
            public = urlparse(self.public_base_url)
            if public.scheme not in ('http', 'https') or not public.hostname or public.username or public.password or public.query or public.fragment:
                raise ValueError('PUBLIC_BASE_URL must be an HTTP(S) URL without credentials, query or fragment')
        if not self.database_url:
            raise ValueError('DATABASE_URL must explicitly select this environment database')
        if self.environment not in ('development', 'test', 'production'):
            raise ValueError('Invalid APP_ENV')
        if self.ai_mode not in ('disabled', 'mock', 'remote'):
            raise ValueError('Invalid AI_MODE')
        if self.ai_mode == 'mock' and self.environment != 'test':
            raise ValueError('Mock AI requires APP_ENV=test and isolated test owners/database')
        if self.environment == 'production' and not self.token_hashes:
            raise ValueError('Production requires explicitly provisioned per-user bearer token hashes')
        if self.ai_mode == 'remote':
            parsed = urlparse(self.ai_base_url)
            if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError('AI_BASE_URL must be an origin/base path without credentials or query')
            if parsed.scheme != 'https' and not (self.environment != 'production' and self.allow_http_ai and parsed.scheme == 'http'):
                raise ValueError('Remote AI requires HTTPS; development HTTP must be explicit')
            if not self.ai_token:
                raise ValueError('AI_SERVER_TOKEN required in remote mode')
        if self.embedding_dimension != 1024:
            raise ValueError('Current PostgreSQL memory contract requires 1024-dimensional embeddings')

    @classmethod
    def from_env(cls):
        from dotenv import load_dotenv
        # Never load a parent workspace's private .env or existing personal database.
        load_dotenv(ROOT / '.env', override=False)
        hashes = json.loads(os.getenv('AUTH_TOKEN_HASHES', '{}'))
        if os.getenv('APP_ENV', 'development') != 'production':
            for token, owner in json.loads(os.getenv('DEV_TOKENS', '{}')).items():
                hashes[hashlib.sha256(token.encode()).hexdigest()] = owner
        starter_manifest=os.getenv('STARTER_MODEL_MANIFEST', str(ROOT / 'Server/assets/starter/lucan/manifest.json'))
        return cls(database_url=os.getenv('DATABASE_URL', ''), environment=os.getenv('APP_ENV', 'development'),
                   ai_mode=os.getenv('AI_MODE', 'disabled'), ai_base_url=os.getenv('AI_BASE_URL', '').rstrip('/'),
                   ai_token=os.getenv('AI_SERVER_TOKEN', ''), ai_timeout=float(os.getenv('AI_TIMEOUT_SECONDS', '30')),
                   contract_version=os.getenv('AI_CONTRACT_VERSION', 'healthmon.ai.v1'), token_hashes=hashes,
                   test_owners=frozenset(json.loads(os.getenv('TEST_OWNERS', '[]'))), instance_id=os.getenv('SERVER_INSTANCE_ID', ''),
                   embedding_model=os.getenv('EMBEDDING_MODEL_ID', 'BAAI/bge-m3'), embedding_version=os.getenv('EMBEDDING_MODEL_VERSION', '1'),
                   allow_http_ai=os.getenv('ALLOW_HTTP_AI', 'false').lower() == 'true',
                   worker_enabled=os.getenv('WORKER_ENABLED', 'true').lower() == 'true',
                   public_base_url=os.getenv('PUBLIC_BASE_URL', '').rstrip('/'),
                   starter_manifest=Path(starter_manifest).resolve() if starter_manifest else None)

    def owner(self, bearer):
        digest = hashlib.sha256(bearer.encode()).hexdigest()
        for key, value in self.token_hashes.items():
            if secrets.compare_digest(digest, key):
                return value
        return None
