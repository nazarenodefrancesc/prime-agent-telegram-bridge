# Changelog

## Unreleased

### Fixed

- Make the one-command installer collect the Telegram bot token (hidden input)
  and numeric allowlist user ID interactively, aborting when either is missing.
- Default `PRIME_WORKDIR` to the cloned repository when the env still contains
  its placeholder, while preserving an explicitly configured workspace.
- Populate `PRIME_AGENT_BIN` with the detected absolute Prime executable when
  the env still contains its default value.
- Fix the one-command installer systemd unit generation: preserve real absolute paths instead of feeding `EnvironmentFile=`, `WorkingDirectory=`, and `ExecStart=` unit-name escapes from `systemd-escape --path`.
- Add a render-only installer diagnostic hook and validate generated units with `systemd-analyze verify` when available.
- Make installer-generated units safe for spaces, `%`, `$`, and other special path characters, and disable ExecStart environment expansion for the executable path.
- Avoid an unnecessary pip self-upgrade during install; improve virtualenv and Prime executable diagnostics.
- Correct README wording for Prime 0.9.3: RPC is daemon-hosted but client-owned, and runtime continuity refers to the Python runtime/REPL rather than IPython.

## 0.1.3 — 2026-09-08

Prime RPC framing and failed-worker recovery hardening after a live Telegram request produced a JSONL event larger than asyncio's default 64 KiB line limit.

### Fixed

- Add `PRIME_RPC_MAX_LINE_BYTES` with a 16 MiB default and a 64 KiB minimum, and pass it to the asyncio subprocess stream limit so large Prime JSONL events are accepted without `LimitOverrunError`/`ValueError`.
- Convert over-limit stdout frames into a specific `PrimeRpcFrameTooLarge` failure, fail pending work promptly, reap the RPC subprocess, and never automatically replay the ambiguous originating prompt.
- Keep oversized stderr diagnostics non-fatal while recording a bounded marker instead of crashing the stderr reader.
- Reap subprocesses before clearing the active process reference, preventing a close/read race from leaving subprocess pipe transports unclosed.
- Automatically replace a persisted session only for Prime's explicit `failed worker that could not be safely reclaimed` state; generic resume/provider/auth failures still preserve the existing mapping.
- Surface a Telegram notice when automatic failed-worker recovery starts a fresh Prime session, while leaving the old session file untouched.
- Keep `/new` as the explicit general-purpose recovery path and avoid double-recovery by disabling automatic failed-worker replacement inside `/new`.

### Unchanged

- No automatic retry of accepted/possibly accepted Prime prompts.
- No exactly-once guarantee across Telegram acknowledgement and Prime prompt admission.
- No GitHub Actions/CI added.

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
- Prime RPC uses Prime's daemon worker infrastructure, but session ownership and runtime continuity depend on the installed Prime version. This bridge does not claim that volatile Python runtime state survives every bridge/client restart.
- Outputs produced entirely while the bridge is offline are not yet reconciled back to Telegram after restart.

## 0.1.0

Initial Telegram transport over Prime Agent JSONL RPC.
