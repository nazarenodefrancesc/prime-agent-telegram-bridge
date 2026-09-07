# REPORT — Prime Telegram Bridge v0.1.1

## TL;DR

The second-pass audit found substantive correctness and security issues in v0.1.0, especially around asynchronous RLM follow-up runs, subprocess failure/restart ownership, Telegram token leakage in error paths, attachment buffering, session recovery and update acknowledgement. v0.1.1 fixes those issues while keeping the architecture a thin Telegram-to-Prime RPC adapter.

## Implemented evidence

- Configuration/bootstrap validation including explicit-empty mapping and `PRIME_THINKING`: `tests/test_config.py`.
- Atomic/private chat/session mapping and directory permissions: `tests/test_state.py`.
- Telegram parsing, exact UTF-16-safe chunking, token-redacted API failures and bounded downloads: `tests/test_telegram_api.py`.
- Prime RPC startup/prompt/new-session/crash/autonomous-RLM/error/env-scrub contracts: `tests/test_prime_rpc.py` + fake subprocesses.
- Session-manager single-flight/recovery, output forwarding, polling frontier and staged-file permissions: `tests/test_bridge.py`.
- Offline quality gate: `scripts/repo-check.sh`.
- Real Prime environment gate: `scripts/smoke-prime.sh`.

## High-value defects fixed

1. **Lost RLM follow-up output:** v0.1.0 returned the first awaited `agent_end` only. A child could later message the parent, trigger a new parent run, and that answer would remain inside Prime. v0.1.1 forwards un-awaited later runs.
2. **Hung ask on RPC death:** prompt waiters now fail when their owning subprocess stdout closes.
3. **Restart race:** requests/waiters are generation-bound so an old reader cannot fail a replacement client's work.
4. **Stale resume after `/new`:** the session's resume target is updated to the new `sessionFile`; Prime cancellation is respected.
5. **First-session race:** concurrent first messages use one initialization flight.
6. **Unsafe automatic state destruction:** missing files recover automatically, while generic resume errors preserve the mapping; `/new` is the explicit recovery path.
7. **Telegram token exposure:** Bot API errors no longer surface token-bearing request URLs; descriptions are redacted; Prime does not intentionally inherit Telegram/bridge env variables.
8. **Attachment memory bound:** downloads are streamed under the configured byte cap.
9. **Telegram text mutation:** chunking no longer strips/reinserts whitespace and counts astral Unicode correctly under the platform's UTF-16 units.
10. **Premature update acknowledgement:** poll offset stays behind the oldest in-flight Telegram update.

## Known deferred items

T007 remains deferred:

- durable idempotency across Telegram acknowledgement and Prime prompt admission;
- reconciliation of Prime outputs created while the bridge is offline;
- partial Telegram streaming/message edits;
- stronger/richer transport routing.

Environment scrubbing is explicitly **not** represented as a same-UID security sandbox.

## Validation snapshot

Validation executed in the delivery environment for v0.1.1:

- `python3 -m pytest -q`: **PASS — 32 tests**.
- `PYTHONWARNINGS=error python3 -m pytest -q`: **PASS — 32 tests**, after pinning the pytest-asyncio fixture loop scope.
- `python3 -m compileall -q src tests`: **PASS**.
- source/test line-length audit against configured 110 columns: **PASS**.
- `git diff --check`: **PASS** before commit.
- Ruff: **NOT RUN** because it is not installed in the delivery environment and network access is disabled; an attempted install could not reach the package index. `repo-check.sh` runs Ruff automatically when dev extras are present.
- `scripts/smoke-prime.sh`: **NOT RUN** because the user's real Prime installation/authentication is not mounted in this environment. This remains an explicit operator gate, never counted as PASS.
- Final `git fsck`, clean-tree, tag and packaged-repository checks are recorded by the release commit/package validation.
