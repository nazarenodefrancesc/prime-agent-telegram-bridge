# Progress T012 — Transcript recovery fallback

## Status

COMPLETE

## Evidence

- Parser/capsule RED→GREEN slice implemented and tested.
- Bridge fallback now runs after resume/native recovery failure and suppresses
  the capsule's synthetic assistant output.
- Recovery capsules now begin with the same explicit notice sent to Telegram:
  conversation history was recovered into a new session, while runtime-only
  state was not recovered.
- Provenance (source file, mode, capsule hash, timestamp) is persisted in the
  bridge state.
- 57 tests pass, including warning-as-error, Ruff, compileall, repo-check, and
  sanitized transcript fixtures.
- Real Telegram test confirmed conversational context recovery after a fresh
  session was required. T011 remains independently open for true daemon-owned
  runtime continuity.
