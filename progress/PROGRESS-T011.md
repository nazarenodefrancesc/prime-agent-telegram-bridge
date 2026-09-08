# Progress T011 — Session lifecycle recovery

## Status

IN_PROGRESS

## Scope

v0.1.4 graceful RPC shutdown and same-session failed-worker recovery.

## Evidence

- RED tests added for EOF-before-escalation and retry-before-fresh behavior.
- v0.1.4 graceful EOF/retry implementation was tested but the real restart test
  showed that Prime's RPC client-owned session is completed on normal shutdown.
- Prime 0.9.3 exposes promotion only in the daemon protocol; no supported CLI
  command currently exposes it.
- The resident/daemon-owned transport decision and implementation remain open.
- Existing v0.1.4 tests and service deployment remain intact, but T011 is not
  certified complete.
