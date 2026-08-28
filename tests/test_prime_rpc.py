from __future__ import annotations

import sys
from pathlib import Path

import pytest

from prime_telegram_bridge.config import BridgeConfig
from prime_telegram_bridge.prime_rpc import PrimeRpcSession


@pytest.mark.asyncio
async def test_rpc_session_prompt_round_trip(tmp_path: Path):
    fake = Path(__file__).with_name("fake_prime_rpc.py")
    # Use a small wrapper shell so PrimeRpcSession's binary+args contract can be tested without Prime installed.
    wrapper = tmp_path / "fake-prime"
    wrapper.write_text(f"#!/bin/sh\nexec {sys.executable} {fake} \"$@\"\n", encoding="utf-8")
    wrapper.chmod(0o755)
    cfg = BridgeConfig(
        telegram_bot_token="x",
        telegram_allowed_user_ids=frozenset({1}),
        telegram_allowed_chat_ids=frozenset(),
        telegram_poll_timeout=1,
        telegram_max_attachment_bytes=1024,
        prime_agent_bin=str(wrapper),
        prime_workdir=tmp_path,
        prime_session_dir=tmp_path / "sessions",
        prime_provider=None,
        prime_model=None,
        prime_thinking=None,
        state_dir=tmp_path / "state",
        log_level="DEBUG",
    )
    session = PrimeRpcSession(cfg, chat_id=1)
    try:
        await session.start()
        answer = await session.ask("hello", timeout=5)
        assert answer == "echo:hello"
        state = await session.get_state()
        assert state["sessionId"] == "fake-session"
    finally:
        await session.close()
