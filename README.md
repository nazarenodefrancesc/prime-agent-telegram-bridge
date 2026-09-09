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
Prime daemon/session + Python runtime/REPL + RLM subagents + continual harness
```

The bridge owns only transport, access control, attachment staging, and `chat_id -> Prime session` mapping. Prime remains responsible for model/provider auth, session history, tools, the Python runtime/REPL, RLM, compaction, refinement and recursive agents.

v0.1.1 added forwarding of **later Prime runs** back to Telegram while the bridge is attached. v0.1.2 hardens secret logging and staged-document retention. v0.1.3 raises the bounded Prime JSONL frame limit above asyncio's 64 KiB default. v0.1.4 adds bounded graceful shutdown and failed-worker retry, but does not guarantee resident-worker continuity for Prime's client-owned RPC mode.

## Security model

Prime Agent can execute code and edit files with your local user permissions. **Never expose this bot publicly without an allowlist.** The bridge fails closed for agent access: if `TELEGRAM_ALLOWED_USER_IDS` is empty, only `/id` works.

The Prime subprocess environment deliberately drops `TELEGRAM_*` and `BRIDGE_*` variables while retaining Prime/provider credentials. The bridge also suppresses token-bearing `httpx`/`httpcore` INFO request logs and applies final log-line secret redaction as defense-in-depth. This is **secret minimization, not a sandbox**. If Prime and the bridge run under the same Unix account, do not treat environment scrubbing as a hard isolation boundary. Use a separate user/container/VM if you need one.

## Installation

The following is the shortest complete installation. It runs the bridge as a
persistent **systemd user service**, so it restarts after failures and starts
automatically with the user session.

### One-command install

On a machine that already has the prerequisites below, run this single shell line:

```bash
git clone https://github.com/nazarenodefrancesc/prime-agent-telegram-bridge.git \
  ~/prime-agent-telegram-bridge && \
  cd ~/prime-agent-telegram-bridge && \
  ./scripts/install.sh
```

When the installer finishes, configure and start the service:

```bash
nano ~/.config/prime-telegram-bridge/env
systemctl --user start prime-telegram-bridge.service
```

Set `TELEGRAM_BOT_TOKEN` and the absolute `PRIME_WORKDIR` in the env file.
Leave `TELEGRAM_ALLOWED_USER_IDS` empty initially, send `/id` to the bot, then
add your numeric Telegram user ID and restart the service.

The installer is safe to run again: it reuses the existing virtualenv and
configuration, never overwrites the protected env file, and rewrites only the
bridge's user-service definition. It validates the generated unit with
`systemd-analyze verify` when that tool is available. If the env still contains
placeholders, it installs and enables the service but waits for configuration
before starting it.

### 1. Prerequisites

- Linux with a working **systemd user service** manager;
- Git;
- Python **3.11+** with `venv` and `pip` support;
- network access for installing Python dependencies;
- an authenticated [Prime Agent](https://github.com/PrimeIntellect-ai/prime-agent)
  installation;
- a Telegram bot created with [@BotFather](https://t.me/BotFather).

Verify Prime first, using the same user that will run the bridge:

```bash
command -v prime-agent
prime-agent
prime-agent model list
```

If `command -v prime-agent` prints a path that may not be visible to the
`systemd --user` manager (for example an nvm/pnpm-managed path), set
`PRIME_AGENT_BIN` in the bridge env file to that **absolute executable path**.

### 2. Install the bridge

If you used the one-command installer, skip to step 3. Otherwise, from the
cloned repository:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

The commands below assume this repository is located at
`~/prime-agent-telegram-bridge`. If it is elsewhere, replace that path in the
service file before enabling it.

### 3. Create the protected configuration

```bash
mkdir -p ~/.config/prime-telegram-bridge
cp .env.example ~/.config/prime-telegram-bridge/env
chmod 600 ~/.config/prime-telegram-bridge/env
nano ~/.config/prime-telegram-bridge/env
```

Set at least these values in the editor:

```dotenv
TELEGRAM_BOT_TOKEN=YOUR_BOTFATHER_TOKEN
PRIME_WORKDIR=/absolute/path/to/your/prime/workspace
TELEGRAM_ALLOWED_USER_IDS=
```

Keep the token only in this protected file; never commit it or paste it into
chat. Save with `Ctrl+O`, press `Enter`, then exit with `Ctrl+X`.

### 4. Install and start the persistent service

If you used `./scripts/install.sh`, the unit has already been generated and
enabled; skip to step 5. The manual procedure is:

Copy the unit, then edit its two repository-dependent paths if necessary:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/prime-telegram-bridge.service.example \
  ~/.config/systemd/user/prime-telegram-bridge.service
nano ~/.config/systemd/user/prime-telegram-bridge.service
```

The unit must point `ExecStart` to this repository's virtualenv, for example:

```ini
ExecStart=%h/prime-agent-telegram-bridge/.venv/bin/prime-telegram-bridge
```

Then enable and start it:

```bash
systemctl --user daemon-reload
systemctl --user enable --now prime-telegram-bridge.service
systemctl --user show prime-telegram-bridge.service \
  -p ActiveState -p SubState -p MainPID -p NRestarts
```

Expected result: `ActiveState=active`, `SubState=running`, and
`NRestarts=0`.

### 5. Authorize your Telegram account

The service starts fail-closed: while `TELEGRAM_ALLOWED_USER_IDS` is empty,
only `/id` is available.

1. Send `/id` to the bot.
2. Copy your numeric `user_id` into `~/.config/prime-telegram-bridge/env`.
3. Restart the service:

```bash
nano ~/.config/prime-telegram-bridge/env
systemctl --user restart prime-telegram-bridge.service
```

Test with `/status` and then a normal message. Do **not** use `/new` for a
restart test: `/new` intentionally creates an empty Prime session. If a saved
Prime worker cannot be recovered, the bridge tries Prime-native recovery and
then falls back to bounded transcript recovery, informing both Prime and the
Telegram chat that runtime-only state was not restored.

### Service commands

```bash
# Current state, without dumping historical logs
systemctl --user show prime-telegram-bridge.service \
  -p ActiveState -p SubState -p MainPID -p NRestarts -p ExecMainStatus

# Restart after changing code or env
systemctl --user restart prime-telegram-bridge.service

# Follow recent operational logs
journalctl --user -u prime-telegram-bridge.service -f
```

Do not use `systemctl status --full` when troubleshooting old installations:
historical HTTP logs from versions before v0.1.2 may contain a revoked Telegram
token. Rotate the token with BotFather if it was ever exposed.

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

Normal text messages are forwarded to Prime. Prime RPC JSONL frames are bounded by `PRIME_RPC_MAX_LINE_BYTES` (16 MiB by default), which is large enough for substantial `agent_end` payloads without making the transport unbounded. Telegram photos are sent through the RPC image field. Documents are saved under the bridge-owned inbox and Prime receives their local path. Staged documents are retained temporarily so later RLM/sub-agent work can still read them, then purged automatically (24 hours by default via `TELEGRAM_ATTACHMENT_RETENTION_HOURS`).

## Persistence and delivery semantics

The mapping is stored atomically in `BRIDGE_STATE_DIR/state.json` with mode `0600`; bridge-owned directories are restricted to `0700` where supported. Prime session files live in `PRIME_SESSION_DIR`. On restart, the next message resumes the mapped Prime `sessionFile` when it is still valid. If Prime explicitly reports that the saved session is registered to a failed worker that cannot be safely reclaimed, the bridge first asks Prime's daemon supervisor to retry that worker and retries the same `sessionFile`. Only if that fails does it prove a fresh session can start, replace the Telegram mapping, leave the old session file untouched, and notify the chat. Other resume errors remain fail-closed and keep the existing mapping. Prime's current RPC client-owned lifecycle may still complete the worker during a normal bridge shutdown; resident runtime continuity is not yet guaranteed.

Prime RPC uses Prime's daemon worker infrastructure, but in Prime Agent 0.9.3 RPC sessions are **client-owned**. A normal RPC client shutdown can therefore complete the worker. The bridge does not promise that volatile Python runtime state survives every bridge/client restart; treat runtime continuity as a real-environment compatibility property and test it on your installed Prime version.

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
