# T005 — Commands & attachments

**Status:** COMPLETE

## Objective
Expose the smallest useful Prime control surface through Telegram.

## Commands
`/id`, `/help`, `/status`, `/new`, `/stop`, `/steer`, `/followup`, `/compact`, `/refine`.

## Attachments
- Photos -> Prime RPC `images` as base64 + MIME type.
- Documents -> sanitized file under `BRIDGE_STATE_DIR/inbox/<chat_id>/`, path appended to prompt.
- Size constrained by `TELEGRAM_MAX_ATTACHMENT_BYTES`.

## Acceptance criteria
- No user filename can escape the inbox directory.
- Oversized files fail before being sent to Prime.
- Commands do not expose local API keys or bot token.
