# T010 — v0.1.3 large-RPC framing & failed-worker recovery

**Status:** COMPLETE

## Objective

Prevent legitimate large Prime JSONL events from killing the bridge's RPC reader at asyncio's default ~64 KiB line limit, and recover narrowly from Prime's explicit unreclaimable failed-worker state without introducing ambiguous prompt replay or broad destructive session recovery.

## Scope

- Add `PRIME_RPC_MAX_LINE_BYTES`, default 16 MiB, minimum 64 KiB.
- Pass the configured bound to `asyncio.create_subprocess_exec(..., limit=...)`.
- Convert an over-limit stdout JSONL frame into a specific `PrimeRpcFrameTooLarge` transport failure.
- Fail pending RPC requests/agent-end waiters promptly, reap the client process, and never automatically replay the originating prompt.
- Keep oversized stderr diagnostics from crashing the stderr reader.
- Recognize only Prime's `failed worker that could not be safely reclaimed` resume failure for automatic fresh-session replacement.
- Prove and persist the fresh session before replacing the in-memory mapping; leave the old session file untouched.
- Notify the Telegram chat after automatic failed-worker recovery.
- Keep `/new` as explicit general recovery and generic resume/provider/auth failures non-destructive.

## Acceptance criteria

- 128 KiB and 1 MiB `agent_end` JSONL events complete successfully with the default bound.
- A frame larger than the configured bound fails promptly as `PrimeRpcFrameTooLarge`.
- An over-limit prompt is admitted at most once by the bridge; there is no automatic prompt replay.
- The failed subprocess is reaped without ResourceWarning/unclosed-pipe regressions under warning-as-error tests.
- A saved session producing Prime's exact unreclaimable failed-worker error is replaced by a fresh persisted mapping and the old file remains on disk.
- An in-memory session whose client transport died can follow the same narrow recovery path on the next operation.
- Generic resume/provider/auth/incompatible-session errors do not replace the persisted mapping.
- `/new` retains its explicit recovery behavior without first performing the automatic failed-worker replacement.
- Existing Telegram, RLM follow-up, logging, retention and command regressions remain green.

## Verification

- `pytest tests/test_prime_rpc.py`
- `pytest tests/test_bridge.py`
- `pytest tests/test_config.py`
- `PYTHONWARNINGS=error pytest -q`
- `python3 -m compileall -q src tests`
- `./scripts/repo-check.sh`
- real Prime/systemd smoke on the deployment host before tagging
