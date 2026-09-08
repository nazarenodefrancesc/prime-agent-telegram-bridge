# T012 — Transcript recovery fallback

## Objective

Preserve conversational continuity when normal Prime resume and Prime-native
worker recovery fail, without pretending to restore the Prime runtime.

## Acceptance criteria

- Recovery order remains: resume/reattach, native retry, transcript recovery,
  then empty fresh session.
- The old Prime session file is read-only and never rewritten or deleted.
- Parsing is streaming, bounded, content-detected, and tolerant of unknown or
  partially corrupt JSONL records.
- Only allowlisted `user` and `assistant` text is extracted; tool output,
  reasoning, metadata, and actions are excluded.
- Duplicate turns are removed while physical record order is preserved.
- A bounded, clearly labelled historical capsule is injected once into the new
  session; the injection response is not forwarded as a user-facing answer.
- Recovery provenance and capsule fingerprint are persisted separately.
- Fixture, mutation, negative, and real Telegram recovery tests are documented.
- This task does not close T011 or claim runtime/kernel continuity.

## Non-goals

- Replaying tools, bash, HTTP, Git, or RLM jobs.
- Recovering Python variables or live child processes.
- Guaranteeing compatibility with arbitrary future Prime transcript schemas.
