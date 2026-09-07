from pathlib import Path

from prime_telegram_bridge.state import ChatSessionRecord, StateStore, secure_directory


def test_state_store_round_trip(tmp_path: Path):
    path = tmp_path / "state" / "state.json"
    store = StateStore(path)
    store.set(
        ChatSessionRecord(chat_id=123, session_file="/tmp/s.jsonl", session_id="abc", session_name="tg")
    )
    record = store.get(123)
    assert record is not None
    assert record.session_file == "/tmp/s.jsonl"
    assert record.session_id == "abc"
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700


def test_empty_session_file_is_treated_as_no_mapping(tmp_path: Path):
    store = StateStore(tmp_path / "state.json")
    store._atomic_write({"version": 1, "chats": {"123": {"session_file": ""}}})
    assert store.get(123) is None


def test_secure_directory_restricts_existing_directory(tmp_path: Path):
    target = tmp_path / "open"
    target.mkdir(mode=0o755)
    target.chmod(0o755)
    secure_directory(target)
    assert target.stat().st_mode & 0o777 == 0o700
