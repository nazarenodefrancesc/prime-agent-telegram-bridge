# PRD — Prime Telegram Bridge v0.1.0

## TL;DR

Deliver a small, secure Telegram adapter that maps each authorized Telegram chat to a persistent Prime Agent session using Prime's documented JSONL RPC mode. The bridge must not reproduce Prime internals.

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
| T007 | DEFERRED | Resident-daemon transport & richer streaming | `prd/T007-future-runtime.md` | `progress/PROGRESS-T007.md` |

## Release acceptance

- Text round-trip works through Prime RPC.
- Prime sessions are resumed after bridge restart from persisted `sessionFile` mapping.
- Empty allowlist permits `/id` only; all agent operations are denied.
- Photos can be passed as RPC images; documents are staged locally with safe filenames.
- `/status`, `/new`, `/stop`, `/compact`, `/refine`, `/help`, `/id` are implemented.
- Offline repository gate passes without requiring network or a real Prime installation.
- Real Prime compatibility is isolated behind an explicit smoke test.
