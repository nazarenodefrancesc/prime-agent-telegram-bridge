from __future__ import annotations

import json
import sys
from pathlib import Path

session_file = str(Path.cwd() / "fake-session.jsonl")
last_text = None
session_id = "fake-session"
name = None
session_counter = 0


def assistant(text: str, *, error: str | None = None) -> dict:
    return {
        "role": "assistant",
        "content": [{"type": "text", "text": text}] if text else [],
        "stopReason": "error" if error else "stop",
        "errorMessage": error,
    }


for raw in sys.stdin:
    cmd = json.loads(raw)
    req_id = cmd.get("id")
    typ = cmd.get("type")
    if typ == "get_state":
        data = {
            "model": {"provider": "fake", "id": "fake-model"},
            "thinkingLevel": "medium",
            "isStreaming": False,
            "sessionFile": session_file,
            "sessionId": session_id,
            "sessionName": name,
        }
        response = {"id": req_id, "type": "response", "command": typ, "success": True, "data": data}
        print(json.dumps(response), flush=True)
    elif typ == "set_session_name":
        name = cmd.get("name")
        print(json.dumps({"id": req_id, "type": "response", "command": typ, "success": True}), flush=True)
    elif typ == "set_thinking_level":
        print(json.dumps({"id": req_id, "type": "response", "command": typ, "success": True}), flush=True)
    elif typ == "prompt":
        last_text = f"echo:{cmd.get('message')}"
        print(json.dumps({"id": req_id, "type": "response", "command": typ, "success": True}), flush=True)
        print(json.dumps({"type": "agent_start"}), flush=True)
        print(json.dumps({"type": "agent_end", "messages": [assistant(last_text)]}), flush=True)
    elif typ == "get_last_assistant_text":
        response = {
            "id": req_id, "type": "response", "command": typ, "success": True, "data": {"text": last_text}
        }
        print(json.dumps(response), flush=True)
    elif typ == "abort":
        print(json.dumps({"id": req_id, "type": "response", "command": typ, "success": True}), flush=True)
    elif typ == "new_session":
        session_counter += 1
        session_id = f"fake-session-{session_counter}"
        session_file = str(Path.cwd() / f"fake-session-{session_counter}.jsonl")
        response = {
            "id": req_id, "type": "response", "command": typ, "success": True, "data": {"cancelled": False}
        }
        print(json.dumps(response), flush=True)
    else:
        response = {"id": req_id, "type": "response", "command": typ, "success": True, "data": {}}
        print(json.dumps(response), flush=True)
