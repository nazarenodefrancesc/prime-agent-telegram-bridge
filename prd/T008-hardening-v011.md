# T008 — v0.1.1 reliability/security hardening

**Status:** COMPLETE

## Objective

Close defects found in the second architecture/security audit without expanding the thin-adapter scope.

## Scope

- Treat Prime `agent_end` as an event stream, not only a one-request/one-response completion signal.
- Deliver autonomous later runs from RLM child-to-parent messages and queued Prime work.
- Bind RPC request/waiter ownership to the exact subprocess generation and fail fast on client death.
- Harden `/new`, resume mapping and first-session concurrency.
- Prevent bridge Telegram credentials from being intentionally inherited by Prime.
- Bound Telegram downloads while streaming and preserve exact Telegram output text under UTF-16 limits.
- Private bridge-owned state/attachment permissions.
- Hold Telegram acknowledgement behind in-flight message handling.
- Document the limits of environment scrubbing and the non-transactional Telegram/Prime boundary.

## Acceptance criteria

- A later un-awaited `agent_end` reaches a registered listener exactly once.
- A crashed RPC client fails `ask()` promptly.
- An autonomous error is delivered as an error and never reuses stale assistant text.
- `TELEGRAM_*` and `BRIDGE_*` are absent from the Prime subprocess environment builder; provider credentials remain.
- First concurrent `get(chat_id)` calls create one session.
- Missing `sessionFile` recovers; generic resume errors do not silently destroy the stored mapping.
- `/new` can intentionally recover an unresumable mapped session.
- Telegram chunk concatenation is byte-for-byte equivalent at the Unicode string level and each chunk respects the UTF-16 unit cap.
- Oversized downloads stop during streaming.
- `state.json` and staged documents are `0600`; bridge-owned directories are `0700` where supported.
- Full offline repository gate passes.

## Verification

- `pytest tests/test_prime_rpc.py`
- `pytest tests/test_bridge.py`
- `pytest tests/test_telegram_api.py`
- `./scripts/repo-check.sh`
