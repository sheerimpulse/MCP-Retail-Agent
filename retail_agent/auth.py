# retail_agent/auth.py
"""
Mock login layer for the retail support agent.

In production, replace MOCK_USERS with a real credential check
(e.g. a DB query, LDAP call, or OAuth token validation).
"""

from __future__ import annotations
import hashlib
import re
import sys

# ── Mock credential store ─────────────────────────────────────────────────────
# Passwords are stored as SHA-256 hashes.
# Add a user:  python -c "import hashlib; print(hashlib.sha256(b'pw').hexdigest())"

def _h(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

MOCK_USERS: dict[str, dict] = {
    "alice": {
        "password_hash": _h("alice123"),
        "role": "agent",
        "display_name": "Alice (Support Agent)",
    },
    "bob": {
        "password_hash": _h("bob456"),
        "role": "manager",
        "display_name": "Bob (Manager)",
    },
    "admin": {
        "password_hash": _h("admin"),
        "role": "admin",
        "display_name": "Admin",
    },
}

# ── Session state keys (single source of truth) ───────────────────────────────
AUTH_STATE_KEY   = "authenticated"   # bool  — is this session logged in?
USER_STATE_KEY   = "current_user"    # str   — username
ROLE_STATE_KEY   = "current_role"    # str   — role (agent / manager / admin)
PENDING_AUTH_KEY = "pending_auth"    # bool  — waiting for credentials this turn?


# ── Core helpers ──────────────────────────────────────────────────────────────

def validate_login(username: str, password: str) -> dict | None:
    """
    Returns the user record on success, None on failure.
    Swap this body to integrate a real auth backend.
    """
    user = MOCK_USERS.get(username.lower().strip())
    if user and user["password_hash"] == _h(password):
        return user
    return None


def parse_credentials(text: str) -> tuple[str, str] | None:
    """
    Extract username / password from a free-text message.

    Accepted formats (all case-insensitive):
        username: alice  password: alice123
        user: alice  pass: alice123
        alice alice123          <- bare "<user> <pass>" fallback
    """
    # Named format: username/user + password/pass/pw
    m = re.search(
        r'(?:username|user)\s*[:\s]\s*(\S+).*?(?:password|pass|pw)\s*[:\s]\s*(\S+)',
        text, re.IGNORECASE | re.DOTALL,
    )
    if m:
        return m.group(1), m.group(2)

    # Bare two-token fallback: "alice alice123"
    tokens = text.strip().split()
    if len(tokens) == 2:
        return tokens[0], tokens[1]

    return None


# ── UI strings ────────────────────────────────────────────────────────────────

def login_prompt() -> str:
    return (
        "🔐 **Retail Support Agent — Login Required**\n\n"
        "Please provide your credentials to continue.\n\n"
        "**Format:** `username: <user>  password: <pass>`\n\n"
        "_Example:_ `username: alice  password: alice123`"
    )


def login_success_message(user: dict) -> str:
    role = user["role"].capitalize()
    name = user["display_name"]
    return (
        f"✅ **Login successful.** Welcome, {name}! *(Role: {role})*\n\n"
        "You can now use the retail support agent. How can I help you today?"
    )


def login_failure_message() -> str:
    return (
        "❌ **Invalid credentials.** Please try again.\n\n"
        "**Format:** `username: <user>  password: <pass>`"
    )