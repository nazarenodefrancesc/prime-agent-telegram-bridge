# T001 — Repository foundation & security baseline

**Status:** COMPLETE

## Objective
Create an installable Python 3.11+ package with an explicit remote-to-local threat boundary.

## Scope
- Package metadata and CLI entrypoint.
- Environment-driven configuration.
- Mandatory Telegram bot token.
- Fail-closed Telegram user allowlist.
- Documentation and repository workflow files.

## Acceptance criteria
- Missing bot token fails before runtime.
- Empty user allowlist enters bootstrap-only mode.
- Secrets are excluded from git by default.
- `AGENTS.md`, `SKILL.md`, `PRD.md`, task and progress structure exist.

## Verification
`pytest tests/test_config.py`
