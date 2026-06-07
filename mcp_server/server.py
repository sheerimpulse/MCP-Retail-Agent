# mcp_server/server.py
import asyncio
import json
import aiosqlite
from mcp.server.lowlevel import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
import mcp.types as types
from mcp_server.database import DB_PATH, init_db

app = Server("retail-mcp-server")

# ─────────────────────────────────────────────
# TOOL DEFINITIONS
# ─────────────────────────────────────────────

TOOLS = [
    types.Tool(
        name="get_customer",
        description="Fetch a customer profile by email, phone, or name. Always call this first before any other tool.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Customer email, phone number, or full name"
                }
            },
            "required": ["query"]
        }
    ),
    types.Tool(
        name="lookup_order",
        description="Look up orders for a customer. Requires customer_id from get_customer. Must be called before process_refund.",
        inputSchema={
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "integer",
                    "description": "Customer ID returned by get_customer"
                },
                "order_number": {
                    "type": "string",
                    "description": "Optional specific order number to look up"
                }
            },
            "required": ["customer_id"]
        }
    ),
    types.Tool(
        name="process_refund",
        description="Process a refund for an order. Requires a prior successful lookup_order call. Checks eligibility before processing.",
        inputSchema={
            "type": "object",
            "properties": {
                "order_number": {
                    "type": "string",
                    "description": "Order number to refund"
                },
                "customer_id": {
                    "type": "integer",
                    "description": "Customer ID to verify ownership"
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for the refund"
                }
            },
            "required": ["order_number", "customer_id", "reason"]
        }
    ),
    types.Tool(
        name="escalate_to_human",
        description="Escalate a case to a human agent. Use when blocked, unsure, or when the issue is too sensitive to handle automatically.",
        inputSchema={
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "integer",
                    "description": "Customer ID"
                },
                "reason": {
                    "type": "string",
                    "description": "Why this case is being escalated"
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Escalation priority"
                }
            },
            "required": ["customer_id", "reason", "priority"]
        }
    ),
]

# ─────────────────────────────────────────────
# LIST TOOLS HANDLER
# ─────────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return TOOLS

# ─────────────────────────────────────────────
# TOOL IMPLEMENTATIONS
# ─────────────────────────────────────────────

async def handle_get_customer(query: str) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        q = f"%{query}%"
        async with db.execute(
            """SELECT * FROM customers
               WHERE email = ? OR phone = ? OR name LIKE ?
               LIMIT 1""",
            (query, query, q)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return {
                "status": "not_found",
                "message": f"No customer found matching '{query}'"
            }

        customer = dict(row)
        customer["preferences"] = json.loads(customer["preferences"] or "{}")

        # Fetch support history
        async with db.execute(
            "SELECT issue, resolution, created_at FROM support_history WHERE customer_id = ? ORDER BY created_at DESC",
            (customer["id"],)
        ) as cursor:
            support_rows = await cursor.fetchall()

        customer["support_history"] = [dict(r) for r in support_rows]

        return {
            "status": "success",
            "customer": customer
        }


async def handle_lookup_order(customer_id: int, order_number: str = None) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Verify customer exists
        async with db.execute("SELECT id, name FROM customers WHERE id = ?", (customer_id,)) as cursor:
            customer = await cursor.fetchone()

        if not customer:
            return {
                "status": "error",
                "message": f"Customer with id {customer_id} not found"
            }

        if order_number:
            async with db.execute(
                """SELECT * FROM orders
                   WHERE customer_id = ? AND order_number = ?""",
                (customer_id, order_number)
            ) as cursor:
                rows = await cursor.fetchall()
        else:
            async with db.execute(
                """SELECT * FROM orders
                   WHERE customer_id = ?
                   ORDER BY created_at DESC""",
                (customer_id,)
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            return {
                "status": "not_found",
                "message": f"No orders found for customer {customer['name']}"
            }

        orders = []
        for row in rows:
            o = dict(row)
            o["items"] = json.loads(o["items"] or "[]")
            orders.append(o)

        return {
            "status": "success",
            "customer_name": customer["name"],
            "customer_id": customer_id,
            "orders": orders
        }


async def handle_process_refund(order_number: str, customer_id: int, reason: str) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Verify order belongs to customer
        async with db.execute(
            """SELECT o.*, c.name as customer_name, c.segment
               FROM orders o
               JOIN customers c ON o.customer_id = c.id
               WHERE o.order_number = ? AND o.customer_id = ?""",
            (order_number, customer_id)
        ) as cursor:
            order = await cursor.fetchone()

        if not order:
            return {
                "status": "error",
                "message": f"Order {order_number} not found for this customer"
            }

        order = dict(order)

        # Eligibility checks
        if order["status"] == "refunded":
            return {
                "status": "already_refunded",
                "message": f"Order {order_number} has already been refunded",
                "order_number": order_number
            }

        if order["status"] == "processing":
            return {
                "status": "not_eligible",
                "message": f"Order {order_number} is still processing and cannot be refunded yet",
                "order_number": order_number
            }

        if not order["refund_eligible"]:
            return {
                "status": "not_eligible",
                "message": f"Order {order_number} is not eligible for a refund (previously resolved via store credit or already actioned)",
                "order_number": order_number
            }

        # Simulate refund
        await db.execute(
            "UPDATE orders SET status = 'refunded', refund_eligible = 0 WHERE order_number = ?",
            (order_number,)
        )
        await db.commit()

        return {
            "status": "success",
            "message": f"Refund of ${order['total_amount']:.2f} successfully processed for order {order_number}",
            "order_number": order_number,
            "amount_refunded": order["total_amount"],
            "customer_name": order["customer_name"],
            "reason": reason
        }


async def handle_escalate_to_human(customer_id: int, reason: str, priority: str) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT name, email, segment FROM customers WHERE id = ?", (customer_id,)) as cursor:
            customer = await cursor.fetchone()

    if not customer:
        return {
            "status": "error",
            "message": f"Customer {customer_id} not found"
        }

    # In production this would create a ticket in a real system
    ticket_id = f"ESC-{customer_id}-{asyncio.get_event_loop().time():.0f}"

    return {
        "status": "escalated",
        "ticket_id": ticket_id,
        "customer_name": customer["name"],
        "customer_email": customer["email"],
        "segment": customer["segment"],
        "priority": priority,
        "reason": reason,
        "message": f"Case escalated to human agent. Ticket {ticket_id} created with {priority} priority."
    }

# ─────────────────────────────────────────────
# CALL TOOL HANDLER
# ─────────────────────────────────────────────

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        if name == "get_customer":
            result = await handle_get_customer(arguments["query"])

        elif name == "lookup_order":
            result = await handle_lookup_order(
                customer_id=arguments["customer_id"],
                order_number=arguments.get("order_number")
            )

        elif name == "process_refund":
            result = await handle_process_refund(
                order_number=arguments["order_number"],
                customer_id=arguments["customer_id"],
                reason=arguments["reason"]
            )

        elif name == "escalate_to_human":
            result = await handle_escalate_to_human(
                customer_id=arguments["customer_id"],
                reason=arguments["reason"],
                priority=arguments["priority"]
            )

        else:
            result = {"status": "error", "message": f"Unknown tool: {name}"}

    except KeyError as e:
        result = {"status": "error", "message": f"Missing required argument: {e}"}
    except Exception as e:
        result = {"status": "error", "message": f"Tool execution failed: {str(e)}"}

    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

async def main():
    await init_db()
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="retail-mcp-server",
                server_version="0.1.0",
                capabilities=app.get_capabilities(
                    notification_options=None,
                    experimental_capabilities={}
                )
            )
        )

if __name__ == "__main__":
    asyncio.run(main())