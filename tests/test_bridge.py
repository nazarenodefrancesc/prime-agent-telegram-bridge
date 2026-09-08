from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from prime_telegram_bridge.bridge import PrimeSessionManager, TelegramPrimeBridge
from prime_telegram_bridge.config import BridgeConfig
from prime_telegram_bridge.prime_rpc import PrimeAgentOutcome, PrimeRpcError, PrimeRpcSession
from prime_telegram_bridge.state import ChatSessionRecord
from prime_telegram_bridge.telegram_api import IncomingMessage


def make_config(tmp_path: Path) -> BridgeConfig:
    return BridgeConfig(
        telegram_bot_token="telegram-secret",
        telegram_allowed_user_ids=frozenset({1}),
        telegram_allowed_chat_ids=frozenset(),
        telegram_poll_timeout=1,
        telegram_max_attachment_bytes=1024,
        telegram_attachment_retention_hours=24,
        prime_agent_bin="prime-agent",
        prime_workdir=tmp_path,
        prime_session_dir=tmp_path / "sessions",
        prime_rpc_max_line_bytes=16 * 1024 * 1024,
        prime_provider=None,
        prime_model=None,
        prime_thinking=None,
        state_dir=tmp_path / "state",
        log_level="DEBUG",
    )


class FakeSession:
    def __init__(self, session_file: str = "/tmp/session.jsonl"):
        self.resume_session: str | None = session_file
        self.session_file = session_file
        self.names: list[str] = []
        self.cancel_new = False

    async def set_session_name(self, name: str) -> None:
        self.names.append(name)

    async def get_state(self, **_kwargs: Any) -> dict[str, Any]:
        return {
            "sessionFile": self.session_file,
            "sessionId": "session-id",
            "sessionName": self.names[-1] if self.names else None,
        }

    async def new_session(self) -> tuple[bool, dict[str, Any]]:
        if not self.cancel_new:
            self.session_file = "/tmp/new-session.jsonl"
        return self.cancel_new, await self.get_state()

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_session_manager_initialization_is_single_flight(tmp_path: Path):
    manager = PrimeSessionManager(make_config(tmp_path))
    session = FakeSession()
    calls = 0

    async def start_session(chat_id: int, *, resume: str | None):
        nonlocal calls
        calls += 1
        assert chat_id == 99
        assert resume is None
        await asyncio.sleep(0.05)
        return session

    manager._start_session = start_session  # type: ignore[method-assign]
    first, second = await asyncio.gather(manager.get(99), manager.get(99))
    assert first is session
    assert second is session
    assert calls == 1


@pytest.mark.asyncio
async def test_session_manager_recovers_when_saved_resume_cannot_start(tmp_path: Path):
    manager = PrimeSessionManager(make_config(tmp_path))
    manager.store.set(ChatSessionRecord(chat_id=99, session_file="/missing/old.jsonl"))
    fresh = FakeSession("/tmp/recovered.jsonl")
    attempts: list[str | None] = []

    async def start_session(_chat_id: int, *, resume: str | None):
        attempts.append(resume)
        return fresh

    manager._start_session = start_session  # type: ignore[method-assign]
    result = await manager.get(99)
    assert result is fresh
    assert attempts == [None]
    assert fresh.names == ["telegram-99"]
    record = manager.store.get(99)
    assert record is not None
    assert record.session_file == "/tmp/recovered.jsonl"


@pytest.mark.asyncio
async def test_cancelled_new_session_keeps_current_mapping(tmp_path: Path):
    manager = PrimeSessionManager(make_config(tmp_path))
    session = FakeSession("/tmp/current.jsonl")
    session.cancel_new = True
    manager.sessions[99] = session  # type: ignore[assignment]
    cancelled, state = await manager.new(99)
    assert cancelled
    assert state["sessionFile"] == "/tmp/current.jsonl"
    assert session.names == []
    record = manager.store.get(99)
    assert record is not None
    assert record.session_file == "/tmp/current.jsonl"


@pytest.mark.asyncio
async def test_normal_get_does_not_destroy_mapping_on_resume_startup_error(tmp_path: Path):
    manager = PrimeSessionManager(make_config(tmp_path))
    saved = tmp_path / "old.jsonl"
    saved.write_text("broken", encoding="utf-8")
    manager.store.set(ChatSessionRecord(chat_id=99, session_file=str(saved)))

    async def start_session(_chat_id: int, *, resume: str | None):
        assert resume == str(saved)
        raise PrimeRpcError("incompatible session")

    manager._start_session = start_session  # type: ignore[method-assign]
    with pytest.raises(PrimeRpcError):
        await manager.get(99)
    record = manager.store.get(99)
    assert record is not None
    assert record.session_file == str(saved)




@pytest.mark.asyncio
async def test_failed_worker_resume_is_replaced_with_fresh_session(tmp_path: Path):
    notices: list[tuple[int, str]] = []

    async def recovery_handler(chat_id: int, message: str) -> None:
        notices.append((chat_id, message))

    manager = PrimeSessionManager(make_config(tmp_path), recovery_handler=recovery_handler)
    saved = tmp_path / "old.jsonl"
    saved.write_text("history", encoding="utf-8")
    manager.store.set(ChatSessionRecord(chat_id=99, session_file=str(saved)))
    fresh = FakeSession(str(tmp_path / "fresh.jsonl"))
    attempts: list[str | None] = []

    async def start_session(_chat_id: int, *, resume: str | None):
        attempts.append(resume)
        if resume is not None:
            raise PrimeRpcError(
                f'Session "{resume}" is registered to a failed worker that could not be safely reclaimed'
            )
        return fresh

    manager._start_session = start_session  # type: ignore[method-assign]
    result = await manager.get(99)
    assert result is fresh
    assert attempts == [str(saved), None]
    assert saved.read_text(encoding="utf-8") == "history"
    record = manager.store.get(99)
    assert record is not None
    assert record.session_file == str(tmp_path / "fresh.jsonl")
    assert len(notices) == 1
    assert notices[0][0] == 99
    assert "fresh Prime session" in notices[0][1]


@pytest.mark.asyncio
async def test_dead_in_memory_session_recovers_only_for_exact_failed_worker_state(tmp_path: Path):
    manager = PrimeSessionManager(make_config(tmp_path))
    saved = tmp_path / "old.jsonl"
    saved.write_text("history", encoding="utf-8")
    manager.store.set(ChatSessionRecord(chat_id=99, session_file=str(saved)))
    dead = PrimeRpcSession(make_config(tmp_path), resume_session=str(saved), chat_id=99)

    async def failed_restart() -> None:
        raise PrimeRpcError("failed worker that could not be safely reclaimed")

    dead.start = failed_restart  # type: ignore[method-assign]
    manager.sessions[99] = dead
    fresh = FakeSession(str(tmp_path / "fresh.jsonl"))
    attempts: list[str | None] = []

    async def start_session(_chat_id: int, *, resume: str | None):
        attempts.append(resume)
        assert resume is None
        return fresh

    manager._start_session = start_session  # type: ignore[method-assign]
    result = await manager.get(99)
    assert result is fresh
    assert attempts == [None]
    record = manager.store.get(99)
    assert record is not None
    assert record.session_file == str(tmp_path / "fresh.jsonl")


@pytest.mark.asyncio
async def test_new_recovers_from_unresumable_existing_session(tmp_path: Path):
    manager = PrimeSessionManager(make_config(tmp_path))
    saved = tmp_path / "old.jsonl"
    saved.write_text("broken", encoding="utf-8")
    manager.store.set(ChatSessionRecord(chat_id=99, session_file=str(saved)))
    fresh = FakeSession(str(tmp_path / "fresh.jsonl"))
    attempts: list[str | None] = []

    async def start_session(_chat_id: int, *, resume: str | None):
        attempts.append(resume)
        if resume is not None:
            raise PrimeRpcError("incompatible session")
        return fresh

    manager._start_session = start_session  # type: ignore[method-assign]
    cancelled, state = await manager.new(99)
    assert not cancelled
    assert state["sessionFile"] == str(tmp_path / "fresh.jsonl")
    assert attempts == [str(saved), None]
    record = manager.store.get(99)
    assert record is not None
    assert record.session_file == str(tmp_path / "fresh.jsonl")


def test_poll_offset_never_acknowledges_an_in_flight_update():
    placeholder = object()
    in_flight = {12: placeholder, 15: placeholder}
    assert TelegramPrimeBridge._poll_offset(in_flight, max_seen=20) == 12  # type: ignore[arg-type]
    assert TelegramPrimeBridge._poll_offset({}, max_seen=20) == 21
    assert TelegramPrimeBridge._poll_offset({}, max_seen=None) is None


class FakeTelegram:
    def __init__(self):
        self.sent: list[tuple[int, str]] = []
        self.closed = False

    async def send_message(self, chat_id: int, text: str, **_kwargs: Any) -> None:
        self.sent.append((chat_id, text))

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_autonomous_prime_output_is_forwarded_to_telegram(tmp_path: Path):
    bridge = TelegramPrimeBridge(make_config(tmp_path))
    await bridge.telegram.close()
    fake = FakeTelegram()
    bridge.telegram = fake  # type: ignore[assignment]

    await bridge._on_prime_output(42, PrimeAgentOutcome(text="later result"))
    await bridge._on_prime_output(42, PrimeAgentOutcome(error="provider failed"))
    await bridge._on_session_recovery(42, "fresh session")
    assert fake.sent == [
        (42, "later result"),
        (42, "Prime Agent error: provider failed"),
        (42, "Prime session recovery: fresh session"),
    ]


class AttachmentTelegram(FakeTelegram):
    async def get_file(self, _file_id: str) -> dict[str, str]:
        return {"file_path": "remote/path/file.txt"}

    async def download_file(self, _file_path: str, *, max_bytes: int) -> bytes:
        assert max_bytes == 1024
        return b"hello"


@pytest.mark.asyncio
async def test_document_staging_uses_private_permissions_and_safe_name(tmp_path: Path):
    bridge = TelegramPrimeBridge(make_config(tmp_path))
    await bridge.telegram.close()
    bridge.telegram = AttachmentTelegram()  # type: ignore[assignment]
    msg = IncomingMessage(
        update_id=1,
        chat_id=42,
        user_id=1,
        message_id=7,
        text="see file",
        document={"file_id": "id", "file_name": "../../unsafe name.txt", "file_size": 5},
    )
    _images, note = await bridge._prepare_attachments(msg)
    target = tmp_path / "state" / "inbox" / "42" / "7-unsafe_name.txt"
    assert target.read_bytes() == b"hello"
    assert target.stat().st_mode & 0o777 == 0o600
    assert target.parent.stat().st_mode & 0o777 == 0o700
    assert str(target) in note


@pytest.mark.asyncio
async def test_attachment_cleanup_failure_does_not_stop_bridge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    bridge = TelegramPrimeBridge(make_config(tmp_path))
    await bridge.telegram.close()
    bridge.telegram = FakeTelegram()  # type: ignore[assignment]

    def fail_cleanup(*_args: Any, **_kwargs: Any):
        raise OSError("simulated cleanup failure")

    monkeypatch.setattr("prime_telegram_bridge.bridge.cleanup_attachment_inbox", fail_cleanup)
    await bridge._cleanup_attachments_once()
