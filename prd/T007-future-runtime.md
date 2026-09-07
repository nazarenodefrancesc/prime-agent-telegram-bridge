# T007 — Durable reconciliation & richer transport

**Status:** DEFERRED

## Motivation

Prime Agent has routed RPC through the same daemon-owned runtime as its other clients since Prime 0.3.2. The bridge nevertheless cannot treat every client restart as proof that the live worker/IPython kernel stayed resident, and it currently has no durable reconciliation protocol for outputs produced while Telegram transport is offline.

## Future scope

- Validate and, if useful, explicitly attach/observe resident Prime daemon sessions across bridge restarts.
- Persist a Telegram delivery watermark and reconcile Prime outputs produced while the bridge was offline.
- Add idempotency/deduplication around the Telegram update -> Prime prompt admission ambiguity.
- Stream partial assistant output to Telegram via message edits.
- Optional Telegram topic -> Prime child/root routing.
- Richer concurrent normal-message steering UX, including images.

## Non-goal for v0.1.1

Do not invent a second agent runtime or private Prime daemon protocol. Keep using documented RPC/observation surfaces and validate lifecycle behavior against the installed Prime release.
