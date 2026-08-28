# Prime Telegram Bridge

A minimal, security-first Telegram transport for **Prime Agent**. It does not fork or reimplement Prime: every authorized Telegram chat is mapped to a normal Prime Agent session started in official JSONL RPC mode.

## TL;DR

```text
Telegram Bot API
      ↓
prime-telegram-bridge
      ↓ JSONL RPC over stdio
prime-agent --mode rpc
      ↓
Prime session + persistent IPython + RLM subagents + continual harness
```

The bridge owns only transport, access control, attachment staging, and `chat_id -> Prime session` mapping. Prime remains responsible for model/provider auth, session history, tools, IPython, RLM, compaction, refinement and recursive agents.

## Security model

Prime Agent can execute code and edit files with your local user permissions. **Never expose this bot publicly without an allowlist.** The bridge therefore fails closed for agent access: if `TELEGRAM_ALLOWED_USER_IDS` is empty, only `/id` works.

## Quick start

1. Install and verify Prime Agent separately:

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

Normal text messages are forwarded to Prime. Telegram photos are sent through the RPC image field. Documents are saved under the bridge state inbox and Prime receives their local path.

## Persistence

The mapping is stored atomically in `BRIDGE_STATE_DIR/state.json` with mode `0600`. Prime session files live in `PRIME_SESSION_DIR`. When the bridge restarts it resumes the mapped Prime session from its JSONL file.

A bridge restart does recreate the RPC process, so volatile in-memory IPython kernel variables do not survive the bridge process restart. Conversation/session history does. Keeping the Prime worker resident independently is deliberately outside v0.1.0.

## Validation

```bash
./scripts/repo-check.sh
./scripts/smoke-prime.sh
```

The first command is offline and uses a fake RPC server for contract tests. The second is an environment smoke test and requires a real `prime-agent` installation.

## Documentation

- `PRD.md` — compact product/task router.
- `prd/Txxx-*.md` — implementation contracts and acceptance criteria.
- `progress/PROGRESS-Txxx.md` — bounded hot state.
- `reports/REPORT-MVP.md` — completion evidence.
- `docs/ARCHITECTURE.md` — runtime design.
- `docs/SECURITY.md` — threat model and hardening.
- `docs/OPERATIONS.md` — service setup and troubleshooting.
- `docs/PRIME-COMPATIBILITY.md` — Prime RPC assumptions and compatibility surface.
