# Prime Agent compatibility contract

## TL;DR

v0.1.0 targets Prime Agent v0.7.x's documented JSONL RPC interface. Prime-specific behavior is isolated in `src/prime_telegram_bridge/prime_rpc.py`.

## Required Prime capabilities

- `prime-agent --mode rpc`
- `--session-dir`
- `--resume <session path|id>`
- RPC `get_state`
- RPC `prompt` and `streamingBehavior`
- `agent_start` / `agent_end` events
- RPC `get_last_assistant_text`
- RPC `new_session`, `abort`, `compact`, `refine`, `set_session_name`, `set_thinking_level`
- `sessionFile` and `sessionId` in session state

## Deliberately not depended upon

- TUI rendering or footer format.
- A specific model (Kimi, GLM, Claude, OpenAI, etc.).
- A specific provider or billing path.
- Prime internal TypeScript module paths.
- Prime's private daemon wire protocol.

## Upgrade procedure

1. Run `./scripts/repo-check.sh`.
2. Run `./scripts/smoke-prime.sh` against the upgraded Prime binary.
3. Send `/status`, one text prompt, one image, `/compact`, and `/refine` through Telegram.
4. Restart bridge and verify the same chat resumes its prior Prime conversation.
