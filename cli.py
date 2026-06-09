"""
cli.py — Interactive CLI for the Retail Support Agent
------------------------------------------------------
Place this file at the root of your project (alongside the retail_agent/ package).

Usage:
    python cli.py                  # start a fresh session
    python cli.py --session <id>   # resume a named session
    python cli.py --help

Dependencies (already in your stack):
    pip install google-adk python-dotenv
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

from dotenv import load_dotenv

load_dotenv()  # pick up .env before ADK initialises

from google.adk.runners import InMemoryRunner          # lightweight local runner
from google.genai import types as genai_types

from retail_agent.agent import root_agent              # your LlmAgent


# ── ANSI colour helpers (gracefully degraded on Windows) ─────────────────────

def _c(code: str, text: str) -> str:
    """Wrap text in an ANSI escape if stdout is a tty."""
    if sys.stdout.isatty():
        return f"\033[{code}m{text}\033[0m"
    return text

BOLD   = lambda t: _c("1",    t)
DIM    = lambda t: _c("2",    t)
GREEN  = lambda t: _c("32",   t)
CYAN   = lambda t: _c("36",   t)
YELLOW = lambda t: _c("33",   t)
RED    = lambda t: _c("31",   t)


# ── Banner ────────────────────────────────────────────────────────────────────

BANNER = f"""
{BOLD(CYAN('╔══════════════════════════════════════════╗'))}
{BOLD(CYAN('║   🛒  Retail Support Agent  — CLI        ║'))}
{BOLD(CYAN('╚══════════════════════════════════════════╝'))}
{DIM('Type your message and press Enter.')}
{DIM('Commands:  /quit  /exit  /new  /session')}
"""


# ── Core runner loop ──────────────────────────────────────────────────────────

async def run_session(session_id: str) -> None:
    """Start (or resume) one interactive session."""

    runner = InMemoryRunner(agent=root_agent, app_name="retail_cli")

    # ADK sessions are keyed by (app_name, user_id, session_id).
    # We use a fixed user_id so the runner wires state correctly.
    USER_ID = "cli_operator"

    # Create (or retrieve) the session
    session = await runner.session_service.create_session(
        app_name="retail_cli",
        user_id=USER_ID,
        session_id=session_id,
    )

    print(BANNER)
    print(DIM(f"  Session ID : {session.id}"))
    print(DIM(f"  Use '/new' to start a fresh session, '/quit' to exit.\n"))

    while True:
        # ── Prompt ──
        try:
            raw = input(BOLD(GREEN("you> "))).strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{YELLOW('Goodbye!')}")
            break

        if not raw:
            continue

        # ── Built-in slash commands ──
        if raw.lower() in ("/quit", "/exit"):
            print(YELLOW("Goodbye!"))
            break

        if raw.lower() == "/new":
            new_id = str(uuid.uuid4())[:8]
            print(DIM(f"Starting new session: {new_id}\n"))
            await run_session(new_id)
            return

        if raw.lower() == "/session":
            print(DIM(f"Current session ID: {session.id}"))
            continue

        # ── Send message to the agent ──
        user_content = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=raw)],
        )

        print(BOLD(CYAN("\nagent> ")), end="", flush=True)

        full_reply: list[str] = []

        try:
            async for event in runner.run_async(
                user_id=USER_ID,
                session_id=session.id,
                new_message=user_content,
            ):
                # ADK emits various event types; we care about final text replies.
                if not event.is_final_response():
                    continue

                response = event.content
                if not response or not response.parts:
                    continue

                for part in response.parts:
                    text = getattr(part, "text", None)
                    if text:
                        full_reply.append(text)

        except Exception as exc:
            print(RED(f"\n[Error] {exc}"))
            continue

        reply = "".join(full_reply).strip()
        if reply:
            # Pretty-print: indent agent lines slightly
            formatted = "\n".join(f"  {line}" for line in reply.splitlines())
            print(formatted)
        else:
            print(DIM("  (no response)"))

        print()   # blank line between turns


# ── CLI argument parsing ──────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python cli.py",
        description="Interactive CLI for the Retail Support Agent.",
    )
    parser.add_argument(
        "--session", "-s",
        metavar="SESSION_ID",
        default=str(uuid.uuid4())[:8],
        help="Session ID to create or resume (default: random short ID).",
    )
    return parser.parse_args()


# ── Entrypoint ────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    try:
        asyncio.run(run_session(args.session))
    except KeyboardInterrupt:
        print(f"\n{YELLOW('Interrupted. Goodbye!')}")


if __name__ == "__main__":
    main()