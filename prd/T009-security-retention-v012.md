# T009 — v0.1.2 log-secret & attachment-retention hardening

**Status:** COMPLETE

## Objective

Close the public-repository audit findings that could expose the Telegram bot token through dependency logging or retain staged Telegram documents indefinitely, without changing Prime RPC/RLM semantics or adding CI/framework dependencies.

## Scope

- Prevent `httpx`/`httpcore` INFO request logging from exposing token-bearing Telegram Bot API URLs.
- Redact the Telegram bot token from fully rendered bridge log records, including %-style arguments and exception tracebacks.
- Add `TELEGRAM_ATTACHMENT_RETENTION_HOURS` with a 24-hour default and a minimum of 1 hour.
- Clean staged documents at bridge startup and hourly while preserving files newer than the retention window.
- Remove empty inbox subdirectories after expiry cleanup.
- Never follow symlinks during cleanup and refuse a symlinked inbox root.
- Treat cleanup failures as non-fatal operational hygiene errors.
- Preserve the existing Telegram -> Prime, RLM follow-up, session, command and attachment behavior.

## Acceptance criteria

- A normal Telegram HTTP call cannot place `TELEGRAM_BOT_TOKEN` in configured bridge logs.
- HTTP failures and Telegram API error descriptions cannot place the token in bridge logs or surfaced exceptions.
- `httpx` and `httpcore` effective bridge logger levels are WARNING or stricter.
- Formatter-level redaction removes the token from ordinary messages and exception tracebacks.
- Retention defaults to 24 hours and rejects values below 1 hour.
- Files older than retention are deleted; recent files remain.
- Empty chat directories are removed.
- Nested symlinks and a symlinked inbox root never cause cleanup outside the inbox.
- A cleanup exception does not stop the bridge.
- Existing regression suite remains green.

## Verification

- `pytest tests/test_logging.py`
- `pytest tests/test_state.py`
- `pytest tests/test_bridge.py`
- `pytest tests/test_telegram_api.py`
- `./scripts/repo-check.sh`
