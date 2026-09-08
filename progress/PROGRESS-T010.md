# PROGRESS-T010

**Status:** COMPLETE

- Live failure reproduced conceptually from v0.1.2: `StreamReader.readline()` used asyncio's default ~64 KiB line limit for Prime JSONL stdout.
- Added bounded 16 MiB default RPC frame size via `PRIME_RPC_MAX_LINE_BYTES`.
- Added explicit over-limit failure with no automatic prompt replay and deterministic subprocess reaping.
- Added narrow automatic recovery for Prime's `failed worker that could not be safely reclaimed` state only.
- Fresh-session recovery persists before mapping replacement, preserves the old session file and notifies Telegram.
- Added 128 KiB, 1 MiB, over-limit/no-replay, persisted failed-worker and dead in-memory recovery regressions.
- Local suite expanded from 41 to 47 tests; warning-as-error suite passes in the patch-build environment.
