from __future__ import annotations

import json
import logging
import os
import stat
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def secure_directory(path: Path) -> None:
    """Create a bridge-owned directory and restrict it to the current user."""
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        # Some non-POSIX filesystems may not support chmod. Creation still
        # succeeds; deployment docs require an OS-level permission review.
        pass


@dataclass(slots=True)
class ChatSessionRecord:
    chat_id: int
    session_file: str
    session_id: str | None = None
    session_name: str | None = None


class StateStore:
    """Tiny atomic JSON store for Telegram chat -> Prime session mapping."""

    def __init__(self, path: Path):
        self.path = path
        secure_directory(self.path.parent)

    def _load_raw(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "chats": {}}
        with self.path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("chats"), dict):
            raise ValueError(f"Unsupported or malformed bridge state: {self.path}")
        return data

    def get(self, chat_id: int) -> ChatSessionRecord | None:
        data = self._load_raw()
        raw = data["chats"].get(str(chat_id))
        if not isinstance(raw, dict):
            return None
        session_file = str(raw.get("session_file", ""))
        if not session_file:
            return None
        return ChatSessionRecord(
            chat_id=chat_id,
            session_file=session_file,
            session_id=raw.get("session_id"),
            session_name=raw.get("session_name"),
        )

    def set(self, record: ChatSessionRecord) -> None:
        data = self._load_raw()
        data["chats"][str(record.chat_id)] = asdict(record)
        self._atomic_write(data)

    def delete(self, chat_id: int) -> None:
        data = self._load_raw()
        data["chats"].pop(str(chat_id), None)
        self._atomic_write(data)

    def _atomic_write(self, data: dict[str, Any]) -> None:
        secure_directory(self.path.parent)
        fd, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, self.path)
            os.chmod(self.path, 0o600)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)


def cleanup_attachment_inbox(
    inbox_root: Path,
    retention_hours: int,
    *,
    now: float | None = None,
) -> tuple[int, int]:
    """Delete expired staged attachments without following symlinks.

    Returns ``(deleted_files, removed_directories)``. Per-entry filesystem
    failures are logged and skipped so cleanup cannot take down the bridge.
    """
    if retention_hours < 1:
        raise ValueError("retention_hours must be >= 1")
    try:
        root_stat = os.lstat(inbox_root)
    except FileNotFoundError:
        return 0, 0
    except OSError as exc:
        logger.warning("Attachment cleanup could not inspect %s: %s", inbox_root, exc)
        return 0, 0
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        logger.warning("Attachment cleanup refused unsafe inbox root: %s", inbox_root)
        return 0, 0

    cutoff = (time.time() if now is None else now) - (retention_hours * 3600)
    deleted_files = 0
    removed_directories = 0

    def visit(directory: Path, *, is_root: bool = False) -> None:
        nonlocal deleted_files, removed_directories
        try:
            with os.scandir(directory) as entries:
                snapshot = list(entries)
        except OSError as exc:
            logger.warning("Attachment cleanup could not scan %s: %s", directory, exc)
            return

        for entry in snapshot:
            path = Path(entry.path)
            try:
                if entry.is_symlink():
                    # Never follow or delete symlinks: a same-UID process could
                    # otherwise redirect cleanup outside the bridge inbox.
                    continue
                if entry.is_dir(follow_symlinks=False):
                    visit(path)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                if entry.stat(follow_symlinks=False).st_mtime < cutoff:
                    os.unlink(path)
                    deleted_files += 1
            except OSError as exc:
                logger.warning("Attachment cleanup skipped %s: %s", path, exc)

        if is_root:
            return
        try:
            directory.rmdir()
            removed_directories += 1
        except OSError:
            # Non-empty, already removed, or not removable: all are harmless.
            pass

    visit(inbox_root, is_root=True)
    return deleted_files, removed_directories
