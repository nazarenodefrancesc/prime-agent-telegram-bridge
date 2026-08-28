# Security

## TL;DR

Treat the Telegram bot as a remote shell-adjacent control plane because Prime Agent can execute local code. Authorization is therefore a release-blocking invariant, not a convenience feature.

## Threat model

Attackers may know the bot username, send arbitrary text/files, choose malicious filenames, flood messages, or attempt prompt injection. The bridge assumes the Telegram Bot API transport is authentic when addressed through HTTPS, but it does not trust message content or sender authorization until IDs are checked.

## Controls

- Empty `TELEGRAM_ALLOWED_USER_IDS` => bootstrap-only mode; only `/id` is served.
- Optional chat allowlist can restrict groups/chats in addition to user IDs.
- Secrets come from environment/Prime's own stores and are never written to bridge state.
- Bridge state is mode `0600`.
- Telegram document names are reduced to safe basenames and staged under a fixed inbox root.
- Attachment size is bounded before Prime receives it.
- No user-controlled shell string is built by the bridge.
- Prime model/provider auth stays outside this repository.

## Operator hardening

- Run under a dedicated Unix user if the Prime workspace is sensitive.
- Set `PRIME_WORKDIR` to the smallest directory tree Prime needs.
- Keep the bot in private chat unless group access is intentional.
- Rotate the bot token immediately if it appears in logs, shell history, a commit, or a screenshot.
