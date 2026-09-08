# REPORT — Prime Agent - Telegram Bridge v0.1.3

## TL;DR

A live Telegram/Prime workload exposed a transport assumption in v0.1.2: the bridge read Prime JSONL stdout with `StreamReader.readline()` while `asyncio.create_subprocess_exec()` retained Python's default ~64 KiB stream limit. A sufficiently large `agent_end` event could therefore terminate the RPC reader even though the bridge service itself stayed alive. Prime could then refuse the persisted session because its resident worker was in the explicit `failed worker that could not be safely reclaimed` state.

v0.1.3 makes JSONL framing large-but-bounded (16 MiB by default), gives over-limit frames a deterministic transport error with no prompt replay, reaps the failed RPC client, and adds a narrow automatic recovery path only for Prime's explicit unreclaimable failed-worker state.

## Implemented evidence

- RPC frame bound/configuration: `src/prime_telegram_bridge/config.py`, `.env.example`, `tests/test_config.py`.
- Large-frame transport handling and subprocess reaping: `src/prime_telegram_bridge/prime_rpc.py`, `tests/test_prime_rpc.py`.
- Failed-worker mapping recovery and Telegram recovery notice: `src/prime_telegram_bridge/bridge.py`, `tests/test_bridge.py`.
- Runtime assumptions/troubleshooting: `docs/PRIME-COMPATIBILITY.md`, `docs/OPERATIONS.md`.

## High-value defects fixed

1. **64 KiB JSONL line ceiling:** Prime stdout now uses `PRIME_RPC_MAX_LINE_BYTES` as the asyncio subprocess stream limit, defaulting to 16 MiB.
2. **Ambiguous over-limit failure:** stdout frame overflow becomes `PrimeRpcFrameTooLarge`; pending work fails promptly and the originating prompt is never automatically replayed.
3. **Subprocess cleanup race:** the RPC child is reaped before the active process reference is cleared, avoiding a concurrent `close()` cancellation that could leave pipe transports/processes open.
4. **Oversized stderr diagnostics:** stderr line overflow is reduced to a bounded marker instead of killing the diagnostic reader.
5. **Repeated unreclaimable-worker failure:** only Prime's explicit `failed worker that could not be safely reclaimed` state can trigger automatic fresh-session replacement.
6. **Recovery safety:** a fresh session must start and persist before the Telegram mapping is replaced; the prior session file remains on disk and the chat receives a recovery notice.
7. **`/new` semantics preserved:** explicit `/new` bypasses automatic failed-worker replacement so it does not create two successive fresh sessions.

## Regression evidence added

- 128 KiB `agent_end` frame: accepted.
- 1 MiB `agent_end` frame: accepted.
- Frame above configured bound: prompt fails promptly as `PrimeRpcFrameTooLarge`.
- Oversized prompt admission counter remains exactly one: no replay.
- Persisted unreclaimable failed-worker mapping: replaced with a fresh persisted session while the old file remains untouched.
- Dead in-memory RPC transport: same narrow recovery path works on the next operation.
- Generic incompatible-session startup error: existing v0.1.2 regression still proves the mapping is preserved.

## Known deferred items

T007 remains deferred:

- durable idempotency across Telegram acknowledgement and Prime prompt admission;
- reconciliation of Prime outputs created while the bridge is offline;
- partial Telegram streaming/message edits;
- stronger/richer transport routing.

The 16 MiB frame limit is deliberately finite. Operators can raise it with `PRIME_RPC_MAX_LINE_BYTES` when their Prime workload legitimately emits larger single-line JSONL events, at the cost of a larger worst-case per-stream buffer.

## Validation snapshot

Validation executed in the patch-build environment for v0.1.3:

- `python3 -m pytest -q`: **PASS — 47 tests**.
- `PYTHONWARNINGS=error python3 -m pytest -q`: **PASS — 47 tests**.
- `python3 -m compileall -q src tests`: **PASS**.
- `git diff --check`: **PASS**.
- Ruff: **NOT RUN** in the patch-build environment because Ruff is not installed; the deployment agent must run it before release.
- real `scripts/smoke-prime.sh` / systemd deployment smoke: **NOT RUN** here; required on the host before tagging.
