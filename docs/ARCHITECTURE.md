# Architecture

## TL;DR

The bridge is intentionally not an agent framework. It is a transport adapter around Prime Agent's official RPC mode.

```text
Telegram long polling
    │
    ▼
TelegramPrimeBridge
    │ authorization + bounded attachment staging
    ▼
PrimeSessionManager
    │ chat_id -> sessionFile
    ▼
PrimeRpcSession
    │ JSONL stdin/stdout
    ▼
prime-agent --mode rpc
    │
    └─ Prime runtime: provider, daemon session, IPython, RLM, subagents, harness
```

## Process/session model

One RPC client subprocess is created lazily per active Telegram chat. Prime's `sessionFile` path is recorded after startup and lifecycle-changing commands. The v0.1.4 client closes RPC stdin gracefully and can retry an unreclaimable worker, but Prime 0.9.3 still treats RPC as client-owned and may complete the worker on normal shutdown. The bridge can be restarted; the next message launches an RPC client with `--resume <sessionFile>`. Resident-worker continuity requires the unresolved T011 daemon-owned transport work.

Prime Agent has used a shared daemon-owned runtime for interactive, print, JSON and RPC clients since Prime 0.3.2. The bridge deliberately depends only on the public RPC/session surface, not Prime's private daemon protocol. A client restart may reattach to a resident Prime worker, but the bridge does not make a blanket guarantee that volatile kernel state survives every failure/restart scenario.

## Event model

A Telegram prompt is not modeled as the only possible source of a Prime run.

For the initiating prompt:

```text
Telegram message
  -> RPC prompt accepted
  -> agent_start
  -> ... Prime work/RLM ...
  -> agent_end(messages=[...])
  -> synchronous Telegram reply
```

Prime can later start another run, for example when an RLM child sends findings back to its parent:

```text
child completes later
  -> parent receives agent message
  -> parent agent_start
  -> parent agent_end(messages=[...])
  -> bridge listener
  -> Telegram follow-up reply
```

`PrimeRpcSession` therefore treats un-awaited `agent_end` events as transport outputs and forwards their structured assistant text/error to the bridge.

## RPC generation ownership

Every pending RPC request and every synchronous `agent_end` waiter is bound to the exact subprocess object that created it. If an old RPC client dies while a replacement starts, the old reader can fail only its own requests/waiters. This prevents cross-generation recovery races.

Prompts are never automatically retried after ambiguous client failure because Prime may already have admitted the work into its daemon.

## Session initialization

First access to a Telegram chat is single-flight through a dedicated initialization lock. This is separate from the per-chat operation lock, so a caller that serializes prompt/session mutation can still call `get()` without deadlock.

If a persisted concrete `sessionFile` is missing, recovery to a fresh session is unambiguous. Other resume failures are preserved rather than silently deleting state. `/new` is the explicit escape hatch: it can prove a fresh Prime session starts, then replace an unresumable mapping.

## Telegram acknowledgement model

Message handling remains concurrent so `/stop`, `/steer` and later updates can be received during a long Prime run. The polling `offset` is held at the oldest in-flight update. Later already-completed updates are deduplicated in memory until the frontier advances.

This prevents the bridge from acknowledging a long-running update merely because its handler task was scheduled. It still cannot provide exactly-once semantics across the external Telegram API and Prime prompt-admission boundary.

## Why RPC instead of one-shot CLI prompts

`prime-agent -p` would make long-lived state and asynchronous later runs harder to coordinate. RPC provides structured prompt acceptance, events, session state, images, abort, compaction and refinement without parsing terminal rendering.

## Concurrency

- One initialization single-flight per Telegram chat.
- Prompt, `/new`, `/compact` and `/refine` lifecycle work is serialized per chat.
- `/stop`, `/steer` and `/followup` intentionally bypass that lock so they can affect an active run.
- Prime's recursive subagents and parent/child messaging remain internal to Prime.
