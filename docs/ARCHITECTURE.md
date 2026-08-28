# Architecture

## TL;DR

The bridge is intentionally not an agent framework. It is a transport adapter around Prime Agent's official RPC mode.

```text
Telegram long polling
    │
    ▼
TelegramPrimeBridge
    │ authorization + attachment staging
    ▼
PrimeSessionManager
    │ chat_id -> sessionFile
    ▼
PrimeRpcSession
    │ JSONL stdin/stdout
    ▼
prime-agent --mode rpc
    │
    └─ Prime runtime: provider, session, IPython, RLM, subagents, harness
```

## Process model

One live RPC subprocess is created lazily per active Telegram chat. Prime's session JSONL path is recorded after startup and after lifecycle-changing commands. The bridge can be restarted; the next message starts a new RPC client process with `--resume <sessionFile>`.

## Why RPC instead of CLI prompts

`prime-agent -p` would create one-shot request semantics and make state/replies harder to coordinate. RPC provides structured prompt acceptance, events, session state, images, abort, compaction and refinement without parsing TUI text.

## Concurrency

Telegram updates are handled as asyncio tasks. Prime lifecycle and persistence operations are serialized per chat to avoid racing `/new`, prompt completion, and state-file updates. Prime's own recursive subagents remain fully internal to Prime.
