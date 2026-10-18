"""Local browser adapter; the public pet API remains usable with Bearer auth."""
import base64
import hashlib
import hmac
import ipaddress
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .db import connect, owned

COOKIE = 'healthmon_beta_session'
SESSION_SECONDS = 12 * 60 * 60
ROOT = Path(__file__).resolve().parents[1]


def _accounts():
    try:
        accounts = json.loads(os.getenv('DEV_TOKENS', '{}'))
        if not isinstance(accounts, dict):
            raise ValueError()
        return {key: owner for key, owner in accounts.items()
                if isinstance(key, str) and key and isinstance(owner, str) and owner}
    except (ValueError, TypeError):
        raise HTTPException(503, 'Local development authentication is not configured')


def _signing_key():
    accounts = _accounts()
    if not accounts:
        raise HTTPException(503, 'Local development authentication is not configured')
    secret = os.getenv('BETA_SESSION_SECRET') or next(iter(accounts))
    return hmac.new(secret.encode(), b'healthmon/local-browser-session/v1', hashlib.sha256).digest()


def _local_request(request: Request, *, require_origin=False):
    """Reject remote peers, rebinding Host names, and browser cross-origin writes."""
    try:
        peer = ipaddress.ip_address(request.client.host if request.client else '')
        local = peer.is_loopback or bool(getattr(peer, 'ipv4_mapped', None) and peer.ipv4_mapped.is_loopback)
    except ValueError:
        local = False
    if not local:
        raise HTTPException(403, 'Browser beta is available on this computer only')
    host = request.headers.get('host', '')
    try:
        parsed = urlsplit(f'{request.url.scheme}://{host}')
        valid_host = (parsed.hostname in {'localhost', '127.0.0.1', '::1'}
                      and not parsed.username and not parsed.password
                      and not parsed.path and not parsed.query and not parsed.fragment)
        parsed.port  # Validate the port without accepting malformed Host headers.
    except ValueError:
        valid_host = False
    if not valid_host:
        raise HTTPException(403, 'Local browser host required')
    expected_origin = f'{request.url.scheme}://{host}'.lower()
    origin = request.headers.get('origin')
    if ((require_origin and not origin)
            or (origin is not None and origin.lower() != expected_origin)
            or request.headers.get('sec-fetch-site') == 'cross-site'):
        raise HTTPException(403, 'Same-origin browser request required')


def _encode_session(owner, expires):
    payload = json.dumps({'owner': owner, 'expires': expires}, separators=(',', ':')).encode()
    encoded = base64.urlsafe_b64encode(payload).rstrip(b'=').decode()
    signature = hmac.new(_signing_key(), encoded.encode(), hashlib.sha256).hexdigest()
    return encoded + '.' + signature


def _decode_session(value):
    try:
        if len(value) > 4096:
            raise ValueError()
        encoded, signature = value.split('.')
        expected = hmac.new(_signing_key(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        payload = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
        if (not isinstance(payload['expires'], int) or payload['expires'] <= int(time.time())
                or payload['owner'] not in _accounts().values()):
            raise ValueError()
        return payload
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise HTTPException(401, 'Browser session expired; reconnect')


def browser_identity(request: Request):
    value = request.cookies.get(COOKIE)
    if not value:
        raise HTTPException(401, 'Authentication required')
    _local_request(request, require_origin=request.method not in {'GET', 'HEAD', 'OPTIONS'})
    return _decode_session(value)['owner']


def _session_response(expires):
    return {'authenticated': True, 'mode': 'local_beta',
            'account_scope': 'shared_local_development',
            'expires_at': datetime.fromtimestamp(expires, timezone.utc).isoformat()}


def install_beta(app, identity):
    @app.post('/beta/session')
    def create_session(request: Request):
        _local_request(request, require_origin=True)
        accounts = _accounts()
        if not accounts:
            raise HTTPException(503, 'Local development authentication is not configured')
        expires = int(time.time()) + SESSION_SECONDS
        response = JSONResponse(_session_response(expires), headers={'Cache-Control': 'no-store'})
        response.set_cookie(COOKIE, _encode_session(next(iter(accounts.values())), expires),
                            max_age=SESSION_SECONDS, httponly=True, samesite='strict',
                            secure=request.url.scheme == 'https', path='/')
        return response

    @app.get('/beta/session')
    def read_session(request: Request):
        browser_identity(request)
        return JSONResponse(_session_response(_decode_session(request.cookies[COOKIE])['expires']),
                            headers={'Cache-Control': 'no-store'})

    @app.get('/pets')
    def list_pets(user=Depends(identity)):
        with connect() as c:
            rows = c.execute("SELECT id AS pet_id,settings->>'name' AS name,version AS state_version "
                             'FROM pets WHERE owner_id=%s ORDER BY created_at DESC,id', (user,)).fetchall()
        return {'pets': rows}

    @app.get('/pets/{pet}/messages')
    def messages(pet: str, limit: int = Query(default=50, ge=1, le=100), user=Depends(identity)):
        with connect() as c:
            p = owned(c, user, pet)
            # A corrected source still has valid user text. Its derived assistant
            # reply is never resurrected after invalidation. Legacy replies were
            # created only at revision 1, before source_revision was included.
            rows = c.execute('''SELECT s.id AS source_id,s.revision AS source_revision,
                s.payload->>'text' AS "user",s.occurred_at AS created_at,
                e.request_id,e.speech,r.result,
                (e.valid AND r.status='done' AND r.result IS NOT NULL
                 AND r.result->>'source_id'=s.id
                 AND COALESCE((r.result->>'source_revision')::int,1)=s.revision
                 AND NOT EXISTS (
                    SELECT 1 FROM jsonb_array_elements_text(e.memory_ids) AS ref(id)
                    LEFT JOIN memories m ON m.pet_id=e.pet_id AND m.id=ref.id
                    LEFT JOIN sources ms ON ms.pet_id=m.pet_id AND ms.id=m.source_id
                    WHERE m.id IS NULL OR NOT m.valid OR ms.id IS NULL OR NOT ms.valid
                          OR ms.revision<>m.source_revision
                 )) AS reply_valid
                FROM sources s LEFT JOIN exchanges e ON e.pet_id=s.pet_id AND e.source_id=s.id
                LEFT JOIN requests r ON r.pet_id=e.pet_id AND r.id=e.request_id
                WHERE s.pet_id=%s AND s.valid AND s.kind='message'
                ORDER BY s.occurred_at DESC,s.id DESC LIMIT %s''', (pet, limit + 1)).fetchall()
            result = []
            for row in rows[:limit][::-1]:
                saved = row['result'] if row['reply_valid'] else None
                result.append({'request_id': row['request_id'] or row['source_id'].removeprefix('message:'),
                               'source_id': row['source_id'], 'source_revision': row['source_revision'],
                               'user': row['user'], 'assistant': row['speech'] if saved else None,
                               'created_at': row['created_at'],
                               'response': saved.get('response') if saved else None,
                               'execution': saved.get('execution', {}) if saved else {},
                               'metrics': saved.get('metrics') if saved else None})
        return {'pet_id': pet, 'state_version': p['version'], 'limit': limit,
                'has_more': len(rows) > limit, 'messages': result}

    @app.get('/', include_in_schema=False)
    def web_home():
        page = ROOT / 'web' / 'index.html'
        if not page.is_file():
            raise HTTPException(503, 'Browser client is not installed')
        return FileResponse(page, headers={'Cache-Control': 'no-cache'})

    app.mount('/web', StaticFiles(directory=ROOT / 'web', check_dir=False), name='web')
