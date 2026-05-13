BEGIN;

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    public_id TEXT UNIQUE,
    profile_name TEXT,
    password_hash TEXT NOT NULL,
    balance NUMERIC(12,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cards (
    id SERIAL PRIMARY KEY,
    country TEXT NOT NULL,
    country_code TEXT NOT NULL DEFAULT 'us',
    network TEXT NOT NULL,
    price NUMERIC(12,2) NOT NULL,
    preload NUMERIC(12,2) NOT NULL,
    city TEXT NOT NULL,
    masked_number TEXT NOT NULL,
    expiry TEXT NOT NULL,
    full_details TEXT NOT NULL,
    display_stock INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'in_stock',
    image_filename TEXT,
    image_mime TEXT,
    image_data TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS crypto_addresses (
    id SERIAL PRIMARY KEY,
    currency TEXT NOT NULL,
    network TEXT NOT NULL,
    address TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS deposits (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    currency TEXT NOT NULL,
    txid TEXT NOT NULL,
    amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE RESTRICT,
    price NUMERIC(12,2) NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    delivered_details TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS card_stock (
    id SERIAL PRIMARY KEY,
    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    details TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'available',
    order_id INTEGER REFERENCES orders(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sold_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS custom_orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    card_type TEXT NOT NULL,
    country TEXT,
    quantity INTEGER NOT NULL DEFAULT 1,
    budget NUMERIC(12,2) NOT NULL DEFAULT 0,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS admin_credentials (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS site_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS public_id TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_name TEXT;
ALTER TABLE cards ADD COLUMN IF NOT EXISTS image_mime TEXT;
ALTER TABLE cards ADD COLUMN IF NOT EXISTS image_data TEXT;
ALTER TABLE cards ADD COLUMN IF NOT EXISTS display_stock INTEGER NOT NULL DEFAULT 0;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS quantity INTEGER NOT NULL DEFAULT 1;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivered_details TEXT;

INSERT INTO site_settings (key, value)
VALUES ('helper_email', 'support@example.com')
ON CONFLICT (key) DO NOTHING;

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_public_id_unique ON users(public_id);
CREATE INDEX IF NOT EXISTS idx_users_login_lower ON users(LOWER(username));
CREATE INDEX IF NOT EXISTS idx_admin_login_lower ON admin_credentials(LOWER(username));
CREATE INDEX IF NOT EXISTS idx_users_public_id ON users(public_id);
CREATE INDEX IF NOT EXISTS idx_cards_status_network ON cards(status, network);
CREATE INDEX IF NOT EXISTS idx_cards_visible_order ON cards(status, id DESC);
CREATE INDEX IF NOT EXISTS idx_crypto_enabled_order ON crypto_addresses(enabled, sort_order, id);
CREATE INDEX IF NOT EXISTS idx_orders_user_status ON orders(user_id, status);
CREATE INDEX IF NOT EXISTS idx_orders_pending ON orders(status, id DESC);
CREATE INDEX IF NOT EXISTS idx_deposits_user_status ON deposits(user_id, status);
CREATE INDEX IF NOT EXISTS idx_deposits_pending ON deposits(status, id DESC);
CREATE INDEX IF NOT EXISTS idx_card_stock_card_status ON card_stock(card_id, status);
CREATE INDEX IF NOT EXISTS idx_custom_orders_user_status ON custom_orders(user_id, status);
CREATE INDEX IF NOT EXISTS idx_custom_orders_pending ON custom_orders(status, id DESC);

COMMIT;

ANALYZE;
