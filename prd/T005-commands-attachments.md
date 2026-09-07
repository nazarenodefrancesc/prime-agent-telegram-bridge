# T005 — Commands & attachments

**Status:** COMPLETE

## Objective

Expose the smallest useful Prime control surface through Telegram.

## Commands

`/id`, `/help`, `/status`, `/new`, `/stop`, `/steer`, `/followup`, `/compact`, `/refine`.

`/stop`, `/steer` and `/followup` remain callable while a long prompt is active. `/new`, `/compact`, `/refine` and normal lifecycle-changing prompt work are serialized per chat.

## Attachments

- Photos -> Prime RPC `images` as base64 + MIME type.
- Documents -> sanitized file under `BRIDGE_STATE_DIR/inbox/<chat_id>/`, path appended to prompt.
- Download is streamed under `TELEGRAM_MAX_ATTACHMENT_BYTES`; the full body is never accepted beyond the limit.
- Bridge-owned staged files are `0600` and directories `0700` where supported.

## Acceptance criteria

- No user filename can escape the inbox directory.
- Oversized files fail while downloading before being sent to Prime.
- Commands do not expose local API keys or bot token.
- Continual-harness refinement and Prime compaction do not race a concurrent lifecycle mutation for the same chat.
