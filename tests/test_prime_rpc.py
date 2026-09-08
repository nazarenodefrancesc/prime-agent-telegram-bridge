from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from prime_telegram_bridge.config import BridgeConfig
from prime_telegram_bridge.prime_rpc import (
    PrimeAgentOutcome,
    PrimeRpcError,
    PrimeRpcFrameTooLarge,
    PrimeRpcSession,
    _assistant_outcome_from_agent_end,
    _prime_subprocess_env,
)


def make_config(
    tmp_path: Path, binary: str, *, max_line_bytes: int = 16 * 1024 * 1024
) -> BridgeConfig:
    return BridgeConfig(
        telegram_bot_token="x",
        telegram_allowed_user_ids=frozenset({1}),
        telegram_allowed_chat_ids=frozenset(),
        telegram_poll_timeout=1,
        telegram_max_attachment_bytes=1024,
        telegram_attachment_retention_hours=24,
        prime_agent_bin=binary,
        prime_workdir=tmp_path,
        prime_session_dir=tmp_path / "sessions",
        prime_rpc_max_line_bytes=max_line_bytes,
        prime_provider=None,
        prime_model=None,
        prime_thinking=None,
        state_dir=tmp_path / "state",
        log_level="DEBUG",
    )


def make_wrapper(tmp_path: Path, script: Path, name: str = "fake-prime") -> Path:
    wrapper = tmp_path / name
    wrapper.write_text(f"#!/bin/sh\nexec {sys.executable} {script} \"$@\"\n", encoding="utf-8")
    wrapper.chmod(0o755)
    return wrapper


@pytest.mark.asyncio
async def test_rpc_session_prompt_round_trip(tmp_path: Path):
    fake = Path(__file__).with_name("fake_prime_rpc.py")
    wrapper = make_wrapper(tmp_path, fake)
    session = PrimeRpcSession(make_config(tmp_path, str(wrapper)), chat_id=1)
    try:
        await session.start()
        answer = await session.ask("hello", timeout=5)
        assert answer == "echo:hello"
        state = await session.get_state()
        assert state["sessionId"] == "fake-session"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_new_session_updates_resume_target(tmp_path: Path):
    fake = Path(__file__).with_name("fake_prime_rpc.py")
    wrapper = make_wrapper(tmp_path, fake)
    session = PrimeRpcSession(make_config(tmp_path, str(wrapper)), chat_id=1)
    try:
        await session.start()
        before = session.resume_session
        cancelled, state = await session.new_session()
        assert not cancelled
        assert state["sessionId"] == "fake-session-1"
        assert session.resume_session == state["sessionFile"]
        assert session.resume_session != before
    finally:
        await session.close()


def test_prime_subprocess_env_strips_bridge_secrets_but_keeps_provider_keys():
    env = _prime_subprocess_env(
        {
            "TELEGRAM_BOT_TOKEN": "secret",
            "TELEGRAM_ALLOWED_USER_IDS": "1",
            "BRIDGE_STATE_DIR": "/private",
            "OPENROUTER_API_KEY": "provider-key",
            "PRIME_API_KEY": "prime-key",
            "PATH": "/bin",
        }
    )
    assert "TELEGRAM_BOT_TOKEN" not in env
    assert "TELEGRAM_ALLOWED_USER_IDS" not in env
    assert "BRIDGE_STATE_DIR" not in env
    assert env["OPENROUTER_API_KEY"] == "provider-key"
    assert env["PRIME_API_KEY"] == "prime-key"
    assert env["PATH"] == "/bin"


def test_prime_subprocess_env_respects_explicit_empty_mapping(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PRIME_API_KEY", "host-key")
    assert _prime_subprocess_env({}) == {}


def test_agent_end_outcome_extracts_text_and_error():
    text = _assistant_outcome_from_agent_end(
        {
            "type": "agent_end",
            "messages": [
                {"role": "assistant", "content": [{"type": "text", "text": "ok"}]}
            ],
        }
    )
    assert text == PrimeAgentOutcome(text="ok")

    error = _assistant_outcome_from_agent_end(
        {
            "type": "agent_end",
            "messages": [
                {
                    "role": "assistant",
                    "content": [],
                    "stopReason": "error",
                    "errorMessage": "provider failed",
                }
            ],
        }
    )
    assert error == PrimeAgentOutcome(error="provider failed")


@pytest.mark.asyncio
async def test_process_exit_fails_ask_without_waiting_for_timeout(tmp_path: Path):
    script = tmp_path / "crash_rpc.py"
    script.write_text(
        """
import json, sys
from pathlib import Path
for raw in sys.stdin:
    cmd=json.loads(raw); typ=cmd.get('type'); rid=cmd.get('id')
    if typ=='get_state':
        data = {
            'sessionFile': str(Path.cwd()/'s.jsonl'),
            'sessionId': 's',
            'isStreaming': False,
            'thinkingLevel': 'medium',
        }
        response = {'id':rid, 'type':'response', 'command':typ, 'success':True, 'data':data}
        print(json.dumps(response), flush=True)
    elif typ=='prompt':
        response = {'id':rid, 'type':'response', 'command':typ, 'success':True}
        print(json.dumps(response), flush=True)
        sys.exit(17)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    wrapper = make_wrapper(tmp_path, script, "crash-prime")
    session = PrimeRpcSession(make_config(tmp_path, str(wrapper)), chat_id=1)
    try:
        await session.start()
        with pytest.raises(PrimeRpcError, match="stdout closed"):
            await asyncio.wait_for(session.ask("boom", timeout=60), timeout=3)
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_close_sends_eof_before_force_terminating_rpc_client(tmp_path: Path):
    marker = tmp_path / "eof.marker"
    script = tmp_path / "graceful_rpc.py"
    script.write_text(
        f"""
import json, sys
from pathlib import Path
marker = Path({str(marker)!r})
for raw in sys.stdin:
    cmd = json.loads(raw)
    if cmd.get('type') == 'get_state':
        print(json.dumps({{'id': cmd['id'], 'type': 'response', 'command': 'get_state',
            'success': True, 'data': {{'sessionFile': str(Path.cwd()/'s.jsonl'),
            'sessionId': 's'}}}}), flush=True)
marker.write_text('eof', encoding='utf-8')
""".strip()
        + "\n",
        encoding="utf-8",
    )
    wrapper = make_wrapper(tmp_path, script, "graceful-prime")
    session = PrimeRpcSession(make_config(tmp_path, str(wrapper)), chat_id=1)
    await session.start()
    await session.close()
    assert marker.read_text(encoding="utf-8") == "eof"


@pytest.mark.asyncio
async def test_later_autonomous_agent_end_is_delivered_once(tmp_path: Path):
    script = tmp_path / "autonomous_rpc.py"
    script.write_text(
        """
import json, sys, time
from pathlib import Path
for raw in sys.stdin:
    cmd=json.loads(raw); typ=cmd.get('type'); rid=cmd.get('id')
    if typ=='get_state':
        data = {
            'sessionFile': str(Path.cwd()/'s.jsonl'),
            'sessionId': 's',
            'isStreaming': False,
            'thinkingLevel': 'medium',
        }
        response = {'id':rid, 'type':'response', 'command':typ, 'success':True, 'data':data}
        print(json.dumps(response), flush=True)
    elif typ=='prompt':
        response = {'id':rid, 'type':'response', 'command':typ, 'success':True}
        print(json.dumps(response), flush=True)
        print(json.dumps({'type':'agent_start'}), flush=True)
        first = {
            'type':'agent_end',
            'messages':[{'role':'assistant','content':[{'type':'text','text':'first'}],'stopReason':'stop'}],
        }
        print(json.dumps(first), flush=True)
        time.sleep(0.05)
        print(json.dumps({'type':'agent_start'}), flush=True)
        second = {
            'type':'agent_end',
            'messages':[
                {
                    'role':'assistant',
                    'content':[{'type':'text','text':'child follow-up'}],
                    'stopReason':'stop',
                }
            ],
        }
        print(json.dumps(second), flush=True)
    elif typ=='get_last_assistant_text':
        response = {
            'id':rid, 'type':'response', 'command':typ, 'success':True, 'data':{'text':'first'}
        }
        print(json.dumps(response), flush=True)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    wrapper = make_wrapper(tmp_path, script, "autonomous-prime")
    session = PrimeRpcSession(make_config(tmp_path, str(wrapper)), chat_id=1)
    received: list[PrimeAgentOutcome] = []
    arrived = asyncio.Event()

    async def listener(outcome: PrimeAgentOutcome) -> None:
        received.append(outcome)
        arrived.set()

    session.add_agent_end_listener(listener)
    try:
        await session.start()
        assert await session.ask("go", timeout=5) == "first"
        await asyncio.wait_for(arrived.wait(), timeout=2)
        assert received == [PrimeAgentOutcome(text="child follow-up")]
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_autonomous_error_does_not_fall_back_to_stale_text(tmp_path: Path):
    session = PrimeRpcSession(make_config(tmp_path, os.devnull), chat_id=1)
    received: list[PrimeAgentOutcome] = []
    done = asyncio.Event()

    async def listener(outcome: PrimeAgentOutcome) -> None:
        received.append(outcome)
        done.set()

    session.add_agent_end_listener(listener)
    session._publish_autonomous_agent_end(
        {
            "type": "agent_end",
            "messages": [
                {
                    "role": "assistant",
                    "content": [],
                    "stopReason": "error",
                    "errorMessage": "later failure",
                }
            ],
        }
    )
    await asyncio.wait_for(done.wait(), timeout=1)
    assert received == [PrimeAgentOutcome(error="later failure")]
    await session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("reply_size", [128 * 1024, 1024 * 1024])
async def test_rpc_accepts_large_jsonl_agent_end_frames(tmp_path: Path, reply_size: int):
    script = tmp_path / "large_rpc.py"
    script.write_text(
        f"""
import json, sys
from pathlib import Path
reply_size = {reply_size}
for raw in sys.stdin:
    cmd=json.loads(raw); typ=cmd.get('type'); rid=cmd.get('id')
    if typ=='get_state':
        data = {{
            'sessionFile': str(Path.cwd()/'large.jsonl'),
            'sessionId': 'large',
            'isStreaming': False,
            'thinkingLevel': 'medium',
        }}
        print(json.dumps({{'id':rid,'type':'response','command':typ,'success':True,'data':data}}), flush=True)
    elif typ=='prompt':
        print(json.dumps({{'id':rid,'type':'response','command':typ,'success':True}}), flush=True)
        print(json.dumps({{'type':'agent_start'}}), flush=True)
        event = {{
            'type':'agent_end',
            'messages':[{{
                'role':'assistant',
                'content':[{{'type':'text','text':'x' * reply_size}}],
                'stopReason':'stop',
            }}],
        }}
        print(json.dumps(event), flush=True)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    wrapper = make_wrapper(tmp_path, script, "large-prime")
    session = PrimeRpcSession(make_config(tmp_path, str(wrapper)), chat_id=1)
    try:
        await session.start()
        answer = await session.ask("large", timeout=5)
        assert len(answer) == reply_size
        assert answer.startswith("x")
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_rpc_frame_over_configured_limit_fails_without_prompt_replay(tmp_path: Path):
    count_file = tmp_path / "prompt-count.txt"
    script = tmp_path / "oversize_rpc.py"
    script.write_text(
        f"""
import json, sys
from pathlib import Path
count_file = Path({str(count_file)!r})
for raw in sys.stdin:
    cmd=json.loads(raw); typ=cmd.get('type'); rid=cmd.get('id')
    if typ=='get_state':
        data = {{
            'sessionFile': str(Path.cwd()/'oversize.jsonl'),
            'sessionId': 'oversize',
            'isStreaming': False,
            'thinkingLevel': 'medium',
        }}
        print(json.dumps({{'id':rid,'type':'response','command':typ,'success':True,'data':data}}), flush=True)
    elif typ=='prompt':
        old = int(count_file.read_text()) if count_file.exists() else 0
        count_file.write_text(str(old + 1))
        print(json.dumps({{'id':rid,'type':'response','command':typ,'success':True}}), flush=True)
        print(json.dumps({{'type':'agent_start'}}), flush=True)
        event = {{
            'type':'agent_end',
            'messages':[{{
                'role':'assistant',
                'content':[{{'type':'text','text':'x' * (128 * 1024)}}],
                'stopReason':'stop',
            }}],
        }}
        print(json.dumps(event), flush=True)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    wrapper = make_wrapper(tmp_path, script, "oversize-prime")
    config = make_config(tmp_path, str(wrapper), max_line_bytes=64 * 1024)
    session = PrimeRpcSession(config, chat_id=1)
    try:
        await session.start()
        with pytest.raises(PrimeRpcFrameTooLarge, match="not retried"):
            await asyncio.wait_for(session.ask("oversize", timeout=60), timeout=3)
        assert count_file.read_text() == "1"
        # A caller can immediately make a new explicit RPC operation; start()
        # waits for the failed reader to finish reaping the old subprocess.
        state = await session.get_state(timeout=3)
        assert state["sessionId"] == "oversize"
        assert count_file.read_text() == "1"
    finally:
        await session.close()
