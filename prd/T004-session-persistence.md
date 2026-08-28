# T004 — Chat/session persistence

**Status:** COMPLETE

## Objective
Preserve `Telegram chat_id -> Prime sessionFile` across bridge restarts.

## Data contract
`BRIDGE_STATE_DIR/state.json`, schema version 1, mode 0600.

## Acceptance criteria
- State writes are atomic.
- Existing chat records resume Prime with `--resume`.
- New sessions update the mapping.
- State contains no provider credentials or Telegram bot token.

## Verification
`pytest tests/test_state.py`
