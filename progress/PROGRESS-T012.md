# Progress T012 — Transcript recovery fallback

## Status

IN_PROGRESS

## Evidence

- Parser/capsule RED→GREEN slice implemented and tested.
- Bridge fallback now runs after resume/native recovery failure and suppresses
  the capsule's synthetic assistant output.
- Provenance (source file, mode, capsule hash, timestamp) is persisted in the
  bridge state.
- 57 tests pass, including warning-as-error, Ruff, compileall, repo-check, and
  sanitized transcript fixtures.
- Real Telegram recovery test is pending; T011 remains independently open for
  true daemon-owned runtime continuity.
