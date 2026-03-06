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
# Each entry: (station_id, station_name, hashtags)
STATIONS = [
    (
        os.getenv("USGS_STATION_ID",   "11284400"),
        os.getenv("USGS_STATION_NAME", "Big Creek @ Whites Gulch"),
        os.getenv("USGS_HASHTAGS",     "#USGS #BigCreek #Groveland"),
    ),
    ("11276900", "Tuolumne R BL Early Intake", "#USGS #Tuolumne #Groveland"),
    ("11278300", "Cherry Creek NR Early Intake", "#USGS #CherryCreek #Tuolumne"),
]

POST_TWITTER = os.getenv("POST_TWITTER", "true").lower() == "true"
POST_BLUESKY = os.getenv("POST_BLUESKY", "true").lower() == "true"

# ── Notable event detection ───────────────────────────────────────────────────

DRY_THRESHOLD   = 1.0   # cfs
RISING_FAST_CFS = 2.0   # cfs/hr
PEAK_WINDOW_HRS = 2.0   # hours

def check_notable(report) -> tuple[bool, str]:
    now = datetime.now(timezone.utc)
    s   = report.stats

    if report.rate_of_change >= RISING_FAST_CFS:
        return True, f"RISING FAST  +{report.rate_of_change:.1f} cfs/hr"

    if report.peak_7d_time:
        hrs = (now - report.peak_7d_time.astimezone(timezone.utc)).total_seconds() / 3600
        if hrs <= PEAK_WINDOW_HRS:
            return True, f"NEW 7-DAY PEAK  {report.peak_7d:.1f} cfs"

    if s.p75 and report.current > s.p75:
        return True, f"ABOVE NORMAL  {report.current:.1f} cfs > p75 {s.p75:.1f}"

    if report.current < DRY_THRESHOLD:
        return True, f"GOING DRY  {report.current:.2f} cfs"

    prior_approx = report.current - report.delta_24h
    if report.current >= DRY_THRESHOLD and prior_approx < DRY_THRESHOLD and report.delta_24h > 0:
        return True, f"FLOW RETURNING  {report.current:.2f} cfs after near-dry"

    return False, "no notable change"


# ── Text composer ─────────────────────────────────────────────────────────────

def _arrow(delta: float) -> str:
    if delta >  0.05: return "↑"
    if delta < -0.05: return "↓"
    return "→"

def _roc_label(roc: float) -> str:
    if   roc >  2.0: return "rising fast ▲"
    elif roc >  0.5: return "rising"
    elif roc >  0.0: return "rising slowly"
    elif roc < -2.0: return "dropping fast ▼"
    elif roc < -0.5: return "falling"
    else:            return "falling slowly"

def compose_post(report, hashtags: str, reason: str) -> str:
    arrow  = _arrow(report.delta_1h)
    d1h    = f"{report.delta_1h:+.1f}"
    d24h   = f"{report.delta_24h:+.1f}"
    ly     = f"{report.last_year}" if report.last_year else "N/A"
    pct    = f"{report.pct_of_mean:.0f}%" if report.pct_of_mean else "N/A"
    roc    = _roc_label(report.rate_of_change)
    peak_t = report.peak_7d_time.strftime("%-m/%-d %H:%Mz") if report.peak_7d_time else "N/A"
    url    = f"https://waterdata.usgs.gov/monitoring-location/{report.station_id}/"

    return (
        f"⚡ {reason}\n"
        f"{report.station_name} (USGS {report.station_id})\n"
        f"Flow {report.current} cfs {arrow}  {roc}\n"
        f"Δ 1h {d1h} · 24h {d24h} cfs\n"
        f"7d peak {report.peak_7d:.1f} cfs @ {peak_t}\n"
        f"7d range {report.range_7d_lo:.1f}–{report.range_7d_hi:.1f} cfs\n"
        f"vs hist avg {pct}  ·  LY ≈ {ly} cfs\n"
        f"{url}\n"
        f"{hashtags}"
    )


# ── Per-station runner ────────────────────────────────────────────────────────

def run_station(station_id: str, station_name: str, hashtags: str) -> bool:
    """Process one station. Returns True if post was attempted."""
    log.info("─" * 56)
    log.info(f"  {station_name}  ({station_id})")
    log.info("─" * 56)

    url = f"https://waterdata.usgs.gov/monitoring-location/{station_id}/"

    try:
        report = build_report(station_id, station_name)
    except Exception as e:
        log.error(f"  Failed to fetch {station_id}: {e}")
        return False

    log.info(f"  Current  : {report.current} cfs  {_arrow(report.delta_1h)}")
    log.info(f"  Δ 1h/24h : {report.delta_1h:+.2f} / {report.delta_24h:+.2f} cfs")
    log.info(f"  ROC      : {report.rate_of_change:+.3f} cfs/hr")
    log.info(f"  Peak 7d  : {report.peak_7d} cfs @ {report.peak_7d_time}")

    should_post, reason = check_notable(report)
    log.info(f"  Notable  : {should_post}  —  {reason}")

    # Always render chart and save to chart/gauge_STATIONID.png
    chart_path = generate_chart(report, station_url=url)
    log.info(f"  Chart    : {chart_path}")

    # Copy to per-gauge path for README / repo
    chart_dest = f"/tmp/latest_{station_id}.png"
    import shutil
    shutil.copy(chart_path, chart_dest)

    if not should_post:
        return False

    text = compose_post(report, hashtags, reason)
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
