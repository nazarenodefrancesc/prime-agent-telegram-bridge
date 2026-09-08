# PRD — Prime Agent - Telegram Bridge v0.1.4

## TL;DR

Deliver a small, secure Telegram adapter that maps each authorized Telegram chat to a persistent Prime Agent session using Prime's documented JSONL RPC mode. The bridge must not reproduce Prime internals. v0.1.1 hardened crash/restart behavior and RLM follow-up delivery; v0.1.2 closed token-bearing HTTP log leakage and bounded staged-document retention; v0.1.3 hardens large JSONL RPC framing; v0.1.4 improves graceful client shutdown and retries failed resident workers before falling back to a new session.

## Product contract

**Input:** authorized Telegram messages and attachments.  
**Output:** Prime Agent replies returned to the same Telegram chat.  
**Trust boundary:** Telegram is untrusted remote input; Prime has local user-level execution power.  
**Primary invariant:** no unauthorized Telegram user may invoke Prime Agent.

## Task router

| ID | Status | Task | Contract | Progress |
|---|---|---|---|---|
| T001 | COMPLETE | Repository foundation & security baseline | `prd/T001-foundation.md` | `progress/PROGRESS-T001.md` |
| T002 | COMPLETE | Prime JSONL RPC client | `prd/T002-prime-rpc.md` | `progress/PROGRESS-T002.md` |
| T003 | COMPLETE | Telegram transport & authorization | `prd/T003-telegram-transport.md` | `progress/PROGRESS-T003.md` |
| T004 | COMPLETE | Chat/session persistence | `prd/T004-session-persistence.md` | `progress/PROGRESS-T004.md` |
| T005 | COMPLETE | Commands & attachments | `prd/T005-commands-attachments.md` | `progress/PROGRESS-T005.md` |
| T006 | COMPLETE | Verification & operations | `prd/T006-verification-operations.md` | `progress/PROGRESS-T006.md` |
| T007 | DEFERRED | Durable reconciliation & richer transport | `prd/T007-future-runtime.md` | `progress/PROGRESS-T007.md` |
| T008 | COMPLETE | v0.1.1 reliability/security hardening | `prd/T008-hardening-v011.md` | `progress/PROGRESS-T008.md` |
| T009 | COMPLETE | v0.1.2 log-secret & attachment-retention hardening | `prd/T009-security-retention-v012.md` | `progress/PROGRESS-T009.md` |
| T010 | COMPLETE | v0.1.3 large-RPC framing & failed-worker recovery | `prd/T010-rpc-framing-recovery-v013.md` | `progress/PROGRESS-T010.md` |
| T011 | IN_PROGRESS | v0.1.4 session lifecycle recovery | `prd/T011-session-lifecycle-recovery-v014.md` | `progress/PROGRESS-T011.md` |

## Release acceptance

- Text round-trip works through Prime RPC.
- Later Prime/RLM parent runs that occur after the initiating run are surfaced to Telegram while the bridge is online.
- Prime sessions are resumed after bridge restart from persisted `sessionFile` mapping when the saved file remains valid.
- Missing mappings recover safely; `/new` can recover an unresumable session without destroying the old mapping before a fresh Prime session starts.
- Empty allowlist permits `/id` only; all agent operations are denied.
- Photos can be passed as RPC images; documents are staged locally with safe filenames and private permissions.
- Attachment downloads are bounded during streaming, not only after buffering.
- `/status`, `/new`, `/stop`, `/steer`, `/followup`, `/compact`, `/refine`, `/help`, `/id` are implemented.
- Telegram bot credentials are not intentionally inherited by the Prime subprocess.
- Token-bearing `httpx`/`httpcore` INFO request logs are suppressed and bridge-formatted logs redact the Telegram token.
- Staged Telegram documents expire after a configurable retention window (24 hours by default); cleanup runs at startup and periodically without following symlinks.
- Prime JSONL events larger than asyncio's default 64 KiB are accepted up to a configurable 16 MiB default bound; over-limit frames fail promptly and are never automatically replayed.
- Prime's explicit unreclaimable failed-worker state is retried through the daemon supervisor before a proven fresh-session replacement; the old mapping is preserved until replacement succeeds. This does not make client-owned RPC workers resident.
- Offline repository gate passes without requiring network or a real Prime installation.
- Real Prime compatibility remains an explicit operator smoke gate.

## Explicit non-guarantees

- No exactly-once transaction spans Telegram update acknowledgement and Prime prompt admission.
- No guarantee that volatile IPython variables or a client-owned Prime worker survive every bridge/client restart. v0.1.4's graceful shutdown/retry work does not provide resident-worker continuity; that requires a supported daemon-owned transport.
- No offline-output reconciliation yet if Prime completes work while the bridge is not attached.
