# retail_agent/hooks.py
import json
import sys
from typing import Any, Optional
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import BaseTool

from retail_agent.memory import save_memory, search_memory, format_memories_for_prompt

REFUND_THRESHOLD = 500.00

_session_tool_history: dict[str, set] = {}

def log(msg: str):
    """Safe logging for Memory — must use stderr, never stdout."""
    print(msg, file=sys.stderr)

def _get_history(ctx: CallbackContext) -> set:
    sid = ctx.session.id
    if sid not in _session_tool_history:
        _session_tool_history[sid] = set()
    return _session_tool_history[sid]

def _log(hook: str, tool: str, decision: str, reason: str) -> dict:
    entry = {
        "hook": hook,
        "tool": tool,
        "decision": decision,
        "reason": reason
    }
    print(f"\n[{hook}] tool={tool} | decision={decision} | reason={reason}",
          file=sys.stderr)
    return entry


# ─────────────────────────────────────────────
# PRE TOOL USE
# ─────────────────────────────────────────────

def pre_tool_use(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: CallbackContext,
) -> Optional[dict]:
    tool_name = tool.name
    history = _get_history(tool_context)

    # ── 1. lookup_order requires get_customer first ──
    if tool_name == "lookup_order":
        if "get_customer" not in history:
            log = _log("PreToolUse", tool_name, "blocked",
                       "lookup_order requires a prior get_customer call.")
            return {
                "hook_decision": "blocked",
                "reason": log["reason"],
                "stop_reason": "blocked_by_policy",
                "trace": log
            }

    # ── 2. process_refund requires lookup_order first ──
    if tool_name == "process_refund":
        if "lookup_order" not in history:
            log = _log("PreToolUse", tool_name, "blocked",
                       "process_refund requires a prior lookup_order call.")
            return {
                "hook_decision": "blocked",
                "reason": log["reason"],
                "stop_reason": "blocked_by_policy",
                "trace": log
            }

    # ── 3. Block unsafe refund keywords ──
    if tool_name == "process_refund":
        reason_text = args.get("reason", "").lower()
        if any(kw in reason_text for kw in ["without check", "skip", "bypass"]):
            log = _log("PreToolUse", tool_name, "blocked",
                       "Unsafe keywords detected in refund reason.")
            return {
                "hook_decision": "blocked",
                "reason": log["reason"],
                "stop_reason": "blocked_by_policy",
                "trace": log
            }

    # ── 4. Inject past memories before get_customer ──
    # We search mem0 using the customer_id (or email) the agent is about to look up
    # and surface any stored context into the session state so the agent can use it.
    if tool_name == "get_customer":
        # The MCP tool typically receives either customer_id or email
        lookup_key = args.get("customer_id") or args.get("email") or args.get("query", "")
        if lookup_key:
            memories = search_memory(
                query=f"customer profile and history for {lookup_key}",
                user_id=str(lookup_key),
                limit=5,
            )
            if memories:
                memory_block = format_memories_for_prompt(memories)
                # Inject into session state so the LLM sees it as prior context
                try:
                    tool_context.state["mem0_customer_context"] = memory_block
                    print(
                        f"[PreToolUse] Injected {len(memories)} memories into session state "
                        f"for {lookup_key}",
                        file=sys.stderr,
                    )
                except Exception as exc:
                    print(f"[PreToolUse] Could not write to session state: {exc}", file=sys.stderr)

    # ── 5. Allow ──
    _log("PreToolUse", tool_name, "allowed", f"{tool_name} approved.")
    return None


# ─────────────────────────────────────────────
# POST TOOL USE
# ─────────────────────────────────────────────

def post_tool_use(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context,
    tool_response: dict
) -> Optional[dict]:
    tool_name = tool.name
    history = _get_history(tool_context)
    history.add(tool_name)
    
    log(f'POST TOOL USE {tool},{tool.name}, {tool_response}')

    # Normalize MCP response to dict
    parsed = tool_response
    if isinstance(parsed, dict) and "content" in parsed:
        try:
            text = parsed["content"][0]["text"]
            parsed = json.loads(text)
        except Exception:
            pass
    elif isinstance(parsed, list):
        for item in parsed:
            text = getattr(item, "text", None)
            if text:
                try:
                    parsed = json.loads(text)
                    break
                except Exception:
                    parsed = {"raw": text}
                    break
    elif isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except Exception:
            parsed = {"raw": parsed}
    tool_response = parsed

    # ── get_customer ──
    if tool_name == "get_customer":
        if isinstance(tool_response, dict) and tool_response.get("status") == "success":
            customer = tool_response.get("customer", {})
            cleaned = {
                "status": "success",
                "customer_id": customer.get("id"),
                "name": customer.get("name"),
                "email": customer.get("email"),
                "phone": customer.get("phone"),
                "segment": customer.get("segment"),
                "preferences": customer.get("preferences", {}),
                "support_history": customer.get("support_history", []),
                "safe_for_customer": True,
                "summary": (
                    f"{customer.get('name')} is a {customer.get('segment', 'regular')} customer. "
                    f"Contact preference: {customer.get('preferences', {}).get('contact', 'email')}."
                )
            }
            print(f"[PostToolUse] get_customer → cleaned profile for {customer.get('name')}",
                  file=sys.stderr)

            # ── mem0: save customer profile facts ──
            customer_id = str(customer.get("id", ""))
            if customer_id:
                mem_facts = [
                    f"Customer name: {customer.get('name')}",
                    f"Segment: {customer.get('segment', 'regular')}",
                    f"Contact preference: {customer.get('preferences', {}).get('contact', 'email')}",
                    f"Email: {customer.get('email')}",
                    f"Phone: {customer.get('phone')}",
                ]
                support_history = customer.get("support_history", [])
                if support_history:
                    mem_facts.append(
                        f"Support history: {json.dumps(support_history)}"
                    )

                save_memory(
                    messages=[{"role": "user", "content": " | ".join(mem_facts)}],
                    user_id=customer_id,
                    metadata={"source": "get_customer", "event": "profile_loaded"},
                )

            return cleaned
        
    if tool_name == "update_customer":
        if isinstance(tool_response, dict) and tool_response.get("status") == "success":
            customer_id = str(tool_response.get("customer_id",""))
            update_summary = tool_response.get("update_summary", "Customer profile updated.")
            if customer_id:
                save_memory(
                    messages=[{"role":"user","content":update_summary}],
                    user_id=customer_id,
                    metadata={
                        "source":"update_customer",
                        "event":"profile_updated",
                        "summary": update_summary
                    }
                )

    # ── lookup_order ──
    if tool_name == "lookup_order":
        if isinstance(tool_response, dict) and tool_response.get("status") == "success":
            orders = tool_response.get("orders", [])
            cleaned_orders = []
            for o in orders:
                entry = {
                    "order_number": o.get("order_number"),
                    "status": o.get("status", "unknown").capitalize(),
                    "total_amount": o.get("total_amount"),
                    "items": o.get("items", []),
                    "created_at": o.get("created_at"),
                    "delivered_at": o.get("delivered_at"),
                    "refund_eligible": bool(o.get("refund_eligible")),
                    "summary": _order_summary(o),
                    "safe_for_customer": True
                }
                if o.get("total_amount", 0) > REFUND_THRESHOLD:
                    entry["refund_requires_escalation"] = True
                    entry["policy_note"] = (
                        f"Orders over ${REFUND_THRESHOLD:.0f} require manager approval."
                    )
                cleaned_orders.append(entry)

            print(f"[PostToolUse] lookup_order → {len(cleaned_orders)} orders cleaned",
                  file=sys.stderr)

            # ── mem0: save order history snapshot ──
            customer_id = str(tool_response.get("customer_id", ""))
            if customer_id and cleaned_orders:
                order_facts = []
                for o in cleaned_orders:
                    items_str = ", ".join(
                        i.get("item", "item") for i in o.get("items", [])
                    )
                    order_facts.append(
                        f"Order {o['order_number']}: {items_str}, "
                        f"status={o['status']}, amount=${o.get('total_amount', 0):.2f}, "
                        f"refund_eligible={o['refund_eligible']}"
                    )

                save_memory(
                    messages=[{
                        "role": "user",
                        "content": "Recent orders: " + " | ".join(order_facts)
                    }],
                    user_id=customer_id,
                    metadata={"source": "lookup_order", "event": "orders_viewed"},
                )

            return {
                "status": "success",
                "customer_name": tool_response.get("customer_name"),
                "customer_id": tool_response.get("customer_id"),
                "orders": cleaned_orders,
                "safe_for_customer": True
            }

    # ── process_refund ──
    if tool_name == "process_refund":
        if isinstance(tool_response, dict):
            tool_response["safe_for_customer"] = True
            tool_response["policy_applied"] = "Standard refund policy"
            if tool_response.get("status") == "success":
                tool_response["summary"] = (
                    f"Refund of ${tool_response.get('amount_refunded', 0):.2f} "
                    f"processed for {tool_response.get('order_number')}."
                )
            print(f"[PostToolUse] process_refund → {tool_response.get('status')}",
                  file=sys.stderr)

            # ── mem0: record refund event ──
            customer_id = str(args.get("customer_id", ""))
            order_number = args.get("order_number", "unknown")
            if customer_id:
                status = tool_response.get("status", "unknown")
                amount = tool_response.get("amount_refunded", args.get("amount", 0))
                refund_fact = (
                    f"Refund {status} for order {order_number}, "
                    f"amount=${float(amount):.2f}, reason={args.get('reason', 'N/A')}"
                )
                save_memory(
                    messages=[{"role": "user", "content": refund_fact}],
                    user_id=customer_id,
                    metadata={
                        "source": "process_refund",
                        "event": "refund_processed",
                        "order_number": order_number,
                        "status": status,
                    },
                )

            return tool_response

    # ── escalate_to_human ──
    if tool_name == "escalate_to_human":
        if isinstance(tool_response, dict):
            tool_response["safe_for_customer"] = True
            tool_response["summary"] = (
                f"Case escalated with {tool_response.get('priority')} priority. "
                f"Ticket: {tool_response.get('ticket_id')}."
            )
            print(f"[PostToolUse] escalate_to_human → {tool_response.get('ticket_id')}",
                  file=sys.stderr)

            # ── mem0: record escalation event ──
            customer_id = str(args.get("customer_id", ""))
            if customer_id:
                ticket_id = tool_response.get("ticket_id", "unknown")
                priority = tool_response.get("priority", "normal")
                reason = args.get("reason", "N/A")
                escalation_fact = (
                    f"Escalated to human agent: ticket={ticket_id}, "
                    f"priority={priority}, reason={reason}"
                )
                save_memory(
                    messages=[{"role": "user", "content": escalation_fact}],
                    user_id=customer_id,
                    metadata={
                        "source": "escalate_to_human",
                        "event": "escalation_created",
                        "ticket_id": ticket_id,
                        "priority": priority,
                    },
                )

            return tool_response

    return None

def _order_summary(order: dict) -> str:
    status = order.get("status", "unknown").lower()
    items = order.get("items", [])
    item_names = ", ".join(i.get("item", "item") for i in items)
    if status == "delayed":
        return f"{item_names} is delayed. Delivery pending logistics update."
    elif status == "delivered":
        return f"{item_names} delivered on {order.get('delivered_at', 'unknown')}."
    elif status == "refunded":
        return f"{item_names} has already been refunded."
    elif status == "processing":
        return f"{item_names} is currently being processed."
    return f"{item_names} — status: {status}."