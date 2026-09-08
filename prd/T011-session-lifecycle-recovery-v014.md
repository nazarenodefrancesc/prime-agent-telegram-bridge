# T011 — Session lifecycle recovery (follow-up to v0.1.4)

## Objective

Preserve the existing Prime session across an ordinary bridge restart by using
a daemon-owned/resident Prime transport. Do not silently discard the
Telegram-to-Prime mapping merely because the first resume attempt reports a
failed worker.

## Acceptance criteria

- The transport does not complete a client-owned session during normal bridge
  shutdown.
- The bridge attaches to a daemon-owned/resident session through a supported
  Prime interface.
- An exact failed-worker state is retried before any fresh session is created.
- A fresh session is created only when retry or same-session reattach fails.
- Generic Prime resume errors remain fail-closed and do not trigger recovery.
- Tests cover ownership, detach/reattach, same-session retry, and fallback.
- Existing offline, static, and real-Prime smoke gates remain green.

## Non-goals

- Reimplementing Prime's daemon supervisor or private wire protocol.
- Guaranteeing volatile IPython/kernel state after a terminal Prime worker
  failure.
- Changing `/new`, which remains the explicit user-requested fresh-session
  operation.

## Current blocker

Prime Agent 0.9.3 selects `client-owned` for `--mode rpc`. Its internal daemon
protocol contains `promote_owned_session`, but the installed CLI does not expose
that operation. The next implementation must either use Prime's public ACP
transport or another documented daemon-owned entry point; it must not speak the
private daemon socket protocol merely to force promotion.
