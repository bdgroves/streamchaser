"""Entry point: python -m streamchaser"""

import os
import sys
import logging
from datetime import datetime, timezone
from typing import Optional

from .gauge  import build_report
from .chart  import generate_chart
from .poster import post_to_twitter, post_to_bluesky

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

STATION_ID   = os.getenv("USGS_STATION_ID",   "11284400")
STATION_NAME = os.getenv("USGS_STATION_NAME", "Big Creek @ Whites Gulch")
HASHTAGS     = os.getenv("USGS_HASHTAGS",     "#USGS #BigCreek #Groveland")
POST_TWITTER = os.getenv("POST_TWITTER", "true").lower() == "true"
POST_BLUESKY = os.getenv("POST_BLUESKY", "true").lower() == "true"
STATION_URL  = f"https://waterdata.usgs.gov/monitoring-location/{STATION_ID}/"

# ── Notable event detection ───────────────────────────────────────────────────

DRY_THRESHOLD     = 1.0    # cfs — below this is "going dry"
RISING_FAST_CFS   = 2.0    # cfs/hr — rising faster than this is a storm pulse
PEAK_WINDOW_HOURS = 2.0    # consider peak "just set" if within this many hours of now

def check_notable(report) -> tuple[bool, str]:
    """
    Returns (should_post, reason_label).
    Checks five triggers in priority order — returns on first match.
    """
    now = datetime.now(timezone.utc)
    s   = report.stats

    # 1. Rising fast — storm pulse arriving
    if report.rate_of_change >= RISING_FAST_CFS:
        return True, f"RISING FAST  +{report.rate_of_change:.1f} cfs/hr"

    # 2. New 7-day peak set in the last ~2 hours
    if report.peak_7d_time:
        hrs_since_peak = (now - report.peak_7d_time.astimezone(timezone.utc)).total_seconds() / 3600
        if hrs_since_peak <= PEAK_WINDOW_HOURS:
            return True, f"NEW 7-DAY PEAK  {report.peak_7d:.1f} cfs"

    # 3. Above p75 — above normal flow
    if s.p75 and report.current > s.p75:
        return True, f"ABOVE NORMAL  {report.current:.1f} cfs > p75 {s.p75:.1f}"

    # 4. Going dry — dropped below threshold
    if report.current < DRY_THRESHOLD:
        return True, f"GOING DRY  {report.current:.2f} cfs"

    # 5. First flow after near-dry — was low, now recovering
    if report.last_year is not None:
        pass  # can't check prior state without persistence — use 24h delta instead
    # Proxy: was near-dry recently (24h delta was negative from low base,
    # now rising from near-zero). Check: current > threshold but 24h ago was near dry.
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

def compose_post(report, reason: str) -> str:
    arrow  = _arrow(report.delta_1h)
    d1h    = f"{report.delta_1h:+.1f}"
    d24h   = f"{report.delta_24h:+.1f}"
    ly     = f"{report.last_year}" if report.last_year else "N/A"
    pct    = f"{report.pct_of_mean:.0f}%" if report.pct_of_mean else "N/A"
    roc    = _roc_label(report.rate_of_change)
    peak_t = report.peak_7d_time.strftime("%-m/%-d %H:%Mz") if report.peak_7d_time else "N/A"

    return (
        f"⚡ {reason}\n"
        f"{report.station_name} (USGS {report.station_id})\n"
        f"Flow {report.current} cfs {arrow}  {roc}\n"
        f"Δ 1h {d1h} · 24h {d24h} cfs\n"
        f"7d peak {report.peak_7d:.1f} cfs @ {peak_t}\n"
        f"7d range {report.range_7d_lo:.1f}–{report.range_7d_hi:.1f} cfs\n"
        f"vs hist avg {pct}  ·  LY ≈ {ly} cfs\n"
        f"{STATION_URL}\n"
        f"{HASHTAGS}"
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("━" * 56)
    log.info(f"  STREAMCHASER  ·  Station {STATION_ID}")
    log.info("━" * 56)

    report = build_report(STATION_ID, STATION_NAME)

    log.info(f"  Current flow   : {report.current} cfs  {_arrow(report.delta_1h)}")
    log.info(f"  Δ 1h / 24h     : {report.delta_1h:+.2f} / {report.delta_24h:+.2f} cfs")
    log.info(f"  7-day peak     : {report.peak_7d} cfs @ {report.peak_7d_time}")
    log.info(f"  Rate of change : {report.rate_of_change:+.3f} cfs/hr")
    log.info(f"  % of mean      : {report.pct_of_mean}")

    should_post, reason = check_notable(report)
    log.info(f"  Notable        : {should_post}  —  {reason}")

    # Always render and commit the chart for the README
    chart_path = generate_chart(report, station_url=STATION_URL)
    log.info(f"  Chart          : {chart_path}")

    if not should_post:
        log.info("━" * 56)
        log.info("  Nothing notable — skipping post.")
        log.info("━" * 56)
        return

    text = compose_post(report, reason)
    log.info(f"\nPost text:\n{text}\n")

    errors = []

    if POST_TWITTER:
        try:
            post_to_twitter(text, chart_path)
            log.info("✓  Twitter/X posted")
        except Exception as e:
            log.error(f"✗  Twitter failed: {e}")
            errors.append(str(e))

    if POST_BLUESKY:
        try:
            post_to_bluesky(text, chart_path, report)
            log.info("✓  Bluesky posted")
        except Exception as e:
            log.error(f"✗  Bluesky failed: {e}")
            errors.append(str(e))

    if errors:
        sys.exit(1)

    log.info("━" * 56)
    log.info("  All clear.")

if __name__ == "__main__":
    main()
