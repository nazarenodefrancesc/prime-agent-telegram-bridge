from pathlib import Path

from prime_telegram_bridge.state import ChatSessionRecord, StateStore


def test_state_store_round_trip(tmp_path: Path):
    path = tmp_path / "state.json"
    store = StateStore(path)
    store.set(ChatSessionRecord(chat_id=123, session_file="/tmp/s.jsonl", session_id="abc", session_name="tg"))
    record = store.get(123)
    assert record is not None
    assert record.session_file == "/tmp/s.jsonl"
    assert record.session_id == "abc"
    assert path.stat().st_mode & 0o777 == 0o600
