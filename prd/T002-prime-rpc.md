# T002 — Prime JSONL RPC client

**Status:** COMPLETE

## Objective
Use Prime's documented `--mode rpc` JSONL protocol as the sole integration boundary.

## Interfaces
- Spawn `prime-agent --mode rpc --session-dir <dir> [--resume <session>]`.
- Correlate command responses by RPC `id`.
- Treat non-response JSON objects as events.
- Detect `agent_start` / `agent_end`.
- Retrieve final text with `get_last_assistant_text`.

## Constraints
- No TUI scraping.
- No assumptions about model provider credentials.
- Prime auth remains owned by Prime Agent.

## Acceptance criteria
- Fake RPC server proves startup, state query, prompt, agent-end and final-text round-trip.
- RPC process failures surface stderr tail.
- `/compact`, `/refine`, `/abort`, new session and status primitives are exposed.

## Verification
`pytest tests/test_prime_rpc.py`
