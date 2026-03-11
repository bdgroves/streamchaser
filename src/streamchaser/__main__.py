"""Entry point: python -m streamchaser"""

import os
import sys
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

# ── Stations ──────────────────────────────────────────────────────────────────
STATIONS = [
    (
        os.getenv("USGS_STATION_ID",   "11284400"),
        os.getenv("USGS_STATION_NAME", "Big Creek @ Whites Gulch"),
        os.getenv("USGS_HASHTAGS",     "#USGS #BigCreek #Groveland"),
    ),
    ("11276900", "Tuolumne R BL Early Intake",   "#USGS #Tuolumne #Groveland"),
    ("11278300", "Cherry Creek NR Early Intake", "#USGS #CherryCreek #Tuolumne"),
]

POST_TWITTER = os.getenv("TWITTER_API_KEY") is not None
POST_BLUESKY = os.getenv("BLUESKY_HANDLE")  is not None


# ── Notability ────────────────────────────────────────────────────────────────

def check_notable(report) -> tuple[bool, str]:
    now = datetime.now(timezone.utc)
    s   = report.stats

    # Scale rising-fast threshold to the gauge's mean (min 2 cfs, max 50 cfs)
    mean_flow     = s.mean if s.mean else 30.0
    rising_thresh = max(2.0, min(50.0, mean_flow * 0.10))

    # 1. Rising fast
    if report.rate_of_change >= rising_thresh:
        return True, f"RISING FAST  +{report.rate_of_change:.1f} cfs/hr"

    # 2. New 7-day peak set within the last 2 hours
    if report.peak_7d_time:
        age = (now - report.peak_7d_time.replace(tzinfo=timezone.utc)
               if report.peak_7d_time.tzinfo is None
               else now - report.peak_7d_time)
        if abs(age.total_seconds()) < 7200:
            return True, f"NEW 7-DAY PEAK  {report.peak_7d:.1f} cfs"

    # 3. Above normal (above p75)
    if s.p75 and report.current > s.p75:
        return True, f"ABOVE NORMAL  {report.current:.1f} cfs > p75 {s.p75:.1f}"

    # 4. Going dry
    if report.current < 1.0:
        return True, f"GOING DRY  {report.current:.2f} cfs"

    # 5. Flow returning after dry spell
    if report.delta_24h > 0 and (report.current - report.delta_24h) < 1.0:
        return True, f"FLOW RETURNING  {report.current:.2f} cfs"

    return False, "no notable change"


# ── Per-station run ───────────────────────────────────────────────────────────

def run_station(station_id: str, station_name: str, hashtags: str) -> bool:
    log.info("─" * 56)
    log.info(f"  {station_name}  ({station_id})")
    log.info("─" * 56)

    station_url = f"https://waterdata.usgs.gov/monitoring-location/{station_id}/"

    try:
        report = build_report(station_id, station_name)
    except Exception as e:
        log.error(f"✗  Failed to build report: {e}")
        return False

    # Always generate chart (commits to repo every run)
    try:
        chart_path = generate_chart(report, station_url=station_url)
        log.info(f"  Chart    : {chart_path}")
    except Exception as e:
        log.error(f"✗  Chart failed: {e}")
        chart_path = None

    notable, reason = check_notable(report)
    log.info(f"  Notable  : {notable}  —  {reason}")

    if not notable:
        return False

    # Build post text
    arrow = "↑" if report.delta_1h > 0.05 else ("↓" if report.delta_1h < -0.05 else "→")
    roc_w = "rising fast ▲" if report.rate_of_change > 0.5 else \
            ("falling ▼"   if report.rate_of_change < -0.5 else \
            ("rising"      if report.rate_of_change > 0.05 else \
            ("falling"     if report.rate_of_change < -0.05 else "steady")))
    peak_str = (report.peak_7d_time.strftime("%-m/%-d %H:%Mz")
                if report.peak_7d_time else "—")
    ly_str   = f"{report.last_year:.2f}" if report.last_year else "N/A"
    pct_str  = f"{report.pct_of_mean:.0f}%" if report.pct_of_mean else "N/A"

    text = (
        f"⚡ {reason}\n"
        f"{station_name} (USGS {station_id})\n"
        f"Flow {report.current:.1f} cfs {arrow}  {roc_w}\n"
        f"Δ 1h {report.delta_1h:+.1f} · 24h {report.delta_24h:+.1f} cfs\n"
        f"7d peak {report.peak_7d:.1f} cfs @ {peak_str}\n"
        f"7d range {report.range_7d_lo:.1f}–{report.range_7d_hi:.1f} cfs\n"
        f"vs hist avg {pct_str}  ·  LY ≈ {ly_str} cfs\n"
        f"{station_url}\n"
        f"{hashtags}"
    )

    log.info(f"\nPost text:\n{text}\n")

    if not chart_path:
        log.warning("  No chart — skipping social posts")
        return False

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

    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("━" * 56)
    log.info("  STREAMCHASER  ·  Tuolumne Watershed")
    log.info("━" * 56)

    for station_id, station_name, hashtags in STATIONS:
        run_station(station_id, station_name, hashtags)

    log.info("━" * 56)
    log.info("  All stations checked.")

if __name__ == "__main__":
    main()
