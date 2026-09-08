from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    """Raised when bridge configuration is invalid."""


VALID_THINKING_LEVELS = frozenset({"off", "minimal", "low", "medium", "high", "xhigh", "max"})


def _parse_int_set(value: str | None, name: str) -> frozenset[int]:
    if not value or not value.strip():
        return frozenset()
    result: set[int] = set()
    for item in value.replace(";", ",").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            result.add(int(item))
        except ValueError as exc:
            raise ConfigError(f"{name} must contain comma-separated integer IDs; got {item!r}") from exc
    return frozenset(result)


def _parse_int(value: str | None, default: int, name: str, minimum: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if parsed < minimum:
        raise ConfigError(f"{name} must be >= {minimum}")
    return parsed


def _parse_thinking(value: str | None) -> str | None:
    level = (value or "").strip().lower()
    if not level:
        return None
    if level not in VALID_THINKING_LEVELS:
        allowed = ", ".join(sorted(VALID_THINKING_LEVELS))
        raise ConfigError(f"PRIME_THINKING must be one of: {allowed}")
    return level


@dataclass(frozen=True, slots=True)
class BridgeConfig:
    telegram_bot_token: str
    telegram_allowed_user_ids: frozenset[int]
    telegram_allowed_chat_ids: frozenset[int]
    telegram_poll_timeout: int
    telegram_max_attachment_bytes: int
    telegram_attachment_retention_hours: int
    prime_agent_bin: str
    prime_workdir: Path
    prime_session_dir: Path
    prime_rpc_max_line_bytes: int
    prime_provider: str | None
    prime_model: str | None
    prime_thinking: str | None
    state_dir: Path
    log_level: str
    transcript_recovery_enabled: bool = True
    transcript_recovery_max_file_bytes: int = 16 * 1024 * 1024
    transcript_recovery_max_line_bytes: int = 1024 * 1024
    transcript_recovery_max_turns: int = 20
    transcript_recovery_max_chars: int = 40_000

    @property
    def bootstrap_only(self) -> bool:
        """True when no Telegram user has been authorized yet."""
        return not self.telegram_allowed_user_ids


def load_config(env: Mapping[str, str] | None = None) -> BridgeConfig:
    # An explicitly empty mapping is a valid test/operator input and must not
    # silently fall back to the host process environment.
    if env is None:
        env = os.environ

    token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise ConfigError("TELEGRAM_BOT_TOKEN is required")

    state_dir = Path(env.get("BRIDGE_STATE_DIR", "~/.prime/telegram")).expanduser().resolve()
    workdir = Path(env.get("PRIME_WORKDIR", os.getcwd())).expanduser().resolve()
    session_dir = Path(env.get("PRIME_SESSION_DIR", str(state_dir / "sessions"))).expanduser().resolve()

    return BridgeConfig(
        telegram_bot_token=token,
        telegram_allowed_user_ids=_parse_int_set(
            env.get("TELEGRAM_ALLOWED_USER_IDS"), "TELEGRAM_ALLOWED_USER_IDS"
        ),
        telegram_allowed_chat_ids=_parse_int_set(
            env.get("TELEGRAM_ALLOWED_CHAT_IDS"), "TELEGRAM_ALLOWED_CHAT_IDS"
        ),
        telegram_poll_timeout=_parse_int(env.get("TELEGRAM_POLL_TIMEOUT"), 30, "TELEGRAM_POLL_TIMEOUT", 1),
        telegram_max_attachment_bytes=_parse_int(
            env.get("TELEGRAM_MAX_ATTACHMENT_BYTES"),
            20 * 1024 * 1024,
            "TELEGRAM_MAX_ATTACHMENT_BYTES",
            1024,
        ),
        telegram_attachment_retention_hours=_parse_int(
            env.get("TELEGRAM_ATTACHMENT_RETENTION_HOURS"),
            24,
            "TELEGRAM_ATTACHMENT_RETENTION_HOURS",
            1,
        ),
        prime_agent_bin=env.get("PRIME_AGENT_BIN", "prime-agent").strip() or "prime-agent",
        prime_workdir=workdir,
        prime_session_dir=session_dir,
        prime_rpc_max_line_bytes=_parse_int(
            env.get("PRIME_RPC_MAX_LINE_BYTES"),
            16 * 1024 * 1024,
            "PRIME_RPC_MAX_LINE_BYTES",
            64 * 1024,
        ),
        prime_provider=(env.get("PRIME_PROVIDER") or "").strip() or None,
        prime_model=(env.get("PRIME_MODEL") or "").strip() or None,
        prime_thinking=_parse_thinking(env.get("PRIME_THINKING")),
        state_dir=state_dir,
        log_level=(env.get("LOG_LEVEL") or "INFO").upper(),
        transcript_recovery_enabled=(
            env.get("TRANSCRIPT_RECOVERY_ENABLED", "true").lower() not in {"0", "false", "no"}
        ),
        transcript_recovery_max_file_bytes=_parse_int(
            env.get("TRANSCRIPT_RECOVERY_MAX_FILE_BYTES"), 16 * 1024 * 1024,
            "TRANSCRIPT_RECOVERY_MAX_FILE_BYTES", 1,
        ),
        transcript_recovery_max_line_bytes=_parse_int(
            env.get("TRANSCRIPT_RECOVERY_MAX_LINE_BYTES"), 1024 * 1024,
            "TRANSCRIPT_RECOVERY_MAX_LINE_BYTES", 1,
        ),
        transcript_recovery_max_turns=_parse_int(
            env.get("TRANSCRIPT_RECOVERY_MAX_TURNS"), 20,
            "TRANSCRIPT_RECOVERY_MAX_TURNS", 1,
        ),
        transcript_recovery_max_chars=_parse_int(
            env.get("TRANSCRIPT_RECOVERY_MAX_CHARS"), 40_000,
            "TRANSCRIPT_RECOVERY_MAX_CHARS", 1,
        ),
    )
