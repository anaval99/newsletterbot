# newsletterbot

A small Python service that forwards new mail from a [PurelyMail](https://purelymail.com) inbox to a Discord channel via webhook.

## How it works

- Opens an IMAP connection to `imap.purelymail.com:993` (SSL).
- Uses **IMAP IDLE** ([RFC 2177](https://datatracker.ietf.org/doc/html/rfc2177)) so PurelyMail pushes notifications when new mail arrives — no polling.
- On each new message, extracts the plain-text body (converts HTML to text if no plain part exists) and POSTs it to a Discord webhook.
- Tracks the last forwarded message via UID in `state.json`, so restarts and outages don't cause duplicates or missed mail.
- Reconnects automatically on network errors with 30-second backoff.

## Prerequisites

- A PurelyMail account. If 2FA is enabled, generate an **App Password** and use that as `PURELYMAIL_PASS`.
- A Discord channel webhook URL (Channel → Edit Channel → Integrations → Webhooks → New Webhook → Copy URL). Requires **Manage Webhooks** permission.

## Configuration

Copy `.env.example` to `.env` and fill in:

```dotenv
PURELYMAIL_USER=you@yourdomain.com
PURELYMAIL_PASS=your-password-or-app-password
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/XXXX/YYYY
```

## Run with Docker (recommended)

```powershell
docker compose up -d --build
docker compose logs -f
```

State is persisted to `./volumes/botstate/state.json` on the host via bind mount.

Other useful commands:

```powershell
docker compose restart      # restart after editing code or .env
docker compose down         # stop and remove the container (state survives)
docker compose down -v      # also wipe state (next start skips existing inbox)
```

## Run locally (no Docker)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python bot.py
```

State is written to `state.json` next to `bot.py` unless `STATE_FILE` env var is set.

## State and delivery semantics

- `state.json` holds a single field: the highest IMAP UID that has been successfully forwarded.
- On first run, the file is created with the **current max UID** so existing inbox mail is *not* backfilled. Delete the file (or set `last_uid` to `0`) before first start if you want backfill.
- Delivery is **at-least-once**: if the process crashes between a successful Discord POST and writing the new UID to disk, that one message will be re-sent on the next start. There is no at-most-once mode.
- The file write is not atomic. Power loss during the write could corrupt it; on next start the bot treats a missing/unreadable file as first-run and skips any unforwarded mail.

## Project structure

```
.
├── bot.py              # IMAP IDLE loop + Discord webhook poster
├── requirements.txt    # imapclient, html2text, requests, python-dotenv
├── Dockerfile          # python:3.12-slim, non-root user, state at /data
├── compose.yaml        # bind-mounts ./volumes/botstate -> /data
├── .env.example        # template for required env vars
├── .dockerignore
└── volumes/botstate/   # bind-mounted state directory (created on first run)
```

## Limitations

- Forwards body text only — no sender, subject, date, or attachments. Trivial to extend in `extract_body`.
- Discord message content is capped at 2000 characters; longer bodies are truncated with a `…(truncated)` marker.
- Watches `INBOX` only. Add Sieve rules in PurelyMail webmail if you want to filter what lands there.
- Does not handle `UIDVALIDITY` changes (extremely rare on PurelyMail). If it ever changes, manually reset `state.json`.
