# Operations

## TL;DR

Run the bridge as a long-lived service only after Prime Agent itself works from the same execution environment. Start with bootstrap-only Telegram access, then explicitly allow your numeric user ID.

## First bootstrap

1. Set only `TELEGRAM_BOT_TOKEN`, `PRIME_WORKDIR`, and optional Prime settings.
2. Start bridge; it logs bootstrap-only mode.
3. Send `/id` to the bot.
4. Put returned `user_id` in `TELEGRAM_ALLOWED_USER_IDS`.
5. Optionally set `TELEGRAM_ATTACHMENT_RETENTION_HOURS` (default `24`).
6. Optionally set `PRIME_RPC_MAX_LINE_BYTES` (default `16777216`, 16 MiB).
7. Restart bridge and use `/status`.

## systemd user service

Copy `systemd/prime-telegram-bridge.service.example` to:

`~/.config/systemd/user/prime-telegram-bridge.service`

Create a protected env file:

```bash
mkdir -p ~/.config/prime-telegram-bridge
cp .env.example ~/.config/prime-telegram-bridge/env
chmod 600 ~/.config/prime-telegram-bridge/env
```

Then:

```bash
systemctl --user daemon-reload
systemctl --user enable --now prime-telegram-bridge
journalctl --user -u prime-telegram-bridge -f
```

## Common failures

**Prime executable not found** — set `PRIME_AGENT_BIN` to the absolute binary path.

**Prime RPC startup fails** — run `prime-agent --mode rpc` manually and verify the provider is authenticated. The bridge intentionally does not implement provider login.

**Bot responds Access denied** — run `/id`, correct `TELEGRAM_ALLOWED_USER_IDS`, restart.

**Saved Prime session file disappeared** — the next access starts a fresh session. The missing mapping is not treated as resumable.

**Saved Prime session exists but is corrupt/incompatible** — normal access surfaces the error and keeps the mapping. Use `/new` to explicitly abandon it; the bridge proves a fresh session can start before replacing the stored mapping.

**A later RLM result arrives after the first reply** — expected. v0.1.1 forwards later un-awaited Prime `agent_end` results to Telegram while the bridge is attached.

**Bridge restarted and Python variables appear missing** — do not assume either outcome. Prime RPC is daemon-owned in current Prime releases, but live worker/kernel survival depends on the concrete lifecycle/failure. Conversation/session JSONL persistence is the supported bridge contract; validate volatile kernel behavior with a real smoke test before relying on it.

**Same Telegram message appears twice after a crash** — possible at the Telegram/Prime admission boundary. See T007 for future durable idempotency/reconciliation work.

**Prime RPC reports `Separator is not found` / `chunk exceed the limit` / `LimitOverrunError`** — v0.1.3 raises the subprocess JSONL stream bound to 16 MiB by default via `PRIME_RPC_MAX_LINE_BYTES`. Frames above the configured bound fail promptly and the originating prompt is not retried automatically.

**Prime reports `failed worker that could not be safely reclaimed`** — v0.1.4 first invokes Prime's daemon-supervisor retry for the persisted session selector and retries the same session file. Only if both attempts fail does the bridge start and persist a fresh session, leave the old session file untouched, and notify Telegram. Generic provider/auth/incompatible-session errors still preserve the old mapping. `/new` remains the explicit recovery command for all other cases.

**Bridge restart loses a resident worker** — v0.1.4 closes RPC stdin gracefully, but Prime 0.9.3's RPC path is client-owned and may complete the worker on normal shutdown. The daemon-owned transport follow-up is tracked in T011; volatile IPython state must not yet be relied upon across bridge restarts.

**Staged Telegram documents are accumulating** — v0.1.2 cleans `BRIDGE_STATE_DIR/inbox` at startup and hourly, deleting files older than `TELEGRAM_ATTACHMENT_RETENTION_HOURS` and empty chat directories. Symlinks are never followed.

**Bot token appears in old journal logs** — rotate the token with BotFather, then update the protected env file. v0.1.2 suppresses token-bearing `httpx`/`httpcore` INFO logs and redacts the token from bridge-formatted log output, but old logs remain sensitive until rotated/expired.

## Release verification

```bash
./scripts/repo-check.sh
./scripts/smoke-prime.sh
```

`repo-check.sh` is offline. `smoke-prime.sh` is the operator-owned compatibility gate against the actually installed Prime binary/authentication.
