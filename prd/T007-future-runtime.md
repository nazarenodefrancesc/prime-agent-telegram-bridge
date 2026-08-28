# T007 — Resident-daemon transport & richer streaming

**Status:** DEFERRED

## Motivation
v0.1.0 resumes persisted Prime sessions after bridge restart, but the RPC subprocess itself is bridge-owned. Its volatile IPython kernel therefore resets if the bridge process restarts.

## Future scope
- Attach to a resident Prime daemon session independent of bridge lifetime.
- Stream partial assistant output to Telegram via message edits.
- Explicit concurrent steering/follow-up UX instead of per-chat lifecycle serialization.
- Optional Telegram topic -> Prime child/root routing.

## Non-goal for v0.1.0
Do not add this complexity before the thin RPC adapter is proven in real use.
