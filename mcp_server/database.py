# mcp_server/database.py
import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "database/retail.db")

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS customers (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                email       TEXT UNIQUE NOT NULL,
                phone       TEXT,
                segment     TEXT,
                preferences TEXT,
                notes       TEXT
            );

            CREATE TABLE IF NOT EXISTS orders (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id     INTEGER NOT NULL,
                order_number    TEXT UNIQUE NOT NULL,
                status          TEXT NOT NULL,
                total_amount    REAL NOT NULL,
                items           TEXT NOT NULL,
                created_at      TEXT NOT NULL,
                delivered_at    TEXT,
                refund_eligible INTEGER DEFAULT 1,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );

            CREATE TABLE IF NOT EXISTS support_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                issue       TEXT NOT NULL,
                resolution  TEXT,
                created_at  TEXT NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );
        """)
        await db.commit()
    print("Database initialized.")