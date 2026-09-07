# Security

## TL;DR

Treat the Telegram bot as a remote shell-adjacent control plane because Prime Agent can execute local code. Authorization is therefore a release-blocking invariant, not a convenience feature.

## Threat model

Attackers may know the bot username, send arbitrary text/files, choose malicious filenames, flood messages, or attempt prompt injection. The bridge assumes the Telegram Bot API transport is authentic when addressed through HTTPS, but it does not trust message content or sender authorization until IDs are checked.

Prime itself runs local tools with the permissions available to its process. The bridge does not claim to sandbox Prime.

## Controls

- Empty `TELEGRAM_ALLOWED_USER_IDS` => bootstrap-only mode; only `/id` is served.
- Optional chat allowlist can restrict groups/chats in addition to user IDs.
- Bridge state never stores Telegram bot tokens or model/provider API keys.
- Prime's subprocess environment intentionally removes `TELEGRAM_*` and `BRIDGE_*` variables while keeping Prime/provider credentials.
- Telegram API exceptions are rewrapped so token-bearing Bot API URLs are not surfaced; Telegram error descriptions are token-redacted.
- Bridge-owned directories are `0700` and state/staged files are `0600` where the filesystem supports Unix modes.
- Telegram document names are reduced to safe basenames and staged under a fixed inbox root.
- Attachment downloads are streamed under `TELEGRAM_MAX_ATTACHMENT_BYTES`; the bridge stops once the bound is exceeded instead of first buffering an arbitrarily large body.
- Unsupported empty Telegram message types are ignored rather than converted into generic prompts.
- No user-controlled shell command string is constructed by the bridge.
- Prime model/provider auth stays outside this repository.

## Important limitation: environment scrubbing is not isolation

Removing `TELEGRAM_BOT_TOKEN` from Prime's inherited environment prevents accidental/simple access through `os.environ`, but a Prime process running under the same Unix UID is not a hard security boundary from the bridge or its host. Depending on the OS and process configuration, same-user processes may inspect each other or read other same-user files.

For a stronger boundary, run the bridge secret and Prime execution environment under separate users/containers/VMs with the minimum filesystem/network access each needs. That deployment is outside this repository's default systemd-user example.

## Delivery/replay risk

The bridge holds Telegram acknowledgement behind in-flight handling, but Telegram update acknowledgement and Prime prompt admission are not one atomic transaction. A crash after Prime accepts a prompt but before Telegram acknowledgement can cause the update to be replayed. Do not use the bot for non-idempotent high-impact actions without an application-level confirmation/idempotency policy.

## Operator hardening

- Run under a dedicated Unix user if the Prime workspace is sensitive.
- For strong Telegram-secret isolation, separate the Telegram transport credentials from the Prime execution principal rather than relying only on environment scrubbing.
- Set `PRIME_WORKDIR` to the smallest directory tree Prime needs.
- Keep the bot in private chat unless group access is intentional.
- Rotate the bot token immediately if it appears in logs, shell history, a commit, or a screenshot.
- Review Prime's own tool/security settings before enabling unattended or autonomous work.
