# retail_agent/agent.py
import os
import sys
from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from retail_agent.hooks import pre_tool_use, post_tool_use

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Absolute path to the MCP server script
MCP_SERVER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "mcp_server", "server.py"
)

SYSTEM_PROMPT = """You are a retail customer support agent. You help operators 
look up customers, check orders, process refunds, and escalate issues.

STRICT TOOL ORDERING — always follow this sequence:
1. get_customer   → always first, to identify the customer
2. lookup_order   → required before any refund
3. process_refund → only after a successful lookup_order
4. escalate_to_human → use when blocked or for sensitive cases

AFTER EVERY TOOL CALL you must summarize the result clearly in plain text.
Never return a blank response. Always tell the operator what you found.

For get_customer: summarize the customer's name, segment, contact preference,
and any support history highlights.

For lookup_order: list each order with its number, status, amount, and 
whether it is refund eligible.

For process_refund: confirm the refund amount and order number, or explain 
why it was blocked.

For escalate_to_human: confirm the ticket ID and priority.

After completing your task, end with one of:
[stop_reason: end_turn]
[stop_reason: needs_clarification]
[stop_reason: escalated_to_human]
[stop_reason: blocked_by_policy]
"""

root_agent = LlmAgent(
    model="gemini-2.5-flash-lite",
    name="retail_support_agent",
    description="Retail customer support agent with order lookup, refund processing, and escalation.",
    instruction=SYSTEM_PROMPT,
    tools=[
        McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "mcp_server.server"],
                ),
                timeout=15
            )
        )
    ],
    before_tool_callback=pre_tool_use,
    after_tool_callback=post_tool_use,
)