# api.py
import asyncio, json, uuid
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from google.adk.runners import InMemoryRunner
from google.adk.sessions import InMemorySessionService
from retail_agent.agent import root_agent
import aiosqlite
from mcp_server.database import DB_PATH

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

runner = InMemoryRunner(agent=root_agent, app_name="retail_cli")
runner.auto_create_session = True
session_service = runner.session_service

# Store sessions keyed by browser session_id
sessions: dict[str, str] = {}  # browser_id → adk_session_id

async def get_or_create_session(browser_id: str) -> str:
    if browser_id not in sessions:
        session = await session_service.create_session(
            app_name=APP_NAME,
            user_id=browser_id
        )
        sessions[browser_id] = session.id
    return sessions[browser_id]


@app.post("/chat")
async def chat(request: Request):
    from google.genai import types as genai_types
    import re

    body = await request.json()
    message = body.get("message", "")
    browser_id = body.get("session_id", "default")

    events_out = []
    async for event in runner.run_async(
        user_id=browser_id,
        session_id=browser_id,  # use browser_id as session_id too
        new_message=genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=message)]
        ),
    ):
        events_out.append(event)
    # Extract the final text reply
    reply = ""
    tool_trace = []
    stop_reason = "end_turn"

    for event in events_out:
        # Agent text response
        if hasattr(event, "content") and event.content:
            for part in event.content.parts or []:
                if hasattr(part, "text") and part.text:
                    reply += part.text

        # Tool calls — build trace entries
        if hasattr(event, "tool_call"):
            tc = event.tool_call
            tool_trace.append({
                "tool": tc.name,
                "args": tc.args,
                "type": "call"
            })
        if hasattr(event, "tool_response"):
            tr = event.tool_response
            tool_trace.append({
                "tool": tr.name,
                "result": tr.result,
                "type": "response"
            })

    # Pull stop_reason from reply text if present
    import re
    m = re.search(r'\[stop_reason:\s*(\w+)\]', reply)
    if m:
        stop_reason = m.group(1)

    return {
        "reply": reply,
        "tool_trace": tool_trace,
        "stop_reason": stop_reason,
        "session_id": browser_id,
    }


@app.delete("/session/{browser_id}")
async def reset_session(browser_id: str):
    # Nothing to clean up — runner manages its own sessions
    return {"status": "reset"}

@app.get("/customers")
async def get_customers():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, name, email, phone, segment FROM customers ORDER BY name"
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


# Serve the dashboard HTML
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    with open("dashboard.html") as f:
        return f.read()