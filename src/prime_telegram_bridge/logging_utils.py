from __future__ import annotations

import logging
import sys
from typing import TextIO

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class SecretRedactingFormatter(logging.Formatter):
    """Redact configured secrets from the fully-rendered log record.

    Redacting after ``logging.Formatter.format`` also covers %-style arguments
    and exception tracebacks. This is defense-in-depth; callers should still
    avoid putting secrets into log messages in the first place.
    """

    def __init__(self, fmt: str, *, secrets: tuple[str, ...]):
        super().__init__(fmt)
        self._secrets = tuple(secret for secret in secrets if secret)

    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        for secret in self._secrets:
            rendered = rendered.replace(secret, "<redacted-secret>")
        return rendered


def configure_logging(
    level: str,
    *,
    telegram_bot_token: str,
    stream: TextIO | None = None,
) -> None:
    """Configure bridge logging without exposing token-bearing HTTP URLs."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(
        SecretRedactingFormatter(LOG_FORMAT, secrets=(telegram_bot_token,))
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(numeric_level)

    # httpx/httpcore include the full request URL in INFO logs. Telegram bot
    # tokens are part of that URL path, so INFO logging from these libraries is
    # never safe for this process.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
