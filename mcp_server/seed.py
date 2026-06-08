# mcp_server/seed.py
import asyncio
import json
import aiosqlite
from mcp_server.database import DB_PATH, init_db

CUSTOMERS = [
    {
        "name": "Shaheer Ahmed",
        "email": "shaheer@example.com",
        "phone": "+92-300-1234567",
        "segment": "vip",
        "preferences": json.dumps({"contact": "whatsapp", "notifications": "whatsapp", "language": "en"}),
    },
    {
        "name": "Aisha Khan",
        "email": "aisha@example.com",
        "phone": "+92-321-9876543",
        "segment": "vip",
        "preferences": json.dumps({"contact": "email", "notifications": "email", "language": "en"}),
    },
    {
        "name": "James Miller",
        "email": "james@example.com",
        "phone": "+1-555-0101",
        "segment": "regular",
        "preferences": json.dumps({"contact": "sms", "notifications": "sms", "language": "en"}),
    },
    {
        "name": "Fatima Zahra",
        "email": "fatima@example.com",
        "phone": "+212-600-123456",
        "segment": "new",
        "preferences": json.dumps({"contact": "email", "notifications": "email", "language": "fr"}),
    },
    {
        "name": "Carlos Rivera",
        "email": "carlos@example.com",
        "phone": "+1-555-0202",
        "segment": "regular",
        "preferences": json.dumps({"contact": "phone", "notifications": "email", "language": "es"}),
    },
    {
        "name": "Priya Patel",
        "email": "priya@example.com",
        "phone": "+91-98765-43210",
        "segment": "vip",
        "preferences": json.dumps({"contact": "email", "notifications": "email", "language": "en"}),
    },
    {
        "name": "Omar Siddiqui",
        "email": "omar@example.com",
        "phone": "+92-333-5556677",
        "segment": "regular",
        "preferences": json.dumps({"contact": "whatsapp", "notifications": "whatsapp", "language": "en"}),
    },
    {
        "name": "Emily Chen",
        "email": "emily@example.com",
        "phone": "+1-555-0303",
        "segment": "new",
        "preferences": json.dumps({"contact": "email", "notifications": "email", "language": "en"}),
    },
    {
        "name": "David Okonkwo",
        "email": "david@example.com",
        "phone": "+234-802-3456789",
        "segment": "regular",
        "preferences": json.dumps({"contact": "sms", "notifications": "sms", "language": "en"}),
    },
    {
        "name": "Sofia Rossi",
        "email": "sofia@example.com",
        "phone": "+39-333-1234567",
        "segment": "vip",
        "preferences": json.dumps({"contact": "email", "notifications": "email", "language": "it"}),
    },
]

ORDERS = [
    # Shaheer Ahmed (id=1) - VIP, WhatsApp
    ("shaheer@example.com", "ORD-1001", "delivered", 250.00,
     json.dumps([{"item": "Wireless Headphones", "qty": 1, "price": 250.00}]),
     "2025-05-01", "2025-05-04", 1),
    ("shaheer@example.com", "ORD-1002", "delivered", 1200.00,
     json.dumps([{"item": "Laptop Stand", "qty": 1, "price": 200.00}, {"item": "Mechanical Keyboard", "qty": 1, "price": 1000.00}]),
     "2025-05-20", "2025-05-23", 1),

    # Aisha Khan (id=2) - VIP, damaged delivery complaint
    ("aisha@example.com", "ORD-1003", "delivered", 89.99,
     json.dumps([{"item": "Silk Scarf", "qty": 1, "price": 89.99}]),
     "2025-01-10", "2025-01-15", 0),  # refund_eligible=0, already resolved with store credit
    ("aisha@example.com", "ORD-1004", "delivered", 340.00,
     json.dumps([{"item": "Leather Handbag", "qty": 1, "price": 340.00}]),
     "2025-04-05", "2025-04-08", 1),

    # James Miller (id=3) - Regular, SMS
    ("james@example.com", "ORD-1005", "delivered", 55.00,
     json.dumps([{"item": "Phone Case", "qty": 2, "price": 27.50}]),
     "2025-03-15", "2025-03-18", 1),
    ("james@example.com", "ORD-1006", "processing", 120.00,
     json.dumps([{"item": "Bluetooth Speaker", "qty": 1, "price": 120.00}]),
     "2025-06-01", None, 0),

    # Fatima Zahra (id=4) - New customer
    ("fatima@example.com", "ORD-1007", "delivered", 45.00,
     json.dumps([{"item": "Notebook Set", "qty": 3, "price": 15.00}]),
     "2025-05-28", "2025-05-31", 1),

    # Carlos Rivera (id=5) - Regular, delayed shipments
    ("carlos@example.com", "ORD-1008", "delayed", 310.00,
     json.dumps([{"item": "Running Shoes", "qty": 1, "price": 310.00}]),
     "2025-05-25", None, 1),
    ("carlos@example.com", "ORD-1009", "delivered", 75.00,
     json.dumps([{"item": "Water Bottle", "qty": 1, "price": 75.00}]),
     "2025-04-10", "2025-04-14", 1),

    # Priya Patel (id=6) - VIP, priority, escalated refund before
    ("priya@example.com", "ORD-1010", "refunded", 599.00,
     json.dumps([{"item": "Smartwatch", "qty": 1, "price": 599.00}]),
     "2025-02-14", "2025-02-20", 0),  # already refunded
    ("priya@example.com", "ORD-1011", "delivered", 850.00,
     json.dumps([{"item": "Designer Sunglasses", "qty": 1, "price": 850.00}]),
     "2025-05-10", "2025-05-13", 1),

    # Omar Siddiqui (id=7) - Regular, store credit loyalist
    ("omar@example.com", "ORD-1012", "delivered", 430.00,
     json.dumps([{"item": "Gaming Mouse", "qty": 1, "price": 130.00}, {"item": "Monitor", "qty": 1, "price": 300.00}]),
     "2025-03-20", "2025-03-24", 1),
    ("omar@example.com", "ORD-1013", "delivered", 220.00,
     json.dumps([{"item": "USB Hub", "qty": 2, "price": 110.00}]),
     "2025-04-28", "2025-05-01", 1),

    # Emily Chen (id=8) - New customer
    ("emily@example.com", "ORD-1014", "processing", 95.00,
     json.dumps([{"item": "Yoga Mat", "qty": 1, "price": 95.00}]),
     "2025-06-03", None, 0),

    # David Okonkwo (id=9) - Fraud flag
    ("david@example.com", "ORD-1015", "delivered", 180.00,
     json.dumps([{"item": "Sunglasses", "qty": 1, "price": 180.00}]),
     "2025-03-01", "2025-03-05", 1),
    ("david@example.com", "ORD-1016", "delivered", 620.00,
     json.dumps([{"item": "Camera Lens", "qty": 1, "price": 620.00}]),
     "2025-05-15", "2025-05-19", 1),

    # Sofia Rossi (id=10) - VIP Italy, luxury
    ("sofia@example.com", "ORD-1017", "delivered", 1500.00,
     json.dumps([{"item": "Diamond Bracelet", "qty": 1, "price": 1500.00}]),
     "2025-04-20", "2025-04-25", 1),
    ("sofia@example.com", "ORD-1018", "delivered", 980.00,
     json.dumps([{"item": "Italian Leather Wallet", "qty": 2, "price": 490.00}]),
     "2025-05-30", "2025-06-03", 1),
]

SUPPORT_HISTORY = [
    ("aisha@example.com", "Package arrived damaged — silk scarf order ORD-1003", "Offered store credit of $90. Customer accepted.", "2025-01-16"),
    ("carlos@example.com", "Shipment delayed — no updates received", "Apologized and provided tracking info. Offered 10% discount on next order.", "2025-04-15"),
    ("carlos@example.com", "Second delayed shipment complaint — ORD-1008", "Escalated to logistics team. Customer offered priority shipping on next order.", "2025-05-26"),
    ("priya@example.com", "Smartwatch ORD-1010 stopped working after 2 weeks", "Escalated to returns team. Full refund processed.", "2025-02-22"),
    ("omar@example.com", "Item not as described — requested refund", "Offered store credit instead. Customer accepted.", "2025-03-25"),
    ("omar@example.com", "Wrong item delivered — USB hub order", "Offered store credit. Customer accepted again.", "2025-05-02"),
    ("david@example.com", "Fraud complaint — unauthorized charge on account", "Investigated, charge reversed, account flagged for extra verification.", "2025-03-10"),
]

async def seed():
    await init_db()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Check if already seeded
        async with db.execute("SELECT COUNT(*) FROM customers") as cursor:
            row = await cursor.fetchone()
            if row[0] > 0:
                print(f"Database already has {row[0]} customers. Skipping seed.")
                return

        # Insert customers
        for c in CUSTOMERS:
            await db.execute(
                "INSERT INTO customers (name, email, phone, segment, preferences) VALUES (?,?,?,?,?)",
                (c["name"], c["email"], c["phone"], c["segment"], c["preferences"])
            )

        # Insert orders
        for o in ORDERS:
            email, order_num, status, amount, items, created, delivered, eligible = o
            async with db.execute("SELECT id FROM customers WHERE email=?", (email,)) as cur:
                row = await cur.fetchone()
                if row:
                    await db.execute(
                        "INSERT INTO orders (customer_id, order_number, status, total_amount, items, created_at, delivered_at, refund_eligible) VALUES (?,?,?,?,?,?,?,?)",
                        (row["id"], order_num, status, amount, items, created, delivered, eligible)
                    )

        # Insert support history
        for s in SUPPORT_HISTORY:
            email, issue, resolution, created = s
            async with db.execute("SELECT id FROM customers WHERE email=?", (email,)) as cur:
                row = await cur.fetchone()
                if row:
                    await db.execute(
                        "INSERT INTO support_history (customer_id, issue, resolution, created_at) VALUES (?,?,?,?)",
                        (row["id"], issue, resolution, created)
                    )

        await db.commit()
        print("✅ Seeded 10 customers, orders, and support history.")

if __name__ == "__main__":
    asyncio.run(seed())