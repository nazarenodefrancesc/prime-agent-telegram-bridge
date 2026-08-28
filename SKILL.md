# Skill: Prime Telegram Bridge Maintenance

## Intent

Use this skill when implementing, reviewing, or repairing this repository.

## Operating loop

1. Route through `PRD.md` to the active `Txxx` contract.
2. Establish a failing test for any observable behavior change.
3. Preserve the thin-adapter boundary: Telegram transport on one side, Prime RPC on the other.
4. Prefer typed/structured JSON fields over parsing human-facing output.
5. Preserve session identity across restarts through `state.json` + Prime `sessionFile`.
6. Fail closed on authorization, malformed RPC, missing session identity, and oversized attachments.
7. Run `./scripts/repo-check.sh`.
8. Record only bounded progress in `progress/`; move durable evidence to `reports/`.

## Completion gate

A task is COMPLETE only when its acceptance criteria pass and the repository gate is green. If a real Prime installation is unavailable, the offline RPC contract tests may pass while `scripts/smoke-prime.sh` remains explicitly NOT RUN; that limitation must be reported, never silently converted to PASS.
