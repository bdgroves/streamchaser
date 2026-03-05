"""Entry point: python -m streamchaser"""

import os
import sys
import logging

from .gauge  import build_report
from .chart  import generate_chart
from .poster import post_to_twitter, post_to_bluesky

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Config from environment ────────────────────────────────────────────────────

STATION_ID   = os.getenv("USGS_STATION_ID",   "11284400")
STATION_NAME = os.getenv("USGS_STATION_NAME", "Big Creek @ Whites Gulch")
HASHTAGS     = os.getenv("USGS_HASHTAGS",     "#USGS #BigCreek #Groveland")
POST_TWITTER = os.getenv("POST_TWITTER", "true").lower() == "true"
POST_BLUESKY = os.getenv("POST_BLUESKY", "true").lower() == "true"
STATION_URL  = f"https://waterdata.usgs.gov/monitoring-location/{STATION_ID}/"

# ── Text composer ──────────────────────────────────────────────────────────────

def _arrow(delta: float) -> str:
    if delta >  0.05: return "↑"
    if delta < -0.05: return "↓"
    return "→"

def _roc_label(roc: float) -> str:
    """Rate-of-change description for post text."""
    if   roc >  0.5: return "accelerating ▲"
    elif roc >  0.0: return "rising slowly"
    elif roc < -0.5: return "decelerating ▼"
    else:            return "falling slowly"

def compose_post(report) -> str:
    arrow  = _arrow(report.delta_1h)
    d1h    = f"{report.delta_1h:+.1f}"
    d24h   = f"{report.delta_24h:+.1f}"
    ly     = f"{report.last_year}" if report.last_year else "N/A"
    pct    = f"{report.pct_of_historical:.0f}%" if report.pct_of_historical else "N/A"
    roc    = _roc_label(report.rate_of_change)
    peak_t = report.peak_7d_time.strftime("%-m/%-d %H:%Mz") if report.peak_7d_time else "N/A"

    return (
        f"{report.station_name} (USGS {report.station_id})\n"
        f"Flow {report.current} cfs {arrow}  {roc}\n"
        f"Δ 1h {d1h} · 24h {d24h} cfs\n"
        f"7d peak {report.peak_7d:.1f} cfs @ {peak_t}\n"
        f"7d range {report.range_7d_lo:.1f}–{report.range_7d_hi:.1f} cfs\n"
        f"vs hist avg {pct}  ·  LY ≈ {ly} cfs\n"
        f"{STATION_URL}\n"
        f"{HASHTAGS}"
    )

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    log.info("━" * 56)
    log.info(f"  STREAMCHASER  ·  Station {STATION_ID}")
    log.info("━" * 56)

    report = build_report(STATION_ID, STATION_NAME)

    log.info(f"  Current flow   : {report.current} cfs  {_arrow(report.delta_1h)}")
    log.info(f"  Δ 1h / 24h     : {report.delta_1h:+.2f} / {report.delta_24h:+.2f} cfs")
    log.info(f"  7-day peak     : {report.peak_7d} cfs @ {report.peak_7d_time}")
    log.info(f"  Rate of change : {report.rate_of_change:+.3f} cfs/hr")
    log.info(f"  % of hist avg  : {report.pct_of_historical}")

    chart_path = generate_chart(report, station_url=STATION_URL)
    log.info(f"  Chart          : {chart_path}")

    text = compose_post(report)
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
