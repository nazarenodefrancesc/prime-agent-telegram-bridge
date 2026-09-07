# T003 — Telegram transport & authorization

**Status:** COMPLETE

## Objective

Receive Telegram updates through the Bot API and forward only authorized messages to Prime.

## Contracts

- Long polling keeps acknowledgement behind the oldest in-flight update.
- In-flight/completed-but-unacknowledged updates are deduplicated in memory.
- `/id` is the only unauthenticated command.
- `TELEGRAM_ALLOWED_USER_IDS` gates all Prime access.
- Optional chat allowlist adds a second restriction.
- Telegram output is plain text and split under the platform's UTF-16 unit limit without changing content.
- Unsupported empty update types are ignored.
- Token-bearing Bot API URLs/descriptions are not surfaced in bridge exceptions.

## Acceptance criteria

- Update parser handles text, captions, photos and documents while ignoring unsupported empty message types.
- Unauthorized users cannot reach Prime session creation.
- Long replies preserve exact text across chunks, including astral Unicode.
- Poll offset never acknowledges an older in-flight handler merely because the task was scheduled.
- Malformed/error Telegram API payloads fail with redacted errors.

## Verification

- `pytest tests/test_telegram_api.py`
- `pytest tests/test_bridge.py`
