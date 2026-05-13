import os
import sqlite3
import uuid
from contextlib import contextmanager

from werkzeug.security import generate_password_hash


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
HASH_METHOD = "pbkdf2:sha256:180000"
SQLITE_PATH = os.getenv(
    "SQLITE_PATH",
    os.path.join(os.path.dirname(__file__), "russian_market.db"),
)


def using_postgres():
    return bool(DATABASE_URL)


def _translate(sql):
    if using_postgres():
        return sql.replace("?", "%s")
    return sql


def _connect():
    if using_postgres():
        from psycopg import connect
        from psycopg.rows import dict_row

        return connect(DATABASE_URL, row_factory=dict_row)

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _dict(row):
    if row is None:
        return None
    return dict(row)


@contextmanager
def connection():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query_all(sql, params=()):
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(_translate(sql), params)
        return [_dict(row) for row in cur.fetchall()]


def query_one(sql, params=()):
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(_translate(sql), params)
        return _dict(cur.fetchone())


def execute(sql, params=()):
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(_translate(sql), params)
        return cur.rowcount


def insert(table, data):
    keys = list(data.keys())
    placeholders = ", ".join(["?"] * len(keys))
    columns = ", ".join(keys)
    values = tuple(data[key] for key in keys)

    with connection() as conn:
        cur = conn.cursor()
        if using_postgres():
            cur.execute(
                _translate(
                    f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING id"
                ),
                values,
            )
            return cur.fetchone()["id"]

        cur.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", values)
        return cur.lastrowid


def init_db():
    with connection() as conn:
        cur = conn.cursor()
        if using_postgres():
            statements = [
                """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    public_id TEXT UNIQUE,
                    profile_name TEXT,
                    password_hash TEXT NOT NULL,
                    balance NUMERIC(12,2) NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """,
                """
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
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS crypto_addresses (
                    id SERIAL PRIMARY KEY,
                    currency TEXT NOT NULL,
                    network TEXT NOT NULL,
                    address TEXT NOT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS deposits (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    currency TEXT NOT NULL,
                    txid TEXT NOT NULL,
                    amount NUMERIC(12,2) NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    reviewed_at TIMESTAMPTZ
                )
                """,
                """
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
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS card_stock (
                    id SERIAL PRIMARY KEY,
                    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
                    details TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'available',
                    order_id INTEGER REFERENCES orders(id) ON DELETE SET NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    sold_at TIMESTAMPTZ
                )
                """,
                """
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
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS admin_credentials (
                    id SERIAL PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """,
            ]
        else:
            statements = [
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    public_id TEXT UNIQUE,
                    profile_name TEXT,
                    password_hash TEXT NOT NULL,
                    balance REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    country TEXT NOT NULL,
                    country_code TEXT NOT NULL DEFAULT 'us',
                    network TEXT NOT NULL,
                    price REAL NOT NULL,
                    preload REAL NOT NULL,
                    city TEXT NOT NULL,
                    masked_number TEXT NOT NULL,
                    expiry TEXT NOT NULL,
                    full_details TEXT NOT NULL,
                    display_stock INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'in_stock',
                    image_filename TEXT,
                    image_mime TEXT,
                    image_data TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS crypto_addresses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    currency TEXT NOT NULL,
                    network TEXT NOT NULL,
                    address TEXT NOT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS deposits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    currency TEXT NOT NULL,
                    txid TEXT NOT NULL,
                    amount REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    reviewed_at TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    card_id INTEGER NOT NULL,
                    price REAL NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    delivered_details TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    approved_at TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(card_id) REFERENCES cards(id)
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS card_stock (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    card_id INTEGER NOT NULL,
                    details TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'available',
                    order_id INTEGER,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    sold_at TEXT,
                    FOREIGN KEY(card_id) REFERENCES cards(id),
                    FOREIGN KEY(order_id) REFERENCES orders(id)
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS custom_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    card_type TEXT NOT NULL,
                    country TEXT,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    budget REAL NOT NULL DEFAULT 0,
                    notes TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    reviewed_at TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS admin_credentials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS site_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """,
            ]

        for statement in statements:
            cur.execute(statement)

    ensure_user_columns()
    ensure_card_image_columns()
    ensure_order_columns()
    ensure_site_settings_table()
    ensure_indexes()
    seed_admin_credentials()
    seed_defaults()


def _public_id():
    return "RM" + uuid.uuid4().hex[:8].upper()


def ensure_user_columns():
    with connection() as conn:
        cur = conn.cursor()
        if using_postgres():
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'users'
                """
            )
            columns = {row["column_name"] for row in cur.fetchall()}
            if "profile_name" not in columns:
                cur.execute("ALTER TABLE users ADD COLUMN profile_name TEXT")
                cur.execute("UPDATE users SET profile_name = username WHERE profile_name IS NULL")
            if "public_id" not in columns:
                cur.execute("ALTER TABLE users ADD COLUMN public_id TEXT")
        else:
            cur.execute("PRAGMA table_info(users)")
            columns = {row["name"] for row in cur.fetchall()}
            if "profile_name" not in columns:
                cur.execute("ALTER TABLE users ADD COLUMN profile_name TEXT")
                cur.execute("UPDATE users SET profile_name = username WHERE profile_name IS NULL")
            if "public_id" not in columns:
                cur.execute("ALTER TABLE users ADD COLUMN public_id TEXT")

        cur.execute("SELECT id FROM users WHERE public_id IS NULL OR public_id = ''")
        missing = cur.fetchall()
        for row in missing:
            cur.execute(_translate("UPDATE users SET public_id = ? WHERE id = ?"), (_public_id(), row["id"]))


def ensure_card_image_columns():
    wanted = {
        "image_mime": "TEXT",
        "image_data": "TEXT",
        "display_stock": "INTEGER NOT NULL DEFAULT 0",
    }
    with connection() as conn:
        cur = conn.cursor()
        if using_postgres():
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'cards'
                """
            )
            columns = {row["column_name"] for row in cur.fetchall()}
        else:
            cur.execute("PRAGMA table_info(cards)")
            columns = {row["name"] for row in cur.fetchall()}

        for column, column_type in wanted.items():
            if column not in columns:
                cur.execute(f"ALTER TABLE cards ADD COLUMN {column} {column_type}")


def ensure_order_columns():
    wanted = {"quantity": "INTEGER NOT NULL DEFAULT 1", "delivered_details": "TEXT"}
    with connection() as conn:
        cur = conn.cursor()
        if using_postgres():
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'orders'
                """
            )
            columns = {row["column_name"] for row in cur.fetchall()}
        else:
            cur.execute("PRAGMA table_info(orders)")
            columns = {row["name"] for row in cur.fetchall()}

        for column, column_type in wanted.items():
            if column not in columns:
                cur.execute(f"ALTER TABLE orders ADD COLUMN {column} {column_type}")


def ensure_site_settings_table():
    if using_postgres():
        execute(
            """
            CREATE TABLE IF NOT EXISTS site_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )


def ensure_indexes():
    statements = [
        "CREATE INDEX IF NOT EXISTS idx_users_public_id ON users(public_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_public_id_unique ON users(public_id)",
        "CREATE INDEX IF NOT EXISTS idx_orders_user_status ON orders(user_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_deposits_user_status ON deposits(user_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_card_stock_card_status ON card_stock(card_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_custom_orders_user_status ON custom_orders(user_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_cards_status_network ON cards(status, network)",
    ]
    with connection() as conn:
        cur = conn.cursor()
        for statement in statements:
            cur.execute(statement)


def seed_admin_credentials():
    if query_one("SELECT id FROM admin_credentials ORDER BY id LIMIT 1"):
        return

    username = os.getenv("ADMIN_USERNAME", "admin").strip() or "admin"
    password = os.getenv("ADMIN_PASSWORD", "admin123").strip() or "admin123"
    insert(
        "admin_credentials",
        {
            "username": username,
            "password_hash": generate_password_hash(password, method=HASH_METHOD),
        },
    )


def seed_defaults():
    if not query_one("SELECT key FROM site_settings WHERE key = ?", ("helper_email",)):
        execute(
            "INSERT INTO site_settings (key, value) VALUES (?, ?)",
            ("helper_email", "support@example.com"),
        )

    if not query_one("SELECT id FROM crypto_addresses LIMIT 1"):
        enabled_value = True if using_postgres() else 1
        addresses = [
            {
                "currency": "USDT",
                "network": "TRC20",
                "address": "TQXU6EaiJy67y2kXT3HUjq2JcuWmRe9X9V",
                "sort_order": 1,
                "enabled": enabled_value,
            },
            {
                "currency": "ETH",
                "network": "ERC20",
                "address": "0x11380946707964fa06e75b3d5d5d545755be49e20",
                "sort_order": 2,
                "enabled": enabled_value,
            },
            {
                "currency": "BTC",
                "network": "Bitcoin",
                "address": "1JmTnCepKpo8efTPrUw8HBNPnsqSzY2rp",
                "sort_order": 3,
                "enabled": enabled_value,
            },
        ]
        for address in addresses:
            insert("crypto_addresses", address)

    if not query_one("SELECT id FROM cards LIMIT 1"):
        cards = [
            ("USA", "us", "Mastercard", 80, 2400, "New York", "5441 7074 **** ****", "03/27"),
            ("Canada", "ca", "Amex", 90, 3100, "Toronto", "3098 1333 **** ****", "08/27"),
            ("UAE", "ae", "Visa", 75, 1600, "Dubai", "4754 2446 **** ****", "07/29"),
            ("USA", "us", "Amex", 110, 4700, "Chicago", "3200 9154 **** ****", "03/27"),
            ("Canada", "ca", "Mastercard", 78, 2000, "Montreal", "5974 9213 **** ****", "02/29"),
            ("UK", "gb", "Visa", 125, 5200, "Coming soon", "4417 2097 **** ****", "09/28"),
            ("Singapore", "sg", "Mastercard", 140, 7000, "Coming soon", "5174 0188 **** ****", "01/29"),
        ]
        for country, code, network, price, preload, city, masked, expiry in cards:
            status = "upcoming" if city == "Coming soon" else "in_stock"
            insert(
                "cards",
                {
                    "country": country,
                    "country_code": code,
                    "network": network,
                    "price": price,
                    "preload": preload,
                    "city": city,
                    "masked_number": masked,
                    "expiry": expiry,
                    "full_details": (
                        f"{country} {network}\n"
                        f"Card: {masked.replace('**** ****', '4821 9147')}\n"
                        f"Expiry: {expiry}\n"
                        "CVV: 742\n"
                        f"City: {city}\n"
                        "Status: Approved by admin"
                    ),
                    "display_stock": 7 if status == "in_stock" else 0,
                    "status": status,
                    "image_filename": None,
                },
            )
