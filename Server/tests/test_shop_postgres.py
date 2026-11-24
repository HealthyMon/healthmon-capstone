"""Real PostgreSQL tests: atomic debits, concurrent requests and account isolation."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re

from fastapi.testclient import TestClient
import pytest

from Server.healthmon import shop
from Server.healthmon.app import create_app

CHAIN = 'prefab_jewelry_chain_type1_color2'
CHAIN2 = 'prefab_jewelry_chain_type2_color2'
CHARACTER = 'prefab_cute_slime_n3'


def fund(db, pet, coin):
    # An isolated database fixture, never a production funding API.
    with db.connect() as c:
        c.execute('INSERT INTO game_ledger(pet_id,reward_key,exp,coin,reason) VALUES(%s,%s,0,%s,%s)',
                  (pet, 'shop-test-fixture', coin, 'isolated_test_fixture'))


def buy(client, pet, item=CHAIN, request='shop-purchase-001', price=None):
    return client.post(f'/pets/{pet}/shop/purchases', json={
        'request_id': request, 'item_id': item,
        'expected_price': shop.ITEMS[item]['coin_price'] if price is None else price})


def select(client, pet, item=CHARACTER, request='shop-selection-001'):
    return client.put(f'/pets/{pet}/shop/character', json={'request_id': request, 'item_id': item})


def inventory(client, pet):
    result = client.get(f'/pets/{pet}/shop')
    assert result.status_code == 200, result.text
    return result.json()


def test_catalog_matches_all_54_existing_unity_products():
    asset = Path(__file__).resolve().parents[2] / 'Client/HealthMonUnity/Assets/HealthMon/Shop/HealthMonShopCatalog.asset'
    rows = asset.read_text(encoding='utf-8').split('  - itemId: ')[1:]
    assert len(rows) == len(shop.ITEMS) == 54
    for row in rows:
        item = shop.ITEMS[row.splitlines()[0]]
        assert item['coin_price'] == int(re.search(r'    displayCoinPrice: (\d+)', row)[1])
        assert item['category'] == ('accessory' if '\n    category: 0\n' in row else 'character')


def test_purchase_persists_and_ai_is_never_required(client, pet, db, settings, monkeypatch):
    monkeypatch.setattr(client.app.state.gateway, 'assert_available', lambda *args: pytest.fail('Shop contacted AI'))
    fund(db, pet, 500)
    before = inventory(client, pet)
    assert before['owned_item_ids'] == [] and before['selected_character_id'] == ''
    bought = buy(client, pet)
    assert bought.status_code == 200, bought.text
    result = bought.json()
    assert result['success'] and not result['duplicate'] and result['charged_coin'] == 90
    assert result['state']['coin'] == 410 and result['owned_item_ids'] == [CHAIN]
    assert result['state']['state_version'] > before['state']['state_version']
    assert result['state']['model_reference'] == before['state']['model_reference']
    # A new application instance sees the same DB, without client cache/prefs.
    with TestClient(create_app(settings, db)) as restarted:
        restarted.headers['Authorization'] = 'Bearer test-owner-a-token'
        after = inventory(restarted, pet)
        assert after['owned_item_ids'] == [CHAIN] and after['state']['coin'] == 410


def test_duplicate_same_or_new_id_charges_once_and_returns_current_balance(client, pet, db):
    fund(db, pet, 1000)
    first = buy(client, pet).json()
    buy(client, pet, CHAIN2, 'another-purchase')
    retry = buy(client, pet).json()
    assert retry['duplicate'] and retry['charged_coin'] == first['charged_coin'] == 90
    assert retry['state']['coin'] == 820  # Latest state, not a stale receipt snapshot.
    fresh = buy(client, pet, request='new-request-same-item').json()
    assert fresh['already_owned'] and fresh['charged_coin'] == 0 and fresh['state']['coin'] == 820
    with db.connect() as c:
        assert c.execute('SELECT count(*) AS n FROM shop_inventory WHERE pet_id=%s', (pet,)).fetchone()['n'] == 2


@pytest.mark.parametrize('mode', ['same_id', 'new_ids', 'different_items'])
def test_concurrent_purchases_never_double_spend(client, pet, db, mode):
    fund(db, pet, 90)
    def send(i):
        return buy(client, pet, CHAIN2 if mode == 'different_items' and i % 2 else CHAIN,
                   'parallel-same-id' if mode == 'same_id' else f'parallel-{i:08d}')
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(send, range(8)))
    assert all(r.status_code in (200, 409) for r in results)
    if mode != 'different_items':
        assert all(r.status_code == 200 for r in results)
    else:
        assert {r.status_code for r in results} == {200, 409}
    after = inventory(client, pet)
    assert after['state']['coin'] == 0 and len(after['owned_item_ids']) == 1
    with db.connect() as c:
        assert shop.spent(c, pet) == 90


def test_request_id_cannot_be_reused_for_different_item_price_or_operation(client, pet, db):
    fund(db, pet, 1000)
    assert buy(client, pet).status_code == 200
    for response in (buy(client, pet, CHAIN2), buy(client, pet, price=1),
                     select(client, pet, request='shop-purchase-001')):
        assert response.status_code == 409
        assert response.json()['detail']['code'] == 'shop_request_conflict'
    assert inventory(client, pet)['state']['coin'] == 910


def test_insufficient_funds_and_client_price_tampering_leave_no_entitlement(client, pet, db):
    assert buy(client, pet).json()['detail']['code'] == 'shop_insufficient_coin'
    fund(db, pet, 90)
    assert buy(client, pet, price=0).json()['detail']['code'] == 'shop_price_changed'
    assert inventory(client, pet)['owned_item_ids'] == []
    assert buy(client, pet).status_code == 200  # Failed attempt did not consume the ID.
    assert inventory(client, pet)['state']['coin'] == 0


@pytest.mark.parametrize('patch', [{'expected_price': -1}, {'expected_price': 1.5}, {'expected_price': True},
                                   {'coin': 9000}, {'request_id': ''}, {'request_id': 'bad/id'}])
def test_strict_purchase_input(client, pet, patch):
    body = {'request_id': 'strict-input-id', 'item_id': CHAIN, 'expected_price': 90, **patch}
    assert client.post(f'/pets/{pet}/shop/purchases', json=body).status_code == 422


def test_unknown_item_and_selection_guards(client, pet, db):
    assert buy(client, pet, 'unknown-item', price=0).status_code == 404
    assert select(client, pet).json()['detail']['code'] == 'shop_not_owned'
    fund(db, pet, 500)
    buy(client, pet)
    assert select(client, pet, CHAIN).status_code == 422
    assert inventory(client, pet)['selected_character_id'] == ''


def test_selection_persists_and_lost_response_retry_does_not_revert_later_selection(client, pet, db):
    fund(db, pet, 1500)
    other = 'prefab_cute_slime_n4'
    before = inventory(client, pet)['state']['model_reference']
    buy(client, pet, CHARACTER, 'purchase-character-one')
    buy(client, pet, other, 'purchase-character-two')
    first = select(client, pet).json()
    assert first['selected_character_id'] == CHARACTER and first['charged_coin'] == 0
    second = select(client, pet, other, 'select-character-two').json()
    retry = select(client, pet).json()
    assert retry['duplicate'] and retry['selected_character_id'] == other
    assert inventory(client, pet)['selected_character_id'] == other
    assert retry['state']['coin'] == second['state']['coin'] == 800
    assert retry['state']['model_reference'] == before


def test_authentication_and_pet_wallet_isolation(client, pet, db):
    fund(db, pet, 500)
    other_pet = client.post('/pets', json={'name': '별도 지갑'}).json()['pet_id']
    buy(client, pet)
    assert inventory(client, other_pet)['owned_item_ids'] == []
    assert inventory(client, other_pet)['state']['coin'] == 0
    for token, expected in [('test-owner-b-token', 404), ('invalid-token', 401)]:
        client.headers['Authorization'] = 'Bearer ' + token
        assert client.get(f'/pets/{pet}/shop').status_code == expected
        assert buy(client, pet).status_code == expected
        assert select(client, pet).status_code == expected
    client.headers.pop('Authorization')
    assert client.get('/shop/catalog').status_code == 401


def test_transaction_rolls_back_debit_inventory_receipt_and_state_on_failure(client, pet, db, monkeypatch):
    fund(db, pet, 200)
    before = inventory(client, pet)
    original, calls = shop.snapshot, []
    def fail_after_insert(*args):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError('simulated failure before commit')
        return original(*args)
    with monkeypatch.context() as patch:
        patch.setattr(shop, 'snapshot', fail_after_insert)
        with pytest.raises(RuntimeError, match='before commit'):
            buy(client, pet)
    assert inventory(client, pet) == before
    with db.connect() as c:
        assert c.execute('SELECT count(*) AS n FROM shop_requests WHERE pet_id=%s', (pet,)).fetchone()['n'] == 0
    assert buy(client, pet).json()['state']['coin'] == 110


def test_gameplay_reward_and_purchase_share_wallet_lock_and_survive_replay(client, pet, db):
    fund(db, pet, 100)
    at = client.app.state.clock().isoformat()
    workout = {'event_id': 'shop-workout', 'occurred_at': at, 'workout_type': 'walking',
               'actual': 8000, 'unit': 'steps', 'source': 'user'}
    with ThreadPoolExecutor(max_workers=2) as pool:
        purchase = pool.submit(buy, client, pet)
        reward = pool.submit(client.post, f'/pets/{pet}/workouts', json=workout)
        assert purchase.result().status_code == reward.result().status_code == 200
    with db.connect() as c:
        earned = c.execute('SELECT sum(coin) AS coin FROM game_ledger WHERE pet_id=%s', (pet,)).fetchone()['coin']
    for _ in range(3):
        assert client.post(f'/pets/{pet}/workouts', json=workout).status_code == 200
        assert client.get(f'/pets/{pet}/quests').json()['reward_balance'] == earned - 90
        assert inventory(client, pet)['state']['coin'] == earned - 90


def test_test_control_coin_value_remains_exact_after_purchase(client, pet):
    body = dict(level=1, coin=500, upper_body=50, lower_body=50, nutrition=50,
                energy_balance=0, activity=50, affinity=50, initiative=50)
    assert client.put(f'/pets/{pet}/test-controls/state', json=body).status_code == 200
    assert buy(client, pet).json()['state']['coin'] == 410
    body['coin'] = 200
    assert client.put(f'/pets/{pet}/test-controls/state', json=body).json()['coin'] == 200
    assert inventory(client, pet)['state']['coin'] == 200
    assert client.delete(f'/pets/{pet}/test-controls/state').json()['coin'] == 0


def test_pet_erasure_cascades_shop_data(client, pet, db):
    fund(db, pet, 1000)
    buy(client, pet, CHARACTER)
    select(client, pet)
    assert client.delete(f'/pets/{pet}').status_code == 200
    with db.connect() as c:
        for table in ('shop_inventory', 'shop_selection', 'shop_requests'):
            assert c.execute(f'SELECT count(*) AS n FROM {table} WHERE pet_id=%s', (pet,)).fetchone()['n'] == 0


def test_migration_can_be_repeated_without_losing_purchase(client, pet, db):
    fund(db, pet, 100)
    buy(client, pet)
    db.migrate()
    assert inventory(client, pet)['owned_item_ids'] == [CHAIN]
    assert inventory(client, pet)['state']['coin'] == 10
