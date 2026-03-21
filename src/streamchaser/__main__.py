"""Entry point: python -m streamchaser"""

import os
import logging
from datetime import datetime, timezone

from .gauge  import build_report
from .chart  import generate_chart
from .poster import post_to_twitter, post_to_bluesky

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Stations ───────────────────────────────────────────────────────────────────
# (station_id, station_name, hashtags, mode)
# mode: "proportional" = small/unregulated streams
#       "absolute"     = large/regulated rivers

STATIONS = [
    # Tuolumne — headwaters → valley
    ("11276500", "Tuolumne R at Hetch Hetchy",    "#USGS #Tuolumne #HetchHetchy", "absolute"),
    ("11274790", "Tuolumne R Grand Canyon",        "#USGS #Tuolumne #GrandCanyon", "absolute"),
    ("11276900", "Tuolumne R BL Early Intake",     "#USGS #Tuolumne #Groveland",   "absolute"),
    ("11289650", "Tuolumne R BL LaGrange Dam",     "#USGS #Tuolumne #LaGrange",    "absolute"),
    ("11290000", "Tuolumne R at Modesto",          "#USGS #Tuolumne #Modesto",     "absolute"),
    # Merced
    ("11264500", "Merced R at Happy Isles",        "#USGS #Merced #Yosemite",      "absolute"),
    ("11266500", "Merced R at Pohono Bridge",      "#USGS #Merced #Yosemite",      "absolute"),
    # Stanislaus
    ("11303000", "Stanislaus R at Ripon",          "#USGS #Stanislaus #Ripon",     "absolute"),
    # Local tributaries
    ("11284400", "Big Creek @ Whites Gulch",       "#USGS #BigCreek #Groveland",   "proportional"),
    ("11278300", "Cherry Creek NR Early Intake",   "#USGS #CherryCreek #Tuolumne", "proportional"),
]

POST_TWITTER = os.getenv("TWITTER_API_KEY") is not None
POST_BLUESKY = os.getenv("BLUESKY_HANDLE")  is not None

# ── Absolute thresholds (large/regulated rivers) ───────────────────────────────
ELEVATED_CFS = 200
HIGH_CFS     = 1_000
FLOOD_CFS    = 5_000

# ── Notability scores — higher = more important ────────────────────────────────
# Used to pick the single most notable event across all gauges each run.
SCORE = {
    "🔴 FLOOD":       100,
    "🟠 HIGH FLOW":    80,
    "NEW 7-DAY PEAK":  60,
    "RISING FAST":     50,
    "🟡 ELEVATED":     40,
    "ABOVE NORMAL":    30,
    "GOING DRY":       20,
    "FLOW RETURNING":  10,
}


def _score(reason: str) -> int:
    for key, val in SCORE.items():
        if reason.startswith(key):
            return val
    return 0


# ── Notability ────────────────────────────────────────────────────────────────

def check_notable(report, mode: str) -> tuple[bool, str]:
    now = datetime.now(timezone.utc)
    s   = report.stats

    # Shared: new 7-day peak
    if report.peak_7d_time:
        age = (now - report.peak_7d_time.replace(tzinfo=timezone.utc)
               if report.peak_7d_time.tzinfo is None
               else now - report.peak_7d_time)
        if abs(age.total_seconds()) < 7200:
            return True, f"NEW 7-DAY PEAK  {report.peak_7d:.1f} cfs"

    # Shared: going dry
    if report.current < 1.0:
        return True, f"GOING DRY  {report.current:.2f} cfs"

    # Shared: flow returning
    if report.delta_24h > 0 and (report.current - report.delta_24h) < 1.0:
        return True, f"FLOW RETURNING  {report.current:.2f} cfs"

    if mode == "proportional":
        mean_flow     = s.mean if s.mean else 30.0
        rising_thresh = max(2.0, min(50.0, mean_flow * 0.10))
        if report.rate_of_change >= rising_thresh:
            return True, f"RISING FAST  +{report.rate_of_change:.1f} cfs/hr"

    else:  # absolute
        cur  = report.current
        prev = cur - report.delta_1h

        if cur >= FLOOD_CFS:
            return True, f"🔴 FLOOD  {cur:,.0f} cfs"
        if cur >= HIGH_CFS and prev < HIGH_CFS:
            return True, f"🟠 HIGH FLOW  {cur:,.0f} cfs"
        if cur >= ELEVATED_CFS and prev < ELEVATED_CFS:
            return True, f"🟡 ELEVATED  {cur:,.0f} cfs"

        mean_flow     = s.mean if s.mean else 500.0
        rising_thresh = max(20.0, min(500.0, mean_flow * 0.05))
        if report.rate_of_change >= rising_thresh:
            return True, f"RISING FAST  +{report.rate_of_change:.0f} cfs/hr"

    return False, "no notable change"


# ── Build post text ───────────────────────────────────────────────────────────

def _post_text(report, station_id, station_name, hashtags, reason) -> str:
    station_url = f"https://waterdata.usgs.gov/monitoring-location/{station_id}/"
    arrow = "↑" if report.delta_1h > 0.05 else ("↓" if report.delta_1h < -0.05 else "→")
    roc_w = ("rising fast ▲" if report.rate_of_change >  0.5  else
             "falling fast ▼" if report.rate_of_change < -0.5  else
             "rising"         if report.rate_of_change >  0.05 else
             "falling"        if report.rate_of_change < -0.05 else
             "steady")
    peak_str = (report.peak_7d_time.strftime("%-m/%-d %H:%Mz")
                if report.peak_7d_time else "—")
    pct_str  = f"{report.pct_of_mean:.0f}%" if report.pct_of_mean else "N/A"
    ly_str   = f"{report.last_year:.1f}"    if report.last_year   else "N/A"

    return (
        f"⚡ {reason}\n"
        f"{station_name} (USGS {station_id})\n"
        f"Flow {report.current:,.1f} cfs {arrow}  {roc_w}\n"
        f"Δ 1h {report.delta_1h:+.1f} · 24h {report.delta_24h:+.1f} cfs\n"
        f"7d peak {report.peak_7d:,.1f} cfs @ {peak_str}\n"
        f"7d range {report.range_7d_lo:,.1f}–{report.range_7d_hi:,.1f} cfs\n"
        f"vs hist avg {pct_str}  ·  LY ≈ {ly_str} cfs\n"
        f"{station_url}\n"
        f"{hashtags}"
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("━" * 56)
    log.info("  STREAMCHASER  ·  Sierra Nevada Watersheds")
    log.info("━" * 56)

    best_score  = -1
    best_event  = None   # (report, station_id, station_name, hashtags, reason, chart_path)

    for station_id, station_name, hashtags, mode in STATIONS:
        log.info("─" * 56)
        log.info(f"  {station_name}  ({station_id})  [{mode}]")
        log.info("─" * 56)

        station_url = f"https://waterdata.usgs.gov/monitoring-location/{station_id}/"

        try:
            report = build_report(station_id, station_name)
        except Exception as e:
            log.error(f"✗  Failed to build report: {e}")
            continue

        # Always generate chart
        try:
            chart_path = generate_chart(report, station_url=station_url)
            log.info(f"  Chart    : {chart_path}")
        except Exception as e:
            log.error(f"✗  Chart failed: {e}")
            chart_path = None

        notable, reason = check_notable(report, mode)
        score = _score(reason) if notable else 0
        log.info(f"  Notable  : {notable}  —  {reason}  [score {score}]")

        MIN_SCORE = 50  # must be Rising Fast or higher to post
        if notable and score >= MIN_SCORE and score > best_score and chart_path:
            best_score = score
            best_event = (report, station_id, station_name, hashtags, reason, chart_path)

    # ── Post the single most notable event ────────────────────────────────────
    if best_event:
        report, sid, sname, hashtags, reason, chart_path = best_event
        text = _post_text(report, sid, sname, hashtags, reason)
        log.info("━" * 56)
        log.info(f"  POSTING BEST EVENT: {sname} — {reason}")
        log.info(f"\nPost text:\n{text}\n")

        if POST_TWITTER:
            try:
                post_to_twitter(text, chart_path)
                log.info("✓  Twitter/X posted")
            except Exception as e:
                log.error(f"✗  Twitter failed: {e}")

        if POST_BLUESKY:
            try:
                post_to_bluesky(text, chart_path, report)
                log.info("✓  Bluesky posted")
            except Exception as e:
                log.error(f"✗  Bluesky failed: {e}")
    else:
        log.info("━" * 56)
        log.info("  No notable events — silent run.")

    log.info("━" * 56)
    log.info("  All stations checked.")

if __name__ == "__main__":
    main()
