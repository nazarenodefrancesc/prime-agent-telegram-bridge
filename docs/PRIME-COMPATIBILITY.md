# Prime Agent compatibility contract

## TL;DR

v0.1.1 targets the documented Prime Agent v0.7.x JSONL RPC surface and also checks the upstream v0.7.0 event/types contract. Prime-specific behavior is isolated in `src/prime_telegram_bridge/prime_rpc.py`.

Prime Agent's changelog records that interactive, print, JSON and RPC clients have used the same daemon-owned runtime since v0.3.2. This bridge uses only the public RPC/session contract and makes no dependency on Prime's private daemon wire protocol. For Prime 0.9.3, RPC is client-owned in the installed lifecycle; transcript recovery is therefore a conversational fallback, not runtime reattachment.

## Required Prime capabilities

- `prime-agent --mode rpc`
- `--session-dir`
- `--resume <session path|id>`
- RPC `get_state`
- RPC `prompt` and `streamingBehavior`
- `agent_start` / `agent_end` events
- structured `agent_end.messages` containing assistant message content/error information
- RPC `get_last_assistant_text` as a compatibility fallback for emitters that omit event messages
- RPC `new_session`, `abort`, `steer`, `follow_up`, `compact`, `refine`, `set_session_name`, `set_thinking_level`
- `new_session.data.cancelled`
- `sessionFile` and `sessionId` in session state

## Event semantics relied upon

Prime's public agent event type defines `agent_end` as the final event of a run and includes that run's `messages`. v0.1.1 uses those messages to distinguish:

- synchronous answer text;
- provider/runtime error or abort;
- later un-awaited runs that must be forwarded independently to Telegram.

This is safer than blindly calling `get_last_assistant_text` after every event, which could resend stale previous text when a later run failed without text.

## Deliberately not depended upon

- TUI rendering or footer format.
- A specific model (Kimi, GLM, Claude, OpenAI, etc.).
- A specific provider or billing path.
- Prime internal TypeScript module paths.
- Prime's private daemon socket/protocol.
- Guaranteed live IPython-kernel survival across every bridge/client restart.
- Full compatibility with arbitrary future Prime transcript formats. The parser is content-detected and designed for forward tolerance with safe degradation.

## Upgrade procedure

1. Read Prime's RPC/changelog changes for the target release.
2. Run `./scripts/repo-check.sh`.
3. Run `./scripts/smoke-prime.sh` against the upgraded Prime binary.
4. Send `/status`, one text prompt, one image, `/compact`, and `/refine` through Telegram.
5. Exercise an RLM child that reports back after the first parent turn and verify the later output reaches Telegram.
6. Restart only the bridge and verify the same chat resumes its prior Prime conversation.
7. If kernel survival matters, explicitly plant a Python variable before restart and verify it afterward; record the result for that Prime version rather than assuming it.


## JSONL frame sizing

Prime emits one JSON object per line, and `agent_end.messages` can make a single event materially larger than a normal text reply. Python asyncio subprocess streams default to a roughly 64 KiB line limit, which is too small for this protocol in real agent workloads. v0.1.3 passes `PRIME_RPC_MAX_LINE_BYTES` (16 MiB by default) as the subprocess stream limit. The bound is configurable but intentionally finite.

If one stdout JSONL frame exceeds the configured bound, the bridge treats the RPC client transport as failed, fails pending waiters promptly, reaps the client process and does not replay the originating prompt because Prime may already have admitted or completed that work in its daemon.

## Failed resident-worker recovery

Prime may refuse a saved-session resume with `failed worker that could not be safely reclaimed`. v0.1.3 treats that exact lifecycle state differently from ordinary resume failures: it proves a fresh session can start and persist before replacing the Telegram mapping, leaves the previous session file on disk, and reports the recovery to the chat. Other startup/resume failures remain non-destructive. T012 adds transcript recovery after this native path fails.

## Transcript recovery fallback

The bridge can extract bounded conversational turns from a failed session's
JSONL transcript and inject them once into a new session. Known Prime message
records are preferred, with a conservative semantic role/content fallback.
Unknown records, tool output, reasoning, and malformed records are ignored.
This preserves conversation context only; it does not restore the original
session identity, worker, IPython variables, or running jobs.
