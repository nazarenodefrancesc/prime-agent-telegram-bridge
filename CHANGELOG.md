# Changelog

## 0.1.2 — 2026-09-07

Security/data-retention hardening after the repository was made public.

### Fixed

- Prevent Telegram bot tokens from leaking through `httpx`/`httpcore` INFO request URL logs.
- Apply formatter-level Telegram token redaction to fully rendered bridge log lines and exception tracebacks as defense-in-depth.
- Add `TELEGRAM_ATTACHMENT_RETENTION_HOURS` (default 24 hours, minimum 1) and purge expired staged Telegram documents at startup and hourly.
- Remove empty inbox directories after retention cleanup.
- Refuse a symlinked inbox root and never follow nested symlinks during cleanup, preventing intentional traversal outside the bridge inbox.
- Keep attachment-cleanup failures non-fatal so retention hygiene cannot take the bridge control plane down.

### Unchanged

- No GitHub Actions/CI added.
- Prime RPC, RLM follow-up delivery, session persistence and Telegram command semantics are unchanged.

## 0.1.1 — 2026-09-07

Hardening release after a second architecture/security audit.

### Fixed

- Forward later Prime `agent_end` runs to Telegram when they are not the synchronous completion of the initiating message. This covers RLM child-to-parent follow-up runs and queued Prime work.
- Fail prompt waiters immediately when the RPC client process exits instead of leaving them blocked until the long prompt timeout.
- Scope pending requests and completion waiters to the exact subprocess generation so an old reader cannot poison a restarted client.
- Update the resume target after `/new`; respect Prime's `new_session.cancelled` response.
- Single-flight first session creation per Telegram chat.
- Recover a missing persisted `sessionFile`; `/new` can also recover an unresumable mapped session without deleting the mapping until a fresh Prime session is proven usable.
- Serialize `/compact` and `/refine` with lifecycle-changing prompt work.
- Extract final text/errors from Prime's structured `agent_end.messages`; autonomous error runs never fall back to stale prior text.
- Preserve Telegram message text exactly when chunking, including whitespace and astral Unicode, while respecting Telegram's UTF-16 limit.
- Ignore unsupported empty Telegram message types instead of accidentally prompting Prime.
- Redact the bot token from Telegram API error paths/descriptions and validate malformed API payloads.
- Stream Telegram downloads under a hard byte bound before buffering the complete attachment.
- Restrict bridge-owned state/inbox directories to `0700` and files to `0600` where supported.
- Remove `TELEGRAM_*` and `BRIDGE_*` variables from the Prime subprocess environment while preserving Prime/provider credentials.
- Validate `PRIME_THINKING` and honor an explicitly empty configuration mapping.
- Keep long-poll acknowledgements behind the oldest in-flight update so a long Prime run does not silently acknowledge itself before bridge handling completes.

### Known limitations

- The Telegram-to-Prime delivery boundary is not exactly-once. If Prime accepts a prompt and the bridge crashes before the Telegram update is safely acknowledged, that update can be replayed after restart.
- Prime has used a daemon-owned runtime for RPC since Prime Agent 0.3.2, but this bridge does not claim that volatile IPython state survives every bridge/client restart. Verify that behavior against the installed Prime version before relying on it.
- Outputs produced entirely while the bridge is offline are not yet reconciled back to Telegram after restart.

## 0.1.0

Initial Telegram transport over Prime Agent JSONL RPC.
