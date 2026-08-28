# Operations

## TL;DR

Run the bridge as a long-lived user service after Prime Agent itself works from the same Unix account.

## First bootstrap

1. Set only `TELEGRAM_BOT_TOKEN`, `PRIME_WORKDIR`, and optional Prime settings.
2. Start bridge; it logs bootstrap-only mode.
3. Send `/id` to the bot.
4. Put returned `user_id` in `TELEGRAM_ALLOWED_USER_IDS`.
5. Restart bridge and use `/status`.

## systemd user service

Copy `systemd/prime-telegram-bridge.service.example` to:

`~/.config/systemd/user/prime-telegram-bridge.service`

Create a protected env file (example path used by the unit):

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

**Session resumes but Python variables are gone after service restart** — expected in v0.1.0; history persists, volatile IPython process memory does not. See T007.
