import os
import sqlite3
from contextlib import contextmanager

from werkzeug.security import generate_password_hash


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
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
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    approved_at TIMESTAMPTZ
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
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    approved_at TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(card_id) REFERENCES cards(id)
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
            ]

        for statement in statements:
            cur.execute(statement)

    ensure_profile_name_column()
    ensure_card_image_columns()
    seed_admin_credentials()
    seed_defaults()


def ensure_profile_name_column():
    with connection() as conn:
        cur = conn.cursor()
        if using_postgres():
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'profile_name'
                """
            )
            has_column = cur.fetchone() is not None
            if not has_column:
                cur.execute("ALTER TABLE users ADD COLUMN profile_name TEXT")
                cur.execute("UPDATE users SET profile_name = username WHERE profile_name IS NULL")
        else:
            cur.execute("PRAGMA table_info(users)")
            columns = [row["name"] for row in cur.fetchall()]
            if "profile_name" not in columns:
                cur.execute("ALTER TABLE users ADD COLUMN profile_name TEXT")
                cur.execute("UPDATE users SET profile_name = username WHERE profile_name IS NULL")


def ensure_card_image_columns():
    wanted = {"image_mime": "TEXT", "image_data": "TEXT"}
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


def seed_admin_credentials():
    if query_one("SELECT id FROM admin_credentials ORDER BY id LIMIT 1"):
        return

    username = os.getenv("ADMIN_USERNAME", "admin").strip() or "admin"
    password = os.getenv("ADMIN_PASSWORD", "admin123").strip() or "admin123"
    insert(
        "admin_credentials",
        {
            "username": username,
            "password_hash": generate_password_hash(password),
        },
    )


def seed_defaults():
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
                    "status": status,
                    "image_filename": None,
                },
            )
