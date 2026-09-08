# Progress T011 — Session lifecycle recovery

## Status

COMPLETE

## Scope

v0.1.4 graceful RPC shutdown and same-session failed-worker recovery.

## Evidence

- RED tests added for EOF-before-escalation and retry-before-fresh behavior.
- Graceful EOF shutdown and bounded signal fallback implemented.
- Failed-worker recovery retries Prime's daemon supervisor with the persisted
  session selector before same-session resume and fresh-session fallback.
- 53 tests pass, including warning-as-error, Ruff, compileall, repo-check, and
  the real Prime CLI/model-catalog smoke test.
- Service v0.1.4 installed and restarted successfully; `active/running`, zero
  automatic restarts, exit status 0, dedicated cgroup verified.
