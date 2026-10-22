"""Explicit loopback capability routing for isolated native acceptance only.

Chat/embedding and 3D models occupy the same single GPU sequentially. This CPU
router preserves one AI origin while forwarding only the declared capabilities.
It neither creates fallback output nor exposes a user-facing inference service.
"""
import argparse
import hmac
import json
from pathlib import Path
import re

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import Response
import httpx

CAPABILITY_ORIGINS = {'chat': 'http://127.0.0.1:18091', 'embedding': 'http://127.0.0.1:18091',
                      'food': 'http://127.0.0.1:18094', 'evolutions': 'http://127.0.0.1:18093'}
DEFAULT_REQUEST_LIMIT = 2 * 1024 * 1024
# The common server accepts 12 MiB of raw JPEG/PNG. Base64 expands this to
# 16 MiB, so retain bounded room for its four-field JSON request envelope.
FOOD_REQUEST_LIMIT = 17 * 1024 * 1024


def create_app(key_file):
    token = json.loads(Path(key_file).read_text(encoding='utf-8'))['server_token']
    app = FastAPI(title='Isolated native acceptance capability router')

    @app.get('/health')
    def health():
        return {'status': 'ok', 'local_acceptance_only': True, 'automatic_fallback': False,
                'configured_capability_origins': dict(CAPABILITY_ORIGINS),
                'food_json_request_limit_bytes': FOOD_REQUEST_LIMIT}

    @app.api_route('/v1/{path:path}', methods=['POST', 'PUT', 'GET'])
    async def route(path: str, request: Request, authorization: str = Header(default='')):
        if not authorization.startswith('Bearer ') or not hmac.compare_digest(authorization[7:], token):
            raise HTTPException(401, 'Server authentication required')
        if path in ('chat', 'embedding', 'food') and request.method == 'POST':
            capability = path
        elif re.fullmatch(r'evolutions/[A-Za-z0-9_-]{1,128}', path) and request.method in ('PUT', 'GET'):
            capability = 'evolutions'
        elif re.fullmatch(r'assets/[A-Za-z0-9_-]{1,128}/model\.glb', path) and request.method == 'GET':
            capability = 'evolutions'
        else:
            raise HTTPException(404, 'Capability is not configured')
        base = CAPABILITY_ORIGINS[capability]
        limit = FOOD_REQUEST_LIMIT if capability == 'food' else DEFAULT_REQUEST_LIMIT
        declared = request.headers.get('content-length')
        if declared is not None:
            try:
                length = int(declared)
            except ValueError:
                raise HTTPException(400, 'Invalid Content-Length') from None
            if length < 0:
                raise HTTPException(400, 'Invalid Content-Length')
            if length > limit:
                raise HTTPException(413, 'Request is too large')
        content = bytearray()
        async for chunk in request.stream():
            if len(content) + len(chunk) > limit:
                raise HTTPException(413, 'Request is too large')
            content.extend(chunk)
        try:
            async with httpx.AsyncClient(timeout=180, trust_env=False, follow_redirects=False) as client:
                reply = await client.request(request.method, base + '/v1/' + path, content=bytes(content),
                                             headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
                if len(reply.content) > 64 * 1024 * 1024:
                    raise HTTPException(502, 'Upstream asset exceeds the declared limit')
        except httpx.HTTPError:
            raise HTTPException(503, 'The selected real capability is unavailable') from None
        return Response(reply.content, status_code=reply.status_code,
                        media_type=reply.headers.get('content-type', 'application/json'),
                        headers={'Cache-Control': 'private, no-store'})

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--key-config', type=Path, required=True)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(create_app(args.key_config), host='127.0.0.1', port=18090, access_log=False)


if __name__ == '__main__':
    main()
