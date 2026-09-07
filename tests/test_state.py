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


def test_cleanup_attachment_inbox_deletes_only_expired_files_and_empty_dirs(tmp_path: Path):
    import os

    from prime_telegram_bridge.state import cleanup_attachment_inbox

    inbox = tmp_path / "inbox"
    chat_old = inbox / "1"
    chat_recent = inbox / "2"
    empty_chat = inbox / "3"
    chat_old.mkdir(parents=True)
    chat_recent.mkdir(parents=True)
    empty_chat.mkdir(parents=True)

    old_file = chat_old / "old.txt"
    recent_file = chat_recent / "recent.txt"
    old_file.write_text("old", encoding="utf-8")
    recent_file.write_text("recent", encoding="utf-8")

    now = 2_000_000.0
    os.utime(old_file, (now - 25 * 3600, now - 25 * 3600))
    os.utime(recent_file, (now - 23 * 3600, now - 23 * 3600))

    deleted, removed_dirs = cleanup_attachment_inbox(inbox, 24, now=now)

    assert deleted == 1
    assert removed_dirs >= 2
    assert not old_file.exists()
    assert not chat_old.exists()
    assert not empty_chat.exists()
    assert recent_file.read_text(encoding="utf-8") == "recent"
    assert chat_recent.exists()


def test_cleanup_attachment_inbox_never_follows_symlinks_outside_inbox(tmp_path: Path):
    import os

    from prime_telegram_bridge.state import cleanup_attachment_inbox

    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "keep.txt"
    outside_file.write_text("keep", encoding="utf-8")
    now = 2_000_000.0
    os.utime(outside_file, (now - 100 * 3600, now - 100 * 3600))

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    link = inbox / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        import pytest

        pytest.skip("symlinks are unavailable on this platform")

    cleanup_attachment_inbox(inbox, 24, now=now)
    assert outside_file.read_text(encoding="utf-8") == "keep"
    assert link.is_symlink()


def test_cleanup_attachment_inbox_refuses_symlink_root(tmp_path: Path):
    import os

    from prime_telegram_bridge.state import cleanup_attachment_inbox

    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "keep.txt"
    outside_file.write_text("keep", encoding="utf-8")
    now = 2_000_000.0
    os.utime(outside_file, (now - 100 * 3600, now - 100 * 3600))

    inbox = tmp_path / "inbox"
    try:
        inbox.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        import pytest

        pytest.skip("symlinks are unavailable on this platform")

    assert cleanup_attachment_inbox(inbox, 24, now=now) == (0, 0)
    assert outside_file.read_text(encoding="utf-8") == "keep"
