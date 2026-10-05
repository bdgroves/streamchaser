"""Entry point: python -m streamchaser

Posts only when a river is doing something unusual for the time of year:

  FLOOD   big river at or above 5,000 cfs
  RECORD  above the highest flow ever measured on this date (20+ years of
          record, and at least 10 cfs)
  STORM   free-flowing stream more than doubled in 24 h and now running above
          normal for the date (Merced in Yosemite, Big Creek)

Dam releases on the regulated reaches move every day and are not news, so a
"new 7-day peak" or a fast rise on its own no longer posts. One post per run
at most, and a station won't post the same level again for 3 days (a higher
level still posts). Charts are drawn for every station every run.

X only posts when the repo variable POST_TO_X is "on" (it's off while the X
account has no API credits). Bluesky posts as before.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from .chart import generate_chart
from .gauge import build_report
from .poster import post_to_bluesky, post_to_twitter

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout),
              logging.FileHandler("logs/last_run.log", "w", "utf-8")])
log = logging.getLogger("streamchaser")

# (station_id, name, hashtags, free_flowing, big_river)
STATIONS = [
    ("11276500", "Tuolumne R at Hetch Hetchy",   "#Tuolumne #HetchHetchy", False, True),
    ("11274790", "Tuolumne R Grand Canyon",      "#Tuolumne #Yosemite",    False, True),
    ("11276900", "Tuolumne R BL Early Intake",   "#Tuolumne #Groveland",   False, True),
    ("11289650", "Tuolumne R BL LaGrange Dam",   "#Tuolumne #LaGrange",    False, True),
    ("11290000", "Tuolumne R at Modesto",        "#Tuolumne #Modesto",     False, True),
    ("11264500", "Merced R at Happy Isles",      "#Merced #Yosemite",      True,  True),
    ("11266500", "Merced R at Pohono Bridge",    "#Merced #Yosemite",      True,  True),
    ("11303000", "Stanislaus R at Ripon",        "#Stanislaus #Ripon",     False, True),
    ("11284400", "Big Creek @ Whites Gulch",     "#BigCreek #Groveland",   True,  False),
    ("11278300", "Cherry Creek NR Early Intake", "#CherryCreek #Tuolumne", False, False),
]

FLOOD_CFS = 5_000
STORM_MIN_RISE_CFS = 10
RECORD_MIN_YEARS = 20
RECORD_MIN_CFS = 10  # a dry creek at 1 cfs isn't news, even if it's a record
COOLDOWN = timedelta(days=3)
LEVELS = {"STORM": 1, "RECORD": 2, "FLOOD": 3}
STATE_FILE = "state.json"
DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
X_ON = os.environ.get("POST_TO_X", "").lower() == "on"


def notable(report, free_flowing: bool, big_river: bool) -> tuple[str, str] | None:
    """(level, headline) if this reading is worth a post, else None."""
    cur, s = report.current, report.stats
    if big_river and cur >= FLOOD_CFS:
        return "FLOOD", f"🔴 High water: {cur:,.0f} cfs"
    if s.high and (s.years or 0) >= RECORD_MIN_YEARS and cur > s.high and cur >= RECORD_MIN_CFS:
        return "RECORD", f"📈 Highest ever for the date: {cur:,.0f} cfs (old record {s.high:,.0f}, {s.years} yrs)"
    if free_flowing:
        before = cur - report.delta_24h
        rise = report.delta_24h
        normal_hi = s.p75 or s.mean
        if (before > 0 and cur >= 2 * before and rise >= STORM_MIN_RISE_CFS
                and normal_hi and cur > normal_hi):
            return "STORM", f"🌧️ Storm rise: {before:,.0f} → {cur:,.0f} cfs in 24 h"
    return None


def post_text(report, sid, name, tags, headline) -> str:
    s = report.stats
    normal = (f"Normal for today: {s.p25:,.0f}–{s.p75:,.0f} cfs" if s.p25 is not None and s.p75 is not None
              else f"Average for today: {s.mean:,.0f} cfs" if s.mean else "")
    trend = ("rising" if report.rate_of_change > 0.05 else
             "falling" if report.rate_of_change < -0.05 else "steady")
    lines = [headline, f"{name} · now {trend}"]
    if normal:
        lines.append(normal)
    lines += [f"https://waterdata.usgs.gov/monitoring-location/{sid}/", f"{tags} #SierraNevada"]
    return "\n".join(lines)


def load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")


def record(network: str, sid: str, outcome: str, text: str) -> None:
    path = "logs/posts.jsonl"
    lines = open(path, encoding="utf-8").read().splitlines() if os.path.exists(path) else []
    lines.append(json.dumps({"t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                             "network": network, "station": sid, "outcome": outcome, "text": text},
                            ensure_ascii=False))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines[-500:]) + "\n")


def due(state: dict, sid: str, level: str, now: datetime) -> bool:
    last = state.get("stations", {}).get(sid)
    if not last:
        return True
    when = datetime.fromisoformat(last["time"])
    return LEVELS[level] > LEVELS.get(last["level"], 0) or now - when >= COOLDOWN


def main() -> int:
    log.info("STREAMCHASER · Sierra Nevada watersheds")
    now = datetime.now(timezone.utc)
    state = load_state()
    best = None
    for sid, name, tags, free, big in STATIONS:
        try:
            report = build_report(sid, name)
        except Exception as e:
            log.error(f"{name}: no data ({e})")
            continue
        chart = None
        try:
            chart = generate_chart(report, station_url=f"https://waterdata.usgs.gov/monitoring-location/{sid}/")
        except Exception as e:
            log.error(f"{name}: chart failed ({e})")
        hit = notable(report, free, big)
        log.info(f"{name}: {report.current:,.1f} cfs · {hit[1] if hit else 'nothing unusual'}")
        if not hit or not chart or not due(state, sid, hit[0], now):
            continue
        if best is None or LEVELS[hit[0]] > LEVELS[best[4]]:
            best = (report, sid, name, tags, hit[0], hit[1], chart)

    if not best:
        log.info("Nothing unusual on any river. Silent run.")
        return 0

    report, sid, name, tags, level, headline, chart = best
    text = post_text(report, sid, name, tags, headline)
    log.info(f"POST {level} {name}\n{text}")
    if DRY_RUN:
        record("all", sid, "dry-run", text)
        return 0

    exit_code, sent = 0, False
    networks = [("bluesky", lambda: post_to_bluesky(text, chart, report),
                 bool(os.environ.get("BLUESKY_HANDLE")))]
    if X_ON:
        networks.append(("x", lambda: post_to_twitter(text, chart),
                         bool(os.environ.get("TWITTER_API_KEY"))))
    else:
        record("x", sid, "standing by (POST_TO_X is off)", text)
    for net, send, configured in networks:
        if not configured:
            continue
        st = state.setdefault("networks", {}).setdefault(net, {"ok": True})
        try:
            send()
        except Exception as e:
            err = f"{type(e).__name__}: {e}"[:300]
            log.error(f"{net}: post failed: {err}")
            record(net, sid, f"error: {err}", text)
            if st.get("ok", True):
                log.error(f"{net} stopped accepting posts. Failing this run once so GitHub sends an email.")
                exit_code = 1
            st.update(ok=False, error=err)
            continue
        sent = True
        st.update(ok=True, error="")
        record(net, sid, "posted", text)
        log.info(f"{net}: posted")
    if sent or not networks or all(not c for _, _, c in networks):
        # Remember it even when nothing could be sent, so it doesn't repeat hourly.
        state.setdefault("stations", {})[sid] = {"level": level, "time": now.isoformat(timespec="minutes"),
                                                 "cfs": report.current}
    save_state(state)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
