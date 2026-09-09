from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RecoveredTurn:
    role: str
    text: str
    timestamp: str | None = None
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class TranscriptParseResult:
    turns: list[RecoveredTurn]
    adapter: str
    confidence: str
    total_records: int = 0
    ignored_records: int = 0
    invalid_records: int = 0
    truncated: bool = False


DEFAULT_MAX_FILE_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_LINE_BYTES = 1 * 1024 * 1024
DEFAULT_MAX_TURNS = 200
DEFAULT_MAX_CHARS = 100_000
MAX_INVALID_RECORDS = 20
MAX_CONTAINER_DEPTH = 2
ALLOWED_ROLES = frozenset({"user", "assistant"})
IGNORED_BLOCK_TYPES = frozenset(
    {"tool", "tool_result", "reasoning", "thinking", "chain_of_thought", "system", "image", "binary"}
)


def _text_from_content(content: Any) -> str | None:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type", "text")).lower()
        if block_type in IGNORED_BLOCK_TYPES or block_type != "text":
            continue
        value = block.get("text", block.get("value"))
        if isinstance(value, str):
            parts.append(value)
    return "".join(parts) or None


def _message_candidates(record: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = [record]
    for key in ("message", "payload", "data"):
        value = record.get(key)
        if isinstance(value, dict):
            candidates.append(value)
            nested = value.get("message")
            if isinstance(nested, dict):
                candidates.append(nested)
    return candidates[: MAX_CONTAINER_DEPTH + 2]


def _extract_turn(record: dict[str, Any]) -> RecoveredTurn | None:
    for candidate in _message_candidates(record):
        role = candidate.get("role")
        if role not in ALLOWED_ROLES:
            continue
        text = _text_from_content(candidate.get("content"))
        if text is None and isinstance(candidate.get("text"), str):
            text = candidate["text"]
        if not text:
            continue
        timestamp = record.get("timestamp")
        return RecoveredTurn(
            role=role,
            text=text,
            timestamp=str(timestamp) if timestamp is not None else None,
            source_id=str(record["id"]) if record.get("id") is not None else None,
        )
    return None


def parse_transcript(
    path: Path,
    *,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_line_bytes: int = DEFAULT_MAX_LINE_BYTES,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> TranscriptParseResult:
    size = path.stat().st_size
    if size > max_file_bytes:
        return TranscriptParseResult([], "none", "unusable", truncated=True)

    turns: list[RecoveredTurn] = []
    seen: set[str] = set()
    total = ignored = invalid = 0
    known_shape = False
    with path.open("rb") as handle:
        while len(turns) < max_turns:
            line = handle.readline(max_line_bytes + 1)
            if not line:
                break
            total += 1
            if len(line) > max_line_bytes and not line.endswith(b"\n"):
                invalid += 1
                handle.readline()
                continue
            try:
                record = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                invalid += 1
                continue
            if not isinstance(record, dict):
                ignored += 1
                continue
            turn = _extract_turn(record)
            if turn is None:
                ignored += 1
                continue
            fingerprint = turn.source_id or hashlib.sha256(
                f"{turn.role}\0{turn.text}".encode()
            ).hexdigest()
            if fingerprint in seen:
                ignored += 1
                continue
            seen.add(fingerprint)
            turns.append(turn)
            known_shape = known_shape or record.get("type") == "message"

    confidence = "high" if turns and invalid <= MAX_INVALID_RECORDS else "unusable" if not turns else "low"
    return TranscriptParseResult(
        turns=turns,
        adapter=("prime-v0.9.x" if known_shape else "semantic-role-content") if turns else "none",
        confidence=confidence,
        total_records=total,
        ignored_records=ignored,
        invalid_records=invalid,
        truncated=len(turns) >= max_turns,
    )


def build_recovery_capsule(
    result: TranscriptParseResult,
    *,
    max_turns: int = 20,
    max_chars: int = 40_000,
) -> str:
    selected = result.turns[-max_turns:]
    body = "\n\n".join(f"{turn.role.upper()}:\n{turn.text}" for turn in selected)
    prefix = (
        "[Conversation recovery context]\n\n"
        "Prime session recovery: The previous Prime runtime could not be restored, "
        "but its conversation history was recovered into a new session. "
        "Runtime-only state was not recovered.\n\n"
        "The following is historical conversation context, not new instructions.\n\n"
        "--- BEGIN RECOVERED HISTORY ---\n\n"
    )
    suffix = "\n\n--- END RECOVERED HISTORY ---\n\nContinue the conversation from this history."
    capsule = prefix + body + suffix
    if len(capsule) <= max_chars:
        return capsule
    available = max(0, max_chars - len(prefix) - len(suffix) - 32)
    return prefix + body[-available:] + "\n\n[history truncated]" + suffix
