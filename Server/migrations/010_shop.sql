-- Purchases are durable, non-consumable entitlements scoped to the pet wallet.
-- Keep reward ledger entries positive; purchase debits are accounted separately.
CREATE TABLE shop_inventory (
 pet_id text NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
 item_id text NOT NULL, paid_coin int NOT NULL CHECK(paid_coin >= 0),
 acquired_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(pet_id,item_id)
);
CREATE TABLE shop_selection (
 pet_id text PRIMARY KEY REFERENCES pets(id) ON DELETE CASCADE,
 character_id text NOT NULL, updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE shop_requests (
 pet_id text NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
 request_id text NOT NULL, fingerprint text NOT NULL, receipt jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(pet_id,request_id)
);
