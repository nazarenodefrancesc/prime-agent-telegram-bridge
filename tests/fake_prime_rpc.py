from __future__ import annotations

import json
import sys
from pathlib import Path

session_file = str(Path.cwd() / "fake-session.jsonl")
last_text = None
session_id = "fake-session"
name = None

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
        print(json.dumps({"id": req_id, "type": "response", "command": typ, "success": True, "data": data}), flush=True)
    elif typ == "set_session_name":
        name = cmd.get("name")
        print(json.dumps({"id": req_id, "type": "response", "command": typ, "success": True}), flush=True)
    elif typ == "set_thinking_level":
        print(json.dumps({"id": req_id, "type": "response", "command": typ, "success": True}), flush=True)
    elif typ == "prompt":
        last_text = f"echo:{cmd.get('message')}"
        print(json.dumps({"id": req_id, "type": "response", "command": typ, "success": True}), flush=True)
        print(json.dumps({"type": "agent_start"}), flush=True)
        print(json.dumps({"type": "agent_end"}), flush=True)
    elif typ == "get_last_assistant_text":
        print(json.dumps({"id": req_id, "type": "response", "command": typ, "success": True, "data": {"text": last_text}}), flush=True)
    elif typ == "abort":
        print(json.dumps({"id": req_id, "type": "response", "command": typ, "success": True}), flush=True)
    elif typ == "new_session":
        print(json.dumps({"id": req_id, "type": "response", "command": typ, "success": True, "data": {"cancelled": False}}), flush=True)
    else:
        print(json.dumps({"id": req_id, "type": "response", "command": typ, "success": True, "data": {}}), flush=True)
