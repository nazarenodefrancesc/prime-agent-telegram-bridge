# REPORT — Prime Agent - Telegram Bridge v0.1.2

## TL;DR

The public-repository follow-up audit found one release-blocking security issue: `httpx` logs the full request URL at INFO, and Telegram embeds the bot token in that URL path. v0.1.2 suppresses those dependency INFO logs and adds formatter-level token redaction as defense-in-depth. It also replaces indefinite staged-document retention with configurable 24-hour cleanup that runs at startup and hourly without following symlinks.

The bridge remains a thin Telegram-to-Prime JSONL RPC adapter. Prime/RLM runtime behavior, session persistence and command semantics are intentionally unchanged.

## Implemented evidence

- Logging hardening and secret-redaction coverage: `src/prime_telegram_bridge/logging_utils.py`, `tests/test_logging.py`.
- Existing Telegram API exception redaction remains covered in `tests/test_telegram_api.py`.
- Attachment retention and symlink-safe cleanup: `src/prime_telegram_bridge/state.py`, `tests/test_state.py`.
- Non-fatal cleanup integration and existing bridge regression coverage: `src/prime_telegram_bridge/bridge.py`, `tests/test_bridge.py`.
- Retention configuration/default validation: `src/prime_telegram_bridge/config.py`, `tests/test_config.py`.
- Existing Prime RPC/RLM regressions remain covered by `tests/test_prime_rpc.py`.

## Public-audit defects fixed

1. **Telegram token in dependency INFO logs:** `httpx`/`httpcore` are forced to WARNING or stricter and the root bridge formatter redacts the bot token from fully rendered lines and tracebacks.
2. **Indefinite staged-document retention:** `TELEGRAM_ATTACHMENT_RETENTION_HOURS` defaults to 24 hours; cleanup executes at startup and hourly.
3. **Cleanup path safety:** the inbox root must be a real directory, symlinks are not followed, and empty chat directories are removed only inside the inbox tree.
4. **Cleanup availability:** per-entry and bridge-level cleanup failures are logged and skipped rather than stopping the bridge.

## Known deferred items

T007 remains deferred:

- durable idempotency across Telegram acknowledgement and Prime prompt admission;
- reconciliation of Prime outputs created while the bridge is offline;
- partial Telegram streaming/message edits;
- stronger/richer transport routing.

Environment scrubbing and log redaction are explicitly **not** represented as a same-UID security sandbox.

## Validation snapshot

Validation executed in the delivery environment for v0.1.2:

- `python3 -m pytest -q`: **PASS — 41 tests**.
- `PYTHONWARNINGS=error python3 -m pytest -q`: **PASS — 41 tests**.
- `python3 -m compileall -q src tests`: **PASS**.
- `git diff --check`: **PASS**.
- Ruff: **NOT RUN** because it is not installed in the delivery environment; `repo-check.sh` runs it automatically when dev extras are present.
- `git fsck --full --no-dangling`: **PASS** on the local release repository.
- `scripts/smoke-prime.sh`: **NOT RUN** in this environment because the user's real Prime installation/authentication is not mounted here; prior live Telegram usage confirms the deployed v0.1.1 bridge path but is not counted as a v0.1.2 smoke PASS.
