"""Bounded live dependency observations, separate from database/API readiness."""
import threading
import time

import httpx


class AIDependencies:
    def __init__(self, settings):
        self.settings = settings
        self._lock = threading.Lock()
        self._expires = 0
        self._value = None

    @staticmethod
    def unavailable(status):
        return {'status': status, 'available': False,
                'services': {name: {'status': status, 'available': False}
                             for name in ('chat', 'vision', 'evolution')}}

    def snapshot(self, owner):
        settings = self.settings
        if settings.ai_mode == 'disabled':
            return self.unavailable('disabled')
        if settings.ai_mode == 'mock':
            allowed = settings.chat_available(owner)
            return {'status': 'synthetic' if allowed else 'disabled', 'available': allowed,
                    'services': {name: {'status': 'synthetic' if allowed else 'disabled', 'available': allowed}
                                 for name in ('chat', 'vision', 'evolution')}}
        # A single short probe per CPU process / two seconds, including failures.
        # Health reporting never updates chat evidence or rejects real retries.
        with self._lock:
            if time.monotonic() < self._expires:
                return self._value
            try:
                with httpx.Client(timeout=2, trust_env=False, follow_redirects=False) as client:
                    response = client.get(settings.ai_base_url + '/health/services',
                                          headers={'Authorization': 'Bearer ' + settings.ai_token})
                    if response.status_code == 404:
                        value = {'status': 'unknown', 'available': None, 'services': {}}
                    else:
                        response.raise_for_status()
                        body = response.json()
                        states = {'ready', 'loading', 'generating_3d', 'stopping', 'off', 'error'}
                        if body.get('status') not in states or not isinstance(body.get('services'), dict):
                            raise ValueError('Invalid service health response')
                        entries = {}
                        for name in ('chat', 'vision', 'evolution'):
                            item = body['services'].get(name, {})
                            if item.get('status') not in states or type(item.get('available')) is not bool:
                                raise ValueError('Invalid capability health response')
                            entries[name] = {'status': item['status'], 'available': item['available']}
                        value = {'status': body['status'], 'available': body['status'] == 'ready' and all(x['available'] for x in entries.values()), 'services': entries}
            except (httpx.ConnectError, httpx.ConnectTimeout):
                value = self.unavailable('off')
            except (httpx.HTTPError, ValueError, TypeError, AttributeError):
                value = self.unavailable('error')
            self._value, self._expires = value, time.monotonic() + 2
            return value
