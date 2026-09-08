# T011 — Session lifecycle recovery (v0.1.4)

## Objective

Preserve the existing Prime session across an ordinary bridge restart whenever
Prime can detach or recover its resident worker. Do not silently discard the
Telegram-to-Prime mapping merely because the first resume attempt reports a
failed worker.

## Acceptance criteria

- `PrimeRpcSession.close()` closes RPC stdin (EOF) and waits up to a bounded
  grace period before using SIGTERM/SIGKILL.
- An exact `failed worker that could not be safely reclaimed` resume failure
  invokes `prime-agent daemon retry <session-id>` (or the persisted selector)
  before any fresh session is created.
- After a successful daemon retry, the bridge resumes the same session file.
- A fresh session is created only when retry or same-session resume fails; the
  old session file remains untouched until the replacement is persisted.
- Generic Prime resume errors remain fail-closed and do not trigger recovery.
- Tests cover graceful EOF, same-session retry, and the existing fallback path.
- Existing offline, static, and real-Prime smoke gates remain green.

## Non-goals

- Reimplementing Prime's daemon supervisor or private wire protocol.
- Guaranteeing volatile IPython/kernel state after a terminal Prime worker
  failure.
- Changing `/new`, which remains the explicit user-requested fresh-session
  operation.
