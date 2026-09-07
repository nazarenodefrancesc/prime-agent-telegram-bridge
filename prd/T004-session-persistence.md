# T004 — Chat/session persistence

**Status:** COMPLETE

## Objective

Preserve `Telegram chat_id -> Prime sessionFile` across bridge restarts without silently destroying valid state on unrelated startup failures.

## Data contract

`BRIDGE_STATE_DIR/state.json`, schema version 1, file mode `0600`; bridge-owned parent directories are `0700` where supported.

## Acceptance criteria

- State writes are atomic.
- Existing valid chat records resume Prime with `--resume`.
- Missing concrete `sessionFile` mappings recover to a fresh session.
- Generic resume failures preserve the old mapping rather than deleting it.
- `/new` may explicitly recover an unresumable mapped session, but only after a fresh Prime session has started successfully.
- New sessions update both persisted mapping and in-memory resume target.
- First concurrent access for one chat creates one session.
- State contains no provider credentials or Telegram bot token.

## Verification

- `pytest tests/test_state.py`
- `pytest tests/test_bridge.py`
