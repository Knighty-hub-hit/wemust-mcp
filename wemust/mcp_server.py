"""Stdio MCP server for WeMust (read-only).

JSON-RPC 2.0 over newline-delimited stdin/stdout, implementing the MCP methods
`initialize`, `tools/list`, and `tools/call`. No third-party dependencies.

Tools (all read-only, against the authenticated user's own account):
  - get_timetable  : today / this week / a date range of class timetable
  - get_notices    : recent WeMust announcements
  - get_messages   : in-site reminders (unread count + current)
  - get_calendar   : personal calendar events

  - get_grades     : DISABLED by default. Only registered when
                     WEMUST_ENABLE_GRADES=1. Enabling it means grade values
                     (courses, final grades, GPA/CGPA) will be sent to whatever
                     LLM client is connected. Off by default on purpose.
"""
import sys
import json

from .config import Config, ConfigError
from .client import WeMustClient, WeMustError

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "wemust-mcp"
SERVER_VERSION = "0.1.0"


# --- tool definitions ---
def _base_tools():
    return [
        {
            "name": "get_timetable",
            "description": "Read the student's class timetable (read-only). "
                           "scope 'today', 'week', or 'range' (range needs start & end).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "enum": ["today", "week", "range"],
                              "default": "today"},
                    "start": {"type": "string", "description": "YYYY-MM-DD (range only)"},
                    "end": {"type": "string", "description": "YYYY-MM-DD (range only)"},
                },
            },
        },
        {
            "name": "get_notices",
            "description": "Read recent WeMust announcements (read-only).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "default": 7},
                    "limit": {"type": "integer", "default": 20},
                },
            },
        },
        {
            "name": "get_messages",
            "description": "Read in-site reminders: unread count and current message (read-only).",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "get_calendar",
            "description": "Read the student's personal calendar events (read-only).",
            "inputSchema": {
                "type": "object",
                "properties": {"days": {"type": "integer", "default": 7}},
            },
        },
    ]


def _grades_tool():
    return {
        "name": "get_grades",
        "description": "Read the student's transcript: courses, final grades and GPA/CGPA. "
                       "WARNING: this sends grade values to the connected LLM client. "
                       "Only available because WEMUST_ENABLE_GRADES=1.",
        "inputSchema": {"type": "object", "properties": {}},
    }


class ServerState:
    def __init__(self, cfg=None):
        self.cfg = cfg if cfg is not None else Config()
        self._client = None

    def tools(self):
        tools = _base_tools()
        if self.cfg.enable_grades:
            tools.append(_grades_tool())
        return tools

    def client(self):
        if self._client is None:
            username = self.cfg.require_username()
            self._client = WeMustClient(username, self.cfg.get_password)
        return self._client


# --- JSON-RPC helpers ---
def _ok(mid, result):
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _err(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def _call_tool(state, name, args):
    args = args or {}
    c = state.client()
    if name == "get_timetable":
        return c.get_timetable(scope=args.get("scope", "today"),
                               start=args.get("start"), end=args.get("end"))
    if name == "get_notices":
        return c.get_notices(days=int(args.get("days", 7)), limit=int(args.get("limit", 20)))
    if name == "get_messages":
        return c.get_messages()
    if name == "get_calendar":
        return c.get_calendar(days=int(args.get("days", 7)))
    if name == "get_grades":
        if not state.cfg.enable_grades:
            raise WeMustError("get_grades is disabled (set WEMUST_ENABLE_GRADES=1 to enable).")
        return c.get_grades_raw()
    raise WeMustError("unknown tool: %s" % name)


def handle(msg, state):
    """Handle one JSON-RPC message. Returns a response dict, or None for notifications.

    `initialize` and `tools/list` never touch the network.
    """
    method = msg.get("method")
    mid = msg.get("id")
    # Notifications (no id) require no response.
    if mid is None and method and method.startswith("notifications/"):
        return None

    if method == "initialize":
        return _ok(mid, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    if method == "ping":
        return _ok(mid, {})
    if method == "tools/list":
        return _ok(mid, {"tools": state.tools()})
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            result = _call_tool(state, name, args)
            text = json.dumps(result, ensure_ascii=False, indent=2)
            return _ok(mid, {"content": [{"type": "text", "text": text}], "isError": False})
        except (WeMustError, ConfigError) as ex:
            return _ok(mid, {"content": [{"type": "text", "text": str(ex)}], "isError": True})
        except Exception as ex:  # never leak secrets; only the exception type/class
            return _ok(mid, {"content": [{"type": "text",
                                          "text": "error: %s" % type(ex).__name__}],
                             "isError": True})
    if mid is None:
        return None
    return _err(mid, -32601, "method not found: %s" % method)


def main():
    state = ServerState()
    inp = sys.stdin
    out = sys.stdout
    for line in inp:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            out.write(json.dumps(_err(None, -32700, "parse error")) + "\n")
            out.flush()
            continue
        resp = handle(msg, state)
        if resp is not None:
            out.write(json.dumps(resp, ensure_ascii=False) + "\n")
            out.flush()


if __name__ == "__main__":
    main()
