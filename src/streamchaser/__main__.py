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
#
# Each entry:
#   station_id   — USGS site number
#   station_name — display name
#   hashtags     — appended to social posts
#   mode         — "proportional"  small/unregulated streams: thresholds scale
#                                  with historical mean (Big Creek, Cherry Creek)
#                — "absolute"      large/regulated rivers: fixed cfs thresholds
#                                  (Elevated ≥200, High ≥1000, Flood ≥5000)
#
# Watershed groupings (for log readability):
#   Tuolumne — headwaters → valley
#   Merced   — Yosemite gauges
#   Stanislaus — valley floor
#   Local    — Groveland-area tributaries

STATIONS = [
    # ── Tuolumne ──────────────────────────────────────────────────────────────
    # Headwaters: first to spike in a storm
    ("11276500", "Tuolumne R at Hetch Hetchy",       "#USGS #Tuolumne #HetchHetchy",    "absolute"),
    # Wild canyon reach — below Hetch Hetchy, above any valley influence
    ("11274790", "Tuolumne R Grand Canyon",           "#USGS #Tuolumne #GrandCanyon",    "absolute"),
    # Early Intake — above Cherry Creek confluence, pre-Don Pedro
    ("11276900", "Tuolumne R BL Early Intake",        "#USGS #Tuolumne #Groveland",      "absolute"),
    # LaGrange — below all major dams, what actually enters the valley
    ("11289650", "Tuolumne R BL LaGrange Dam",        "#USGS #Tuolumne #LaGrange",       "absolute"),
    # Modesto — valley floor, the bottom line
    ("11290000", "Tuolumne R at Modesto",             "#USGS #Tuolumne #Modesto",        "absolute"),

    # ── Merced ────────────────────────────────────────────────────────────────
    # Happy Isles — raw Yosemite backcountry signal, above Pohono
    ("11264500", "Merced R at Happy Isles",           "#USGS #Merced #Yosemite",         "absolute"),
    # Pohono Bridge — classic Yosemite Valley gauge, spectacular in flood years
    ("11266500", "Merced R at Pohono Bridge",         "#USGS #Merced #Yosemite",         "absolute"),

    # ── Stanislaus ────────────────────────────────────────────────────────────
    # Ripon — valley floor, below New Melones Reservoir
    ("11303000", "Stanislaus R at Ripon",             "#USGS #Stanislaus #Ripon",        "absolute"),

    # ── Local tributaries ─────────────────────────────────────────────────────
    # Big Creek — no dams, pure snowmelt signal, the canary in the watershed
    ("11284400", "Big Creek @ Whites Gulch",          "#USGS #BigCreek #Groveland",      "proportional"),
    # Cherry Creek — high-country canary, spikes first
    ("11278300", "Cherry Creek NR Early Intake",      "#USGS #CherryCreek #Tuolumne",    "proportional"),
]

POST_TWITTER = os.getenv("TWITTER_API_KEY") is not None
POST_BLUESKY = os.getenv("BLUESKY_HANDLE")  is not None

# ── Absolute thresholds (large/regulated rivers) ───────────────────────────────
# Mirrors sierra-streamflow dashboard levels
ELEVATED_CFS = 200
HIGH_CFS     = 1_000
FLOOD_CFS    = 5_000


# ── Notability ────────────────────────────────────────────────────────────────

def check_notable(report, mode: str) -> tuple[bool, str]:
    now = datetime.now(timezone.utc)
    s   = report.stats

    # ── Shared trigger: new 7-day peak (all gauges) ───────────────────────────
    if report.peak_7d_time:
        age = (now - report.peak_7d_time.replace(tzinfo=timezone.utc)
               if report.peak_7d_time.tzinfo is None
               else now - report.peak_7d_time)
        if abs(age.total_seconds()) < 7200:
            return True, f"NEW 7-DAY PEAK  {report.peak_7d:.1f} cfs"

    # ── Shared trigger: going dry (all gauges) ────────────────────────────────
    if report.current < 1.0:
        return True, f"GOING DRY  {report.current:.2f} cfs"

    # ── Shared trigger: flow returning after dry spell ────────────────────────
    if report.delta_24h > 0 and (report.current - report.delta_24h) < 1.0:
        return True, f"FLOW RETURNING  {report.current:.2f} cfs"

    if mode == "proportional":
        # ── Small/unregulated streams ─────────────────────────────────────────
        mean_flow     = s.mean if s.mean else 30.0
        rising_thresh = max(2.0, min(50.0, mean_flow * 0.10))

        if report.rate_of_change >= rising_thresh:
            return True, f"RISING FAST  +{report.rate_of_change:.1f} cfs/hr"

        if s.p75 and report.current > s.p75:
            return True, f"ABOVE NORMAL  {report.current:.1f} cfs > p75 {s.p75:.1f}"

    else:
        # ── Large/regulated rivers — absolute cfs thresholds ─────────────────
        cur = report.current

        # Flood alert
        if cur >= FLOOD_CFS:
            return True, f"🔴 FLOOD  {cur:,.0f} cfs"

        # High — crossed upward in the last hour
        prev = cur - report.delta_1h
        if cur >= HIGH_CFS and prev < HIGH_CFS:
            return True, f"🟠 HIGH FLOW  {cur:,.0f} cfs"

        # Elevated — crossed upward in the last hour
        if cur >= ELEVATED_CFS and prev < ELEVATED_CFS:
            return True, f"🟡 ELEVATED  {cur:,.0f} cfs"

        # Rising fast — 5% of mean per hour, min 20 cfs, max 500 cfs
        mean_flow     = s.mean if s.mean else 500.0
        rising_thresh = max(20.0, min(500.0, mean_flow * 0.05))
        if report.rate_of_change >= rising_thresh:
            return True, f"RISING FAST  +{report.rate_of_change:.0f} cfs/hr"

        # Above historical normal (p75)
        if s.p75 and report.current > s.p75:
            return True, f"ABOVE NORMAL  {cur:,.0f} cfs > p75 {s.p75:,.0f}"

    return False, "no notable change"


# ── Chart filename slug ───────────────────────────────────────────────────────

def _slug(station_name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "_", station_name.lower()).strip("_")


# ── Per-station run ───────────────────────────────────────────────────────────

def run_station(station_id: str, station_name: str, hashtags: str, mode: str) -> bool:
    log.info("─" * 56)
    log.info(f"  {station_name}  ({station_id})  [{mode}]")
    log.info("─" * 56)

    station_url = f"https://waterdata.usgs.gov/monitoring-location/{station_id}/"

    try:
        report = build_report(station_id, station_name)
    except Exception as e:
        log.error(f"✗  Failed to build report: {e}")
        return False

    try:
        chart_path = generate_chart(report, station_url=station_url)
        log.info(f"  Chart    : {chart_path}")
    except Exception as e:
        log.error(f"✗  Chart failed: {e}")
        chart_path = None

    notable, reason = check_notable(report, mode)
    log.info(f"  Notable  : {notable}  —  {reason}")

    if not notable:
        return False

    # Build post text
    arrow = "↑" if report.delta_1h > 0.05 else ("↓" if report.delta_1h < -0.05 else "→")
    roc_w = ("rising fast ▲" if report.rate_of_change > 0.5  else
             "falling fast ▼" if report.rate_of_change < -0.5 else
             "rising"         if report.rate_of_change > 0.05 else
             "falling"        if report.rate_of_change < -0.05 else
             "steady")
    peak_str = (report.peak_7d_time.strftime("%-m/%-d %H:%Mz")
                if report.peak_7d_time else "—")
    pct_str  = f"{report.pct_of_mean:.0f}%" if report.pct_of_mean else "N/A"
    ly_str   = f"{report.last_year:.1f}"    if report.last_year   else "N/A"

    text = (
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
    log.info("  STREAMCHASER  ·  Sierra Nevada Watersheds")
    log.info("━" * 56)

    for station_id, station_name, hashtags, mode in STATIONS:
        run_station(station_id, station_name, hashtags, mode)

    log.info("━" * 56)
    log.info("  All stations checked.")

if __name__ == "__main__":
    main()
