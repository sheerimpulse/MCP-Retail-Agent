# Take Home Assignment

# Retail Production Agent

**Role context:** We are building an AI operating system for retailers. One core module is a customer-support agent that looks up customers, checks orders, handles refunds, escalates sensitive cases, remembers context per customer, and — critically — runs every tool call through controlled safety checkpoints.

You'll build a retail support agent that:

- Runs as a **command-line (CLI) application** *and* surfaces through a **visual dashboard**, both driven by the same agent engine.
- Is built on the **Agent Development Kit (ADK)**.
- Pulls live order data from a **database over MCP** (BigQuery, or a SQL database).
- Remembers the customer across turns using **mem0**.
- Runs every tool call through `PreToolUse` and `PostToolUse` hooks, with the full execution trace visible.

It should look like a chatbot on the front end but behave like a production agent system underneath.

---

## What we're looking for

The center of gravity is the **production agent loop** — a request flowing into the agent, through a `PreToolUse` check, into a tool, through a `PostToolUse` transform, and back out with a clear stop reason — with the full trace visible both in the terminal and in the dashboard.

Equally important is that the infrastructure is *real*, not faked: the agent genuinely retrieves orders from a database over MCP, and genuinely persists and reuses memory through mem0. We want to see correct wiring, sensible architecture, and clean, readable code across the whole build.

---

## Required Work

### 1. Agent engine on ADK

Build the agent using the **Agent Development Kit (ADK)**. The same engine must back both the CLI and the dashboard — no duplicate logic. The agent, tools, hooks, and the loop all live here.

### 2. Database access over MCP

Connect to a database **through MCP** (not a direct driver call from the agent). Target **BigQuery**, or a SQL database if you prefer.

- The agent must **automatically retrieve customer order information** — order history, status, line items, dates, amounts — by issuing queries through the MCP connection.
- Seed the database with **10 customers** and their orders. Make the customers *meaningfully different*; that difference is what makes memory testable.
- Each customer record: name, email, phone, segment, preferences, purchase/order history, support history.

### 3. Memory with mem0

Integrate **mem0** so the agent remembers facts about a user and reuses them in follow-up turns.

- Memory must be **per customer** and must change the answer. The same question should produce different results across customers, and **within a session** new information the customer shares should be remembered and applied later.
- Example: tell the agent "this customer prefers WhatsApp updates," then later ask how to notify them — the answer should reflect the stored preference.

> "What's the right way to handle this customer's issue?"
> 
> - customer with a prior delivery complaint → answer references the earlier complaint
> - high-value customer flagged for priority handling → answer reflects the priority flag
> - customer who previously accepted store credit → answer suggests store credit first

### 4. CLI application

A working terminal interface where the operator can: log in (mocked is fine — `demo@traversaal.ai` / `demo123`), search/select a customer by name, email, or phone, and chat with the agent. Every response prints the full execution trace (see §6).

### 5. Visual dashboard

A web dashboard over the same engine. A three-region layout is enough:

```
| Customer list / search |  Chat window  |  Customer profile + memory |
|                        |  Tool trace   |                            |
```

The chat window must surface, per response: which tool(s) ran, the `PreToolUse` decision + reason, what `PostToolUse` changed, and the stop reason. The trace is a deliverable, not a nice-to-have.

### 6. The agent loop — the heart of this assignment

The agent must **never call a tool directly.** Every tool call flows through:

```
User message → Agent → PreToolUse → Tool → PostToolUse → Response (+ stop_reason)
```

**`PreToolUse`** fires before every outgoing tool call and can **block, redirect, or log** it, returning a decision + reason. At minimum it must:

- Allow a legitimate lookup for the *selected* customer
- **Block** access to a different customer's private data
- **Redirect** an under-specified or unsafe request to a clarification instead of running the tool
- **Escalate** (or block) a refund that's over a threshold or lacks order-level eligibility
- **Log** every decision so it appears in the trace

```json
{ "hook": "PreToolUse", "tool": "process_refund", "decision": "blocked",
  "reason": "Refund requires order-level eligibility check." }
```

**`PostToolUse`** runs on every result before the agent or UI sees it and does three jobs: **format cleanup** (drop internal fields, normalize status), **policy enforcement** (add policy notes, set customer-safe flags), and **data enrichment** (add a customer-safe summary):

```json
// raw → cleaned
{ "order_id": "ORD-1045", "status": "Delayed",
  "summary": "Delayed due to a warehouse routing issue; expected tomorrow.",
  "safe_for_customer": true }
```

**`stop_reason`** must be present on every response. Use a small enum: `end_turn`, `tool_needed`, `needs_clarification`, `escalated_to_human`, `blocked_by_policy`. The loop is driven by `stop_reason`, **not a fixed iteration counter** — the agent keeps calling tools and decides for itself when it is done by returning `end_turn`. It should be able to call **multiple tools within a single loop** before answering.

**Gates live in code, not prompts.** Safety-critical tool ordering must be enforced programmatically in the loop/hooks, not merely requested in a system prompt — so it holds even when the model "wants" to skip a step. The required ordering: `get_customer` → `lookup_order` → `process_refund`, with `escalate_to_human` as the fallback. A refund must not run before a successful eligibility/order lookup; encode that as a real check, not an instruction.

### 7. Tools (implement all four), exposed as MCP tools

The agent's tools are **MCP tools** — invoked over the MCP connection, not as in-process function calls. The data tools read live from the database (BigQuery/SQL); none return static data.

- `get_customer` *(step 1)* — fetch the selected customer's profile
- `lookup_order` *(step 2)* — retrieve orders, status, dates, and amounts from the database
- `process_refund` *(step 3)* — check eligibility and simulate the refund; gated behind a successful order lookup
- `escalate_to_human` *(fallback)* — escalate sensitive, blocked, or unresolved cases

The `step 1 → 2 → 3 / fallback` ordering above is the safety-critical sequence the code-level gates in §6 must enforce.

---

## Demo flows to verify

Make sure these work end to end; you'll walk through them in the video.

1. **Profile lookup:** select a customer, ask what they usually buy → `get_customer`, `PreToolUse` allows, clean result, answer uses that customer's memory.
2. **Support history:** ask about the customer's last issue → uses support history from the database.
3. **Refund (happy path):** "Can we refund this customer's last order?" → `PreToolUse` checks eligibility, `process_refund` runs only if allowed, `PostToolUse` formats the result, full trace visible.
4. **Blocked / escalated:** "Refund all orders above $500 without checking eligibility." → `PreToolUse` blocks or escalates; trace shows `decision: blocked`, `stop_reason: blocked_by_policy`.
5. **Memory recall:** tell the agent a new fact about the customer, then ask a follow-up that depends on it → the answer reflects what was stored in mem0.
6. **Ordering gate:** ask for a refund without first establishing the order → the code-level gate forces `lookup_order` before `process_refund` (or blocks), proving the sequence is enforced in code, not just prompted.

---

## Stretch goals

After the required work is solid:

- Richer trace/debug panel in the dashboard
- A second agent + router (e.g. a Product/recommendations agent) with rule-based routing
- Persistent chat history per customer
- Additional tools (`check_delivery_status`, `recommend_product`, `add_customer_note`)
- Live deployment
- Polished error and empty states

---

## Deliverables

1. **GitHub repo** containing the ADK agent engine, CLI app, dashboard, MCP database integration, mem0 integration, sample/seed data, tools, and both hooks.
2. **README** covering: project overview; full setup and how to run both the CLI and dashboard (including login, the MCP/database connection, and mem0 configuration — list any env vars/keys we'll need); tech stack; architecture; memory design (how mem0 is used); the tool-use flow and both hooks; known limitations; and future improvements. We must be able to run it from the README alone.
3. **Demo video (3–5 min)** showing login, customer search, the CLI and the dashboard, memory recall, tool calls, `PreToolUse`, `PostToolUse`, and a blocked/escalated action.

---

## Stack

- **Agent framework:** Agent Development Kit (ADK) — required.
- **Database via MCP:** BigQuery, or SQL (SQLite/Postgres) — required to go through MCP.
- **Memory:** mem0 — required.
- **CLI:** your choice of language/runtime.
- **Dashboard:** your choice (e.g. Next.js/React + Tailwind, FastAPI + a light front end). shadcn/ui optional.

---

## Evaluation

| Area | Weight | What "good" looks like |
| --- | --- | --- |
| Production agent loop & hooks | 30% | `stop_reason`-driven loop (not a counter); `PreToolUse` can block/redirect/log; `PostToolUse` does cleanup/policy/enrichment; code-level gates enforce tool ordering; multi-tool loops work |
| MCP database integration | 15% | Orders are really fetched through MCP from BigQuery/SQL, not faked |
| mem0 memory | 15% | Memory is per-customer, persisted, and demonstrably changes answers; new facts are recalled later |
| CLI + dashboard | 15% | Both interfaces work over one engine; trace is legible in each |
| ADK usage & architecture | 15% | Idiomatic ADK; clean separation; one engine, two front ends |
| Code quality & README | 10% | Readable structure; runnable from the README; sound trade-off reasoning |

---

## A note on AI tools

If you use AI tools for assistance, you must fully own the final work. This means you should be able to defend the architecture, logic, and thought process behind your solution, understand every major decision, explain why it was made, and clearly describe how the system works end to end.

**In one line:** Build a retail support agent on ADK — exposed as a CLI and a dashboard — that fetches orders from a database over MCP, remembers customers with mem0, and runs every tool call through `PreToolUse` and `PostToolUse` with a fully visible execution trace.