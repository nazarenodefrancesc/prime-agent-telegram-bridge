# T003 — Telegram transport & authorization

**Status:** COMPLETE

## Objective
Receive Telegram updates through the Bot API and forward only authorized messages to Prime.

## Contracts
- Long polling with monotonic update offset.
- `/id` is the only unauthenticated command.
- `TELEGRAM_ALLOWED_USER_IDS` gates all Prime access.
- Optional chat allowlist adds a second restriction.
- Telegram output is plain text and split below platform limits.

## Acceptance criteria
- Update parser handles text, captions and photos.
- Unauthorized users cannot reach Prime session creation.
- Long replies are split deterministically.

## Verification
`pytest tests/test_telegram_api.py`
