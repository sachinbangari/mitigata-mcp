"""
Mitigata Agent Tools — an MCP server
====================================

Exposes a few safe "autonomous action" tools that an AI agent can call:
  - create_note / read_note / list_notes  (a tiny notes store, saved to notes.json)
  - calculate                             (safe arithmetic only)
  - send_email                            (MOCK — records to sent_emails.log, never really sends)

It runs as a network (streamable-HTTP) MCP server so it can be placed behind
SentinelOne's MCP gateway: the agent connects to the gateway URL, the gateway
forwards to this server while inspecting every tool call.

Run:   python mcp_server.py
Listens on  http://0.0.0.0:9000/mcp  by default (set MCP_HOST / MCP_PORT to change).
"""

import os
import ast
import json
import operator
from pathlib import Path

from mcp.server.fastmcp import FastMCP

HOST = os.getenv("MCP_HOST", "0.0.0.0")
# Hosts like Render provide PORT; fall back to MCP_PORT, then 9000 locally.
PORT = int(os.getenv("PORT", os.getenv("MCP_PORT", "9000")))

mcp = FastMCP("mitigata-agent-tools", host=HOST, port=PORT)

BASE_DIR   = Path(__file__).parent
NOTES_FILE = BASE_DIR / "notes.json"
EMAIL_LOG  = BASE_DIR / "sent_emails.log"


# ---------- notes ----------
def _load_notes() -> dict:
    try:
        return json.loads(NOTES_FILE.read_text())
    except Exception:
        return {}


def _save_notes(notes: dict) -> None:
    NOTES_FILE.write_text(json.dumps(notes, indent=2))


@mcp.tool()
def create_note(title: str, content: str) -> str:
    """Create or overwrite a note with the given title and content."""
    notes = _load_notes()
    notes[title] = content
    _save_notes(notes)
    return f"Saved note '{title}'."


@mcp.tool()
def read_note(title: str) -> str:
    """Read the content of a saved note by its title."""
    notes = _load_notes()
    return notes.get(title, f"No note titled '{title}' was found.")


@mcp.tool()
def list_notes() -> str:
    """List the titles of all saved notes."""
    notes = _load_notes()
    return ", ".join(notes.keys()) if notes else "There are no notes yet."


# ---------- calculator (safe: arithmetic only, no code execution) ----------
_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("unsupported expression")


@mcp.tool()
def calculate(expression: str) -> str:
    """Evaluate a basic arithmetic expression, e.g. '3 * (4 + 5) / 2'."""
    try:
        return str(_eval(ast.parse(expression, mode="eval").body))
    except Exception:
        return "Could not evaluate that expression (arithmetic only)."


# ---------- mock email ----------
@mcp.tool()
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email. MOCK: this records the email locally and never actually sends it."""
    with EMAIL_LOG.open("a", encoding="utf-8") as f:
        f.write(f"TO: {to}\nSUBJECT: {subject}\nBODY: {body}\n-----\n")
    return f"Email queued to {to} with subject '{subject}'. (mock — not really sent)"


if __name__ == "__main__":
    print(f"MCP server 'mitigata-agent-tools' on http://{HOST}:{PORT}/mcp")
    mcp.run(transport="streamable-http")
