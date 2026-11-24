"""Server-owned catalog, wallet debits and idempotent non-consumable purchases.

Every read/mutation holds the same pet lock as workouts and quest reconciliation.
No AI service is used; entitlement, debit, receipt and state commit together.
"""
import json
from pathlib import Path

from fastapi import Depends, HTTPException
from psycopg.types.json import Jsonb
from pydantic import Field

from . import service
from .contracts import Strict

CATALOG = json.loads(Path(__file__).with_name('shop_catalog.json').read_text(encoding='utf-8'))
ITEMS = {item['item_id']: item for item in CATALOG['items']}
DEFAULT_IDS = [item['item_id'] for item in ITEMS.values() if item['included_by_default']]
# Empty selection means the pet's current starter (the existing slime).
DEFAULT_CHARACTER = next((item['item_id'] for item in ITEMS.values()
                          if item['category'] == 'character' and item['included_by_default']), '')


class Purchase(Strict):
    request_id: str = Field(min_length=8, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')
    item_id: str = Field(min_length=1, max_length=100)
    expected_price: int = Field(ge=0, le=1000000, strict=True)


class Selection(Strict):
    request_id: str = Field(min_length=8, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')
    item_id: str = Field(min_length=1, max_length=100)


def spent(c, pet):
    return c.execute('SELECT coalesce(sum(paid_coin),0) AS spent FROM shop_inventory WHERE pet_id=%s', (pet,)).fetchone()['spent']


def snapshot(c, p, timestamp, available):
    # Re-read the version after a preceding refresh in the same transaction.
    p = service.owned(c, p['owner_id'], p['id'], True)
    state, _ = service.refresh(c, p, timestamp, available)
    owned = set(DEFAULT_IDS)
    owned.update(row['item_id'] for row in c.execute('SELECT item_id FROM shop_inventory WHERE pet_id=%s', (p['id'],)))
    selected = c.execute('SELECT character_id FROM shop_selection WHERE pet_id=%s', (p['id'],)).fetchone()
    return {'pet_id': p['id'], 'catalog_version': CATALOG['version'], 'items': CATALOG['items'],
            'owned_item_ids': sorted(owned), 'selected_character_id': selected['character_id'] if selected else DEFAULT_CHARACTER,
            'state': state}


def register(app, settings, db, identity, now):
    @app.get('/shop/catalog')
    def catalog(owner=Depends(identity)):
        return CATALOG

    @app.get('/pets/{pet}/shop')
    def inventory(pet: str, owner=Depends(identity)):
        with db.connect() as c:
            return snapshot(c, service.owned(c, owner, pet, True), now(), settings.chat_available(owner))

    def mutate(pet, owner, body, operation):
        timestamp, available = now(), settings.chat_available(owner)
        key = service.fingerprint({'operation': operation, **body.model_dump()})
        with db.connect() as c:
            p = service.owned(c, owner, pet, True)
            prior = c.execute('SELECT fingerprint,receipt FROM shop_requests WHERE pet_id=%s AND request_id=%s',
                              (pet, body.request_id)).fetchone()
            if prior:
                if prior['fingerprint'] != key:
                    raise HTTPException(409, {'code': 'shop_request_conflict'})
                return dict(prior['receipt'], duplicate=True, **snapshot(c, p, timestamp, available))
            item = ITEMS.get(body.item_id)
            if item is None:
                raise HTTPException(404, {'code': 'shop_item_not_found'})
            before = snapshot(c, p, timestamp, available)
            owned = body.item_id in before['owned_item_ids']
            charged = 0
            if operation == 'purchase':
                # Already owned is a successful no-op, even with a new request ID.
                if not owned:
                    if body.expected_price != item['coin_price']:
                        raise HTTPException(409, {'code': 'shop_price_changed'})
                    if before['state']['coin'] < item['coin_price']:
                        raise HTTPException(409, {'code': 'shop_insufficient_coin'})
                    charged = item['coin_price']
                    c.execute('INSERT INTO shop_inventory(pet_id,item_id,paid_coin,acquired_at) VALUES(%s,%s,%s,%s)',
                              (pet, body.item_id, charged, timestamp))
            else:
                if item['category'] != 'character':
                    raise HTTPException(422, {'code': 'shop_not_character'})
                if not owned:
                    raise HTTPException(409, {'code': 'shop_not_owned'})
                c.execute('INSERT INTO shop_selection(pet_id,character_id,updated_at) VALUES(%s,%s,%s) '
                          'ON CONFLICT(pet_id) DO UPDATE SET character_id=excluded.character_id,updated_at=excluded.updated_at',
                          (pet, body.item_id, timestamp))
            receipt = {'success': True, 'request_id': body.request_id, 'item_id': body.item_id,
                       'operation': operation, 'charged_coin': charged, 'already_owned': owned}
            c.execute('INSERT INTO shop_requests(pet_id,request_id,fingerprint,receipt,created_at) VALUES(%s,%s,%s,%s,%s)',
                      (pet, body.request_id, key, Jsonb(receipt), timestamp))
            return dict(receipt, duplicate=False, **snapshot(c, p, timestamp, available))

    @app.post('/pets/{pet}/shop/purchases')
    def purchase(pet: str, body: Purchase, owner=Depends(identity)):
        return mutate(pet, owner, body, 'purchase')

    @app.put('/pets/{pet}/shop/character')
    def select_character(pet: str, body: Selection, owner=Depends(identity)):
        return mutate(pet, owner, body, 'select_character')
