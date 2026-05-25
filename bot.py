import email
import json
import logging
import os
import time
from email import policy
from pathlib import Path

import html2text
import requests
from dotenv import load_dotenv
from imapclient import IMAPClient

load_dotenv()

IMAP_HOST = "imap.purelymail.com"
IMAP_PORT = 993
USER = os.environ["PURELYMAIL_USER"]
PASSWORD = os.environ["PURELYMAIL_PASS"]
WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

STATE_FILE = Path(os.environ.get("STATE_FILE", Path(__file__).parent / "state.json"))
IDLE_REFRESH_SECONDS = 25 * 60  # re-issue IDLE before the 29-min RFC limit

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("mailbot")

_h2t = html2text.HTML2Text()
_h2t.ignore_links = False
_h2t.ignore_images = True
_h2t.body_width = 0  # don't wrap


def load_last_uid() -> int:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text()).get("last_uid", 0)
    return 0


def save_last_uid(uid: int) -> None:
    STATE_FILE.write_text(json.dumps({"last_uid": uid}))


def extract_body(msg: email.message.EmailMessage) -> str:
    body = msg.get_body(preferencelist=("plain", "html"))
    if body is None:
        return ""
    content = body.get_content()
    if body.get_content_type() == "text/html":
        content = _h2t.handle(content)
    return content.strip()


def post_to_discord(text: str) -> None:
    if not text:
        text = "(empty message)"
    # Discord embed description limit is 4096 chars
    if len(text) > 4090:
        text = text[:4090] + "\n…(truncated)"
    resp = requests.post(
        WEBHOOK_URL,
        json={"embeds": [{"description": text}]},
        timeout=15,
    )
    resp.raise_for_status()


def forward_uid(client: IMAPClient, uid: int) -> None:
    data = client.fetch([uid], ["RFC822"])
    raw = data[uid][b"RFC822"]
    msg = email.message_from_bytes(raw, policy=policy.default)
    post_to_discord(extract_body(msg))
    log.info("forwarded uid=%s", uid)


def fetch_and_forward_new(client: IMAPClient, last_uid: int) -> int:
    uids = client.search(["UID", f"{last_uid + 1}:*"])
    # IMAP returns the highest UID even when N:* is past it; filter manually.
    uids = sorted(u for u in uids if u > last_uid)
    for uid in uids:
        try:
            forward_uid(client, uid)
        except Exception:
            log.exception("failed to forward uid=%s; will retry", uid)
            return last_uid
        last_uid = uid
        save_last_uid(last_uid)
    return last_uid


def run() -> None:
    while True:
        try:
            log.info("connecting to %s", IMAP_HOST)
            with IMAPClient(IMAP_HOST, port=IMAP_PORT, ssl=True) as client:
                client.login(USER, PASSWORD)
                client.select_folder("INBOX")

                last_uid = load_last_uid()
                if last_uid == 0:
                    all_uids = client.search(["ALL"])
                    last_uid = max(all_uids) if all_uids else 0
                    save_last_uid(last_uid)
                    log.info("first run; baseline last_uid=%s", last_uid)

                last_uid = fetch_and_forward_new(client, last_uid)

                while True:
                    client.idle()
                    log.info("IDLE…")
                    responses = client.idle_check(timeout=IDLE_REFRESH_SECONDS)
                    client.idle_done()
                    if responses:
                        log.info("IDLE notif: %s", responses)
                    last_uid = fetch_and_forward_new(client, last_uid)
        except Exception:
            log.exception("connection error; reconnecting in 30s")
            time.sleep(30)


if __name__ == "__main__":
    run()
