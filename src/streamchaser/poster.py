"""
poster.py — Social posting for Twitter/X and Bluesky.

Twitter:  tweepy v4  (OAuth 1.0a, API v2 tweet + v1.1 media upload)
Bluesky:  atproto SDK  (App Password auth, blob upload, rich-text facets)
"""

import os
import logging
import re
from datetime import datetime, timezone

log = logging.getLogger(__name__)


# ── Twitter / X ────────────────────────────────────────────────────────────────

def post_to_twitter(text: str, image_path: str) -> None:
    """
    Post text + image to Twitter/X.

    Required secrets (env vars):
        TWITTER_API_KEY          Consumer Key
        TWITTER_API_SECRET       Consumer Secret
        TWITTER_ACCESS_TOKEN     Account Access Token
        TWITTER_ACCESS_SECRET    Account Access Token Secret
    """
    import tweepy

    auth = tweepy.OAuth1UserHandler(
        os.environ["TWITTER_API_KEY"],
        os.environ["TWITTER_API_SECRET"],
        os.environ["TWITTER_ACCESS_TOKEN"],
        os.environ["TWITTER_ACCESS_SECRET"],
    )
    api_v1 = tweepy.API(auth)
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
    """
    Post text + image to Bluesky.

    Required secrets (env vars):
        BLUESKY_HANDLE          e.g. yourhandle.bsky.social
        BLUESKY_APP_PASSWORD    App Password (NOT your login password)
    """
    from atproto import Client

    handle   = os.environ["BLUESKY_HANDLE"]
    password = os.environ["BLUESKY_APP_PASSWORD"]

    client = Client()
    client.login(handle, password)

    with open(image_path, "rb") as f:
        blob_resp = client.upload_blob(f.read())
    blob = blob_resp.blob

    alt = (
        f"Stream flow chart for {report.station_name} (USGS {report.station_id}). "
        f"Current: {report.current} cfs. "
        f"7-day range: {report.range_7d_lo}–{report.range_7d_hi} cfs. "
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


# ── SMS via Twilio ─────────────────────────────────────────────────────────────

def send_sms(text: str, reason: str, report) -> None:
    """
    Send an SMS alert via Twilio.

    Required secrets (env vars):
        TWILIO_ACCOUNT_SID
        TWILIO_AUTH_TOKEN
        TWILIO_FROM          your Twilio number e.g. +18664765090
        TWILIO_TO            your cell number e.g. +12067190742
    """
    import urllib.request
    import urllib.parse
    import base64

    account_sid = os.environ["TWILIO_ACCOUNT_SID"]
    auth_token  = os.environ["TWILIO_AUTH_TOKEN"]
    from_number = os.environ["TWILIO_FROM"]
    to_number   = os.environ["TWILIO_TO"]

    # Compact SMS — just the essentials, no hashtags or URL noise
    arrow = "↑" if report.delta_1h > 0.05 else ("↓" if report.delta_1h < -0.05 else "→")
    sms = (
        f"⚡ {reason}\n"
        f"{report.station_name}\n"
        f"{report.current} cfs {arrow}  Δ1h {report.delta_1h:+.1f}\n"
        f"7d peak {report.peak_7d:.1f} cfs\n"
        f"waterdata.usgs.gov/monitoring-location/{report.station_id}/"
    )

    url  = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    data = urllib.parse.urlencode({
        "From": from_number,
        "To":   to_number,
        "Body": sms,
    }).encode()

    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": f"Basic {credentials}",
        "Content-Type":  "application/x-www-form-urlencoded",
    })

    with urllib.request.urlopen(req) as resp:
        if resp.status == 201:
            log.info(f"✓  SMS sent to {to_number}")
        else:
            log.warning(f"  SMS unexpected status {resp.status}")


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
