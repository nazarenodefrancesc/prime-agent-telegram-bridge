from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


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
