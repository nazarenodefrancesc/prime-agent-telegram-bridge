# T002 — Prime JSONL RPC client

**Status:** COMPLETE

## Objective

Use Prime's documented `--mode rpc` JSONL protocol as the sole integration boundary.

## Interfaces

- Spawn `prime-agent --mode rpc --session-dir <dir> [--resume <session>]`.
- Correlate command responses by RPC `id` and subprocess generation.
- Treat non-response JSON objects as events.
- Detect `agent_start` / `agent_end`.
- Read structured assistant text/error from `agent_end.messages`.
- Use `get_last_assistant_text` only as a compatibility fallback when event messages are absent.
- Surface un-awaited later `agent_end` runs through listeners for RLM/queued work.

## Constraints

- No TUI scraping.
- No automatic prompt retry after ambiguous client failure.
- No assumptions about model provider credentials.
- Prime auth remains owned by Prime Agent.
- Telegram/bridge credentials are not intentionally inherited by the Prime subprocess.

## Acceptance criteria

- Fake RPC subprocesses prove startup, state query, prompt, agent-end and final-text round-trip.
- RPC process failure promptly fails owned requests/waiters.
- Old subprocess readers cannot poison new-generation work.
- Later autonomous runs are delivered exactly once to registered listeners.
- Autonomous errors do not fall back to stale prior assistant text.
- `/compact`, `/refine`, `/abort`, `/steer`, `/follow_up`, new session and status primitives are exposed.

## Verification

`pytest tests/test_prime_rpc.py`
