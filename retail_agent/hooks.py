# retail_agent/hooks.py
import json
import sys
from typing import Any, Optional
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import BaseTool

REFUND_THRESHOLD = 500.00

_session_tool_history: dict[str, set] = {}

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

    # ── 4. Allow ──
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

    # Normalize MCP response to dict
    parsed = tool_response
    if isinstance(parsed, list):
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
                "notes": customer.get("notes"),
                "safe_for_customer": True,
                "summary": (
                    f"{customer.get('name')} is a {customer.get('segment', 'regular')} customer. "
                    f"Contact preference: {customer.get('preferences', {}).get('contact', 'email')}."
                )
            }
            print(f"[PostToolUse] get_customer → cleaned profile for {customer.get('name')}",
                  file=sys.stderr)
            return cleaned

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