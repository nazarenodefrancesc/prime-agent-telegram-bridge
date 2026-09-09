# T011 — Prime ownership/lifecycle research

## Reference

Installed Prime Agent version: `0.9.3`.

The bridge launches `prime-agent --mode rpc`. Prime's startup code routes RPC
through the daemon client, but `isClientOwnedDaemonSession()` returns true for
every app mode except ACP. Therefore the bridge's RPC session is client-owned.

## Observed lifecycle

- RPC startup attaches/creates a client-owned worker.
- `DaemonAgentConnection.dispose()` sends `complete_owned_session` for an owned
  session and `detach` only for a non-owned session.
- The daemon supervisor supports `promote_owned_session`, which removes the
  owner and makes the worker resident.
- Prime's installed `daemon` CLI exposes `retry`, `restart`, and other commands,
  but does not expose `promote_owned_session`.
- The real bridge restart after v0.1.4 left the daemon with zero sessions and
  the bridge created a fresh session, confirming that graceful EOF is not a
  resident detach for this RPC ownership mode.

## Conclusion

The v0.1.4 EOF/retry change cannot satisfy runtime continuity on its own. A
private daemon-socket call to promotion would violate the bridge's public-API
boundary and would be brittle across Prime releases. The viable next paths are:

1. adapt the bridge to Prime's public ACP transport, if it provides the needed
   session/event/image/control surface; or
2. use a future documented Prime option that creates/attaches a daemon-owned
   session.

Until one of these paths is implemented and tested with Prime 0.9.3, T011 must
remain `IN_PROGRESS` and the bridge must not claim worker/runtime continuity.

## T012 outcome

The separate transcript fallback was implemented and validated through the
Telegram bot: a new Prime session recovered the prior conversational context.
This confirms transcript continuity only; it does not change the T011 runtime
ownership conclusion.
