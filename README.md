# Prime Agent - Telegram Bridge

This repository exists to let you **query Prime Agent from Telegram first**: send a message to a Telegram bot and receive Prime's response without needing to open the local Prime interface. The bridge keeps Telegram as a thin, authorized transport while Prime remains the agent runtime.

A minimal, security-first Telegram transport for **[Prime Agent](https://github.com/PrimeIntellect-ai/prime-agent)**. It does not fork or reimplement Prime: every authorized Telegram chat is mapped to a normal Prime Agent session started through Prime's documented JSONL RPC mode.

## TL;DR

```text
Telegram Bot API
      ↓
prime-telegram-bridge
      ↓ JSONL RPC over stdio
prime-agent --mode rpc
      ↓
Prime daemon/session + IPython + RLM subagents + continual harness
```

The bridge owns only transport, access control, attachment staging, and `chat_id -> Prime session` mapping. Prime remains responsible for model/provider auth, session history, tools, IPython, RLM, compaction, refinement and recursive agents.

v0.1.1 also forwards **later Prime runs** back to Telegram while the bridge is attached. This matters when an RLM child reports back after the initiating parent turn has already ended, or queued Prime work starts a new run.

## Security model

Prime Agent can execute code and edit files with your local user permissions. **Never expose this bot publicly without an allowlist.** The bridge fails closed for agent access: if `TELEGRAM_ALLOWED_USER_IDS` is empty, only `/id` works.

The Prime subprocess environment deliberately drops `TELEGRAM_*` and `BRIDGE_*` variables while retaining Prime/provider credentials. This is **secret minimization, not a sandbox**. If Prime and the bridge run under the same Unix account, do not treat environment scrubbing as a hard isolation boundary. Use a separate user/container/VM if you need one.

## Quick start

1. Install and verify [Prime Agent](https://github.com/PrimeIntellect-ai/prime-agent) separately:

```bash
prime-agent
prime-agent model list
```

2. Create a Telegram bot with BotFather and copy the token.

3. Install the bridge:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
cp .env.example .env
```

4. Export the variables in `.env` (or use your preferred secret manager). At first leave `TELEGRAM_ALLOWED_USER_IDS` empty, start the bridge, then send `/id` to the bot.

```bash
set -a
. ./.env
set +a
prime-telegram-bridge
```

5. Put the returned `user_id` into `TELEGRAM_ALLOWED_USER_IDS` and restart.

## Telegram commands

- `/id` — show Telegram user/chat IDs; available before authorization.
- `/status` — show Prime session/model status.
- `/new` — start a fresh Prime session for this Telegram chat.
- `/stop` — abort current Prime work.
- `/steer <instruction>` — steer a currently running Prime turn.
- `/followup <instruction>` — queue work after the current run.
- `/compact [instructions]` — invoke Prime context compaction.
- `/refine [instructions]` — invoke Prime continual-harness refinement.
- `/help` — help.

Normal text messages are forwarded to Prime. Telegram photos are sent through the RPC image field. Documents are saved under the bridge-owned inbox and Prime receives their local path.

## Persistence and delivery semantics

The mapping is stored atomically in `BRIDGE_STATE_DIR/state.json` with mode `0600`; bridge-owned directories are restricted to `0700` where supported. Prime session files live in `PRIME_SESSION_DIR`. On restart, the next message resumes the mapped Prime `sessionFile` when it is still valid.

Prime has used the same daemon-owned runtime for RPC as other clients since Prime Agent 0.3.2. That means an RPC client restart is **not equivalent to a guaranteed Prime worker reset**, but this bridge also does not promise that volatile IPython variables survive every bridge/client restart. Treat live kernel survival as a real-environment compatibility property and test it on your installed Prime version.

Telegram delivery is intentionally closer to **at-least-once** than at-most-once: the bridge does not advance the polling acknowledgement past the oldest in-flight update. There is still no atomic transaction spanning Telegram acknowledgement and Prime prompt admission. A crash after Prime accepts a prompt but before Telegram acknowledgement can replay that update after restart.

## Validation

```bash
./scripts/repo-check.sh
./scripts/smoke-prime.sh
```

The first command is offline and uses fake RPC processes for contract/regression tests. The second requires the operator's real `prime-agent` installation and authentication.

## Documentation

- `PRD.md` — compact product/task router.
- `prd/Txxx-*.md` — implementation contracts and acceptance criteria.
- `progress/PROGRESS-Txxx.md` — bounded hot state.
- `reports/REPORT-MVP.md` — release evidence.
- `docs/ARCHITECTURE.md` — runtime design.
- `docs/SECURITY.md` — threat model and hardening.
- `docs/OPERATIONS.md` — service setup and troubleshooting.
- `docs/PRIME-COMPATIBILITY.md` — Prime RPC assumptions and compatibility surface.
- `CHANGELOG.md` — release history.
