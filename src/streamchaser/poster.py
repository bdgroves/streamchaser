"""
poster.py — Social posting for Twitter/X, Bluesky, and SMS.
"""

import os
import logging
import re
from datetime import datetime, timezone

log = logging.getLogger(__name__)


# ── Twitter / X ────────────────────────────────────────────────────────────────

def post_to_twitter(text: str, image_path: str) -> None:
    import tweepy
    auth = tweepy.OAuth1UserHandler(
        os.environ["TWITTER_API_KEY"],    os.environ["TWITTER_API_SECRET"],
        os.environ["TWITTER_ACCESS_TOKEN"], os.environ["TWITTER_ACCESS_SECRET"],
    )
    api_v1  = tweepy.API(auth)
    client  = tweepy.Client(
        consumer_key        = os.environ["TWITTER_API_KEY"],
        consumer_secret     = os.environ["TWITTER_API_SECRET"],
        access_token        = os.environ["TWITTER_ACCESS_TOKEN"],
        access_token_secret = os.environ["TWITTER_ACCESS_SECRET"],
    )
    media    = api_v1.media_upload(filename=image_path)
    response = client.create_tweet(text=text, media_ids=[media.media_id])
    log.info(f"Twitter tweet id={response.data['id']}")


# ── Bluesky ────────────────────────────────────────────────────────────────────

def post_to_bluesky(text: str, image_path: str, report) -> None:
    from atproto import Client

    # Bluesky hard limit: 300 graphemes
    if len(text) > 300:
        text = text[:297] + "..."

    handle   = os.environ["BLUESKY_HANDLE"]
    password = os.environ["BLUESKY_APP_PASSWORD"]
    client   = Client()
    client.login(handle, password)

    with open(image_path, "rb") as f:
        blob_resp = client.upload_blob(f.read())
    blob = blob_resp.blob

    alt = (
        f"Stream flow chart for {report.station_name} (USGS {report.station_id}). "
        f"Current: {report.current} cfs. "
        f"7-day range: {report.range_7d_lo}-{report.range_7d_hi} cfs. "
        f"Peak: {report.peak_7d} cfs."
    )
    client.app.bsky.feed.post.create(
        repo   = handle,
        record = {
            "$type":     "app.bsky.feed.post",
            "text":      text,
            "facets":    _facets(text),
            "embed": {
                "$type":  "app.bsky.embed.images",
                "images": [{"alt": alt, "image": blob}],
            },
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
    )
    log.info("✓  Bluesky posted")


def _facets(text: str) -> list:
    """Build AT Protocol facets for URLs and #hashtags."""
    facets = []
    for m in re.finditer(r"https?://\S+", text):
        s = len(text[:m.start()].encode())
        e = len(text[:m.end()].encode())
        facets.append({
            "index":    {"byteStart": s, "byteEnd": e},
            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": m.group()}],
        })
    for m in re.finditer(r"#(\w+)", text):
        s = len(text[:m.start()].encode())
        e = len(text[:m.end()].encode())
        facets.append({
            "index":    {"byteStart": s, "byteEnd": e},
            "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": m.group(1)}],
        })
    return facets


# ── SMS via email-to-SMS gateway (Verizon) ─────────────────────────────────────

def send_sms(text: str, reason: str, report) -> None:
    import smtplib
    from email.mime.text import MIMEText

    gmail_user     = os.environ["GMAIL_USER"]
    gmail_password = os.environ["GMAIL_APP_PASSWORD"]
    sms_address    = os.environ["SMS_ADDRESS"]   # e.g. 2067190742@vtext.com

    arrow = "↑" if report.delta_1h > 0.05 else ("↓" if report.delta_1h < -0.05 else "→")
    body = (
        f"{reason}\n"
        f"{report.station_name}\n"
        f"{report.current} cfs {arrow} {report.delta_1h:+.1f}/hr\n"
        f"peak {report.peak_7d:.0f} cfs\n"
        f"usgs.gov/{report.station_id}"
    )

    msg = MIMEText(body)
    msg["From"]    = gmail_user
    msg["To"]      = sms_address
    msg["Subject"] = ""

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, sms_address, msg.as_string())

    log.info(f"✓  SMS sent to {sms_address}")
