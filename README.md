# 🛒 Retail Support Agent

An AI-powered retail customer support agent built with **Google ADK**, **MCP (Model Context Protocol)**, and **mem0** persistent memory. Operators can look up customers, view orders, process refunds, update preferences, and escalate cases — all through a conversational interface with role-based access control.

Comes with two interfaces: an interactive **CLI** and a browser-based **dashboard** served by FastAPI.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Environment Variables](#environment-variables)
- [Database Setup](#database-setup)
- [Running the Project](#running-the-project)
  - [CLI](#cli)
  - [Dashboard (FastAPI)](#dashboard-fastapi)
- [Login & Authentication](#login--authentication)
- [Tool-Use Flow](#tool-use-flow)
- [Hooks — Before & After Tool Use](#hooks--before--after-tool-use)
- [Memory Design (mem0)](#memory-design-mem0)
- [Role-Based Permissions](#role-based-permissions)
- [Known Limitations](#known-limitations)
- [Future Improvements](#future-improvements)

---

## Project Overview

This project simulates a **back-office retail support tool** for operators (agents, managers, admins) — not an end-customer chatbot. An operator selects a customer and interacts with the AI agent to:

- Look up customer profiles and support history
- View and query orders
- Process refunds (subject to policy checks)
- Update customer preferences
- Escalate cases to human agents

The agent enforces a strict tool-calling order, role-based permissions, and remembers customer context across sessions via mem0.

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM Agent | Google ADK (`google-adk`) with Gemini 2.5 Flash Lite |
| Tool Server | MCP (Model Context Protocol) over `stdio` |
| Database | SQLite via `aiosqlite` |
| Memory | mem0 (`mem0ai`) — cloud or local |
| API / Dashboard | FastAPI + plain HTML/JS |
| Auth | SHA-256 hashed mock credentials (session-scoped) |
| Config | `python-dotenv` |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Interfaces                        │
│         CLI (cli.py)    Dashboard (api.py)          │
└──────────────────┬──────────────────────────────────┘
                   │  Google ADK InMemoryRunner
┌──────────────────▼──────────────────────────────────┐
│               retail_agent/                         │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────┐ │
│  │ agent.py │  │ hooks.py │  │     memory.py      │ │
│  │ (LlmAgent│  │ before_  │  │  mem0 read/write   │ │
│  │  + tools)│  │ agent,   │  │  search_memory     │ │
│  │          │  │ pre/post │  │  save_memory       │ │
│  └────┬─────┘  │ tool_use)│  └────────────────────┘ │
│       │        └──────────┘                         │
└───────┼─────────────────────────────────────────────┘
        │  MCP StdioServerParameters (subprocess)
┌───────▼─────────────────────────────────────────────┐
│               mcp_server/                           │
│  server.py — 5 tools exposed over MCP stdio         │
│  database.py — aiosqlite schema                     │
│  seed.py — 10 sample customers + orders             │
└──────────────────────────────────────────────────────┘
        │
┌───────▼──────────┐
│  database/       │
│  retail.db       │  SQLite (auto-created on first run)
└──────────────────┘
```

The agent process spawns the MCP server as a **subprocess** and communicates over `stdio`. The ADK runner manages session state and routes user messages through the auth gate (`before_agent` hook) before any tool can be called.

---

## Prerequisites

- Python **3.10+**
- `pip`
- A **Google AI / Gemini API key** (for the ADK agent)
- A **mem0 API key** — _or_ choose `MEM0_PROVIDER=local` for local dev (requires `qdrant-client` and an OpenAI key for embeddings)
- _(Optional, for local mem0)_ An **OpenAI API key** for mem0's local embedding/extraction pipeline

---

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/sheerimpulse/MCP-Retail-Agent.git
cd MCP-Retail-Agent

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

> Alternatively, run `python setup.py` which creates the venv and installs requirements automatically.

---

## Environment Variables

Create a `.env` file in the project root. Copy the block below and fill in your keys:

```env
# ── Google ADK / Gemini ────────────────────────────────────────────────────
GOOGLE_API_KEY=your_gemini_api_key_here

# ── mem0 Memory ───────────────────────────────────────────────────────────
# Option A: Managed mem0 cloud (default)
MEM0_PROVIDER=cloud
MEM0_API_KEY=your_mem0_api_key_here

# Option B: Local mem0 (no mem0 API key needed — needs OpenAI + qdrant-client)
# MEM0_PROVIDER=local
# OPENAI_API_KEY=your_openai_api_key_here
```

### Where to get the keys

| Key | Where |
|---|---|
| `GOOGLE_API_KEY` | [Google AI Studio](https://aistudio.google.com/app/apikey) |
| `MEM0_API_KEY` | [app.mem0.ai](https://app.mem0.ai) → Settings → API Keys |
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/api-keys) _(local mem0 only)_ |

---

## Database Setup

The SQLite database is created and seeded automatically on first run. To seed it manually:

```bash
python -m mcp_server.seed
```

This inserts **10 sample customers** (VIP, regular, new segments), associated orders (ORD-1001 through ORD-1018), and support history records. If the database is already seeded, the script skips without overwriting.

The database file lives at `database/retail.db`.

---

## Running the Project

### CLI

```bash
python cli.py
```

Options:

```bash
python cli.py --session my-session-id   # resume a named session
python cli.py --help
```

In-session commands:

| Command | Action |
|---|---|
| `/quit` or `/exit` | Exit the CLI |
| `/new` | Start a fresh session |
| `/session` | Print the current session ID |

You will be prompted to log in before the agent responds to anything (see [Login](#login--authentication) below).

---

### Dashboard (FastAPI)

```bash
uvicorn api:app --reload --port 8000
```

Then open [http://localhost:8000](http://localhost:8000) in your browser.

The dashboard shows:
- A searchable customer list (left panel)
- A chat window with an execution trace for every tool call (center)
- A live customer profile + support history panel (right)

Select a customer to begin; the agent will prompt you to log in on the first message.

---

## Login & Authentication

The agent uses a **session-scoped auth gate** implemented in `before_agent` (see `hooks.py`). No tool can be called until the operator is authenticated.

### Default credentials

| Username | Password | Role |
|---|---|---|
| `demo@traversaal.ai` | `demo123` | admin |
| `alice` | `alice123` | agent |
| `bob` | `bob456` | manager |
| `admin` | `admin` | admin |

### How to log in

Type your credentials in the chat in any of these formats:

```
username: alice  password: alice123
user: bob  pass: bob456
admin admin
```

The auth layer parses free-form text, so you don't need to use a form — just type naturally.

### Auth state machine

```
First message → show login prompt, set pending_auth=True
Next message  → parse credentials
                ├── valid   → mark authenticated, continue to agent
                └── invalid → show error, ask again (loop)
Authenticated → before_agent returns None → agent runs normally
```

---

## Tool-Use Flow

The MCP server exposes five tools. The agent enforces a **strict calling order**:

```
1. get_customer        ← always first; identifies the customer by email, phone, or name
        │
2. lookup_order        ← requires get_customer to have run first
        │
3. process_refund      ← requires lookup_order to have run first
        │
   update_customer     ← can run after get_customer; updates preferences & saves to mem0
        │
   escalate_to_human   ← can run at any point when blocked or for sensitive cases
```

### Tool reference

| Tool | What it does | Key inputs |
|---|---|---|
| `get_customer` | Fetches customer profile + support history; triggers mem0 memory search | `query` (email / phone / name) |
| `lookup_order` | Lists all orders for a customer; flags refund eligibility; saves order snapshot to mem0 | `customer_id`, optional `order_number` |
| `process_refund` | Processes a refund; checks eligibility and order status; saves refund event to mem0 | `order_number`, `customer_id`, `reason` |
| `update_customer` | Updates customer preferences (contact method, notifications, language); saves update summary to mem0 | `customer_id`, `preferences`, `update_summary` |
| `escalate_to_human` | Creates an escalation ticket; saves escalation fact to mem0 | `customer_id`, `reason`, `priority` |

---

## Hooks — Before & After Tool Use

All hooks live in `retail_agent/hooks.py`.

### `before_agent` (auth gate)

Runs before **every** agent turn. Implements the auth state machine described above — returning a `Content` object short-circuits the LLM entirely, so the agent cannot respond until the operator is logged in.

### `pre_tool_use` (PreToolUse hook)

Runs before each tool call. Enforces:

1. **Ordering rules** — `lookup_order` is blocked if `get_customer` hasn't run; `process_refund` is blocked if `lookup_order` hasn't run.
2. **Unsafe keyword detection** — refund reasons containing `without check`, `skip`, or `bypass` are blocked immediately.
3. **Stale context reset** — clears mem0 customer context when a new `get_customer` is initiated.

When blocked, the hook returns a `hook_decision: blocked` payload with a `stop_reason` and a `reason` — the agent surfaces this to the operator and halts.

### `post_tool_use` (PostToolUse hook)

Runs after each tool call. Responsibilities:

- **Normalises MCP responses** from the raw `{content: [{text: "..."}]}` wrapper to clean Python dicts.
- **Enriches responses** — adds `safe_for_customer`, `policy_note`, human-readable `summary` fields, and flags orders over $500 as requiring manager approval.
- **Writes to mem0** — persists customer facts, order snapshots, refund events, update summaries, and escalation records for future sessions.
- **Injects memory context** — after `get_customer`, searches mem0 for past context and injects it into `tool_context.state["mem0_customer_context"]`, which the system prompt picks up via `{mem0_customer_context}`.

---

## Memory Design (mem0)

mem0 gives the agent **persistent, per-customer memory** across sessions. Each customer is stored under a `user_id` equal to their database integer ID.

### What gets saved

| Event | Memory content | Metadata tags |
|---|---|---|
| `get_customer` | Customer profile facts | `source: get_customer` |
| `lookup_order` | Order items, statuses, amounts, refund eligibility | `source: lookup_order`, `event: orders_viewed` |
| `process_refund` | Refund outcome, amount, reason | `source: process_refund`, `event: refund_processed` |
| `update_customer` | Free-text `update_summary` from the agent | `source: update_customer`, `event: profile_updated` |
| `escalate_to_human` | Ticket ID, priority, reason | `source: escalate_to_human`, `event: escalation_created` |

### How memory is injected

After `get_customer` succeeds, `post_tool_use` calls `search_memory` with the customer's email as the query and injects the results into `state["mem0_customer_context"]`. The system prompt includes:

```
{mem0_customer_context}
IMPORTANT: If past memory context is present above, it may reflect more recent
updates than the live tool response. Always prefer memory context over tool
response for fields like contact preferences or profile updates.
```

This means a preference updated last week — even if not yet reflected in the database — will be surfaced to the agent and take precedence.

### Switching between cloud and local mem0

| Mode | `.env` setting | Notes |
|---|---|---|
| Cloud (default) | `MEM0_PROVIDER=cloud` + `MEM0_API_KEY=...` | Fully managed; persists across machines |
| Local | `MEM0_PROVIDER=local` | Uses in-process Qdrant + SQLite; requires `pip install mem0ai[local]` and `OPENAI_API_KEY` for embeddings |

If `mem0ai` is not installed, a silent no-op stub is used and the agent runs without memory features.

---

## Role-Based Permissions

| Role | Permissions |
|---|---|
| `agent` | Look up customers, look up orders, escalate issues, update preferences |
| `manager` | All agent permissions + approve refunds over $500 |
| `admin` | Full access |

The role is set at login and injected into the system prompt. Refunds above $500 are flagged in the `post_tool_use` hook with a `policy_note` requiring manager approval.

---

## Known Limitations

- **Mock auth only** — credentials are stored as SHA-256 hashes in a plain Python dict. Not suitable for production. Replace `validate_login` in `auth.py` with a real auth backend (DB query, LDAP, OAuth).
- **In-memory ADK sessions** — `InMemoryRunner` means sessions are lost on server restart. There is no session persistence for the agent's conversational state (separate from mem0 long-term memory).
- **SQLite single-file database** — fine for development; not suitable for concurrent production workloads. The `update_customer` tool currently does not write back to SQLite — it only persists the update to mem0.
- **No streaming responses** — the FastAPI `/chat` endpoint collects all ADK events before responding. Long tool chains will feel slow.
- **Single-agent, single-turn tool calls** — the agent calls tools sequentially. Parallel tool calls are not used.
- **MCP server restarts with each request** — the MCP server is started as a subprocess per ADK session, which has some startup overhead.
- **No real ticket system** — `escalate_to_human` generates a fake ticket ID (`ESC-{id}-{timestamp}`) and does not connect to any external ticketing system.

---

## Future Improvements

- **Real authentication** — integrate OAuth2 / JWT or an identity provider; add token refresh and logout.
- **Session persistence** — swap `InMemoryRunner` for a persistent ADK session backend (e.g. Firestore, Redis) so operator sessions survive server restarts.
- **Write-through to database** — `update_customer` should also write preference changes back to SQLite, not just mem0.
- **Streaming responses** — use `StreamingResponse` in FastAPI to stream agent output token-by-token for a better UX.
- **Multi-customer session** — allow a single operator session to handle multiple customers without re-authenticating.
- **Real ticketing integration** — connect `escalate_to_human` to Zendesk, Jira, or Linear via their APIs.
- **Audit logging** — persist every tool call, decision, and operator action to an audit table for compliance.
- **Expanded role permissions** — granular permission checks enforced server-side in hooks, not just surfaced in the prompt.
- **Eval suite** — automated tests covering the auth gate, hook ordering rules, refund policy, and memory injection.
- **Docker / docker-compose** — containerise the app, MCP server, and (for local mem0) Qdrant for one-command startup.