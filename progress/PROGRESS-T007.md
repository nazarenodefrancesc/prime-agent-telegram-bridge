# PROGRESS-T007

**Status:** DEFERRED

- v0.1.1 now forwards later autonomous `agent_end` runs while the bridge is attached.
- Still deferred: offline output reconciliation, durable idempotency/deduplication, partial Telegram streaming and richer routing.
- Prime RPC is daemon-owned in current Prime releases; do not assume live kernel survival across every client restart without a real-environment lifecycle test.
