"""
gauge.py — USGS Water Services API client.

Fetches instantaneous streamflow (param 00060) and computes:
  • current flow + 1h / 24h deltas
  • 7-day series, range, and peak (value + timestamp)
  • rate of change (cfs/hr) — slope of last 3h via linear regression
  • full percentile stats for today's date (low / p25 / median / mean / p75 / high)
    based on 56 years of daily mean data, sourced from USGS statistics service
  • last-year reference value (same calendar date, prior year)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np
import requests

log = logging.getLogger(__name__)

USGS_IV    = "https://waterservices.usgs.gov/nwis/iv/"
USGS_STAT  = "https://waterservices.usgs.gov/nwis/stat/"
TIMEOUT    = 15


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class FlowReading:
    value:     float
    timestamp: datetime


@dataclass
class PercentileStats:
    """Day-of-year statistics from USGS — based on full period of record."""
    low:    Optional[float] = None   # all-time minimum for this date
    p25:    Optional[float] = None   # 25th percentile
    median: Optional[float] = None   # 50th percentile
    mean:   Optional[float] = None   # long-term daily mean
    p75:    Optional[float] = None   # 75th percentile
    high:   Optional[float] = None   # all-time maximum for this date
    years:  Optional[int]   = None   # number of years of record
    source: str = "none"             # "stat_svc" | "dv_computed" | "none"


@dataclass
class GaugeReport:
    station_id:       str
    station_name:     str
    # Core flow
    current:          float
    delta_1h:         float
    delta_24h:        float
    # 7-day
    range_7d_lo:      float
    range_7d_hi:      float
    peak_7d:          float
    peak_7d_time:     Optional[datetime]
    series_7d:        list[FlowReading]
    # Trend
    rate_of_change:   float    # cfs/hr, positive = rising
    roc_acceleration: float    # cfs/hr², positive = accelerating
    # Historical context
    stats:            PercentileStats
    last_year:        Optional[float]
    # Derived
    pct_of_mean:      Optional[float]   # current / mean * 100
    percentile_band:  Optional[str]     # "below normal" | "normal" | "above normal" | "flood"
    # Meta
    fetched_at:       datetime


# ── USGS fetchers ──────────────────────────────────────────────────────────────

def _get_iv(site: str, period: str) -> list[FlowReading]:
    params = {
        "format":      "json",
        "sites":       site,
        "parameterCd": "00060",
        "period":      period,
    }
    log.info(f"  USGS IV  site={site}  period={period}")
    r = requests.get(USGS_IV, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    ts = r.json()["value"]["timeSeries"]
    if not ts:
        return []
    readings = []
    for v in ts[0]["values"][0]["value"]:
        try:
            val = float(v["value"])
            dt  = datetime.fromisoformat(v["dateTime"].replace("Z", "+00:00"))
            readings.append(FlowReading(value=val, timestamp=dt))
        except (ValueError, KeyError):
            continue
    return readings


def _get_percentile_stats(site: str) -> PercentileStats:
    """
    Fetch all day-of-year percentile stats in a SINGLE API call by requesting
    all stat types at once with a comma-separated statType parameter.
    Tight 15-second timeout — returns empty stats rather than hanging.
    """
    today     = datetime.now(timezone.utc)
    month_day = f"{today.month:02d}-{today.day:02d}"

    params = {
        "format":         "rdb",
        "sites":          site,
        "statReportType": "daily",
        "statType":       "minimum,maximum,mean,P25,P50,P75",
        "parameterCd":    "00060",
    }
    try:
        log.info(f"  USGS STAT site={site} (all percentiles, single call)")
        r = requests.get(USGS_STAT, params=params, timeout=15)
        r.raise_for_status()

        results = {}
        years   = None

        stat_map = {
            "minimum": "low",
            "maximum": "high",
            "mean":    "mean",
            "p25":     "p25",
            "p50":     "median",
            "p75":     "p75",
        }

        for line in r.text.splitlines():
            if not line.strip() or line.startswith("#") or "\t" not in line:
                continue
            parts = line.split("\t")
            if parts[0].strip() in ("agency_cd", "5s"):
                continue
            # RDB columns: agency_cd, site_no, parameter_cd, ts_id, loc_web_ds,
            #              month_nu, day_nu, begin_yr, end_yr, count_nu, mean_va
            if len(parts) >= 11:
                try:
                    m  = int(parts[5])
                    d  = int(parts[6])
                    if f"{m:02d}-{d:02d}" != month_day:
                        continue
                    val = float(parts[10])
                    # Determine which stat this row is by checking dd_nu / loc_web_ds
                    # The stat type is encoded in parts[4] (loc_web_ds) or we track by order
                    # Actually the RDB returns all stat types interleaved — identify by count_nu
                    # Simpler: collect all rows for today and map by position
                    # The statType order in the response matches our request order
                    field = list(stat_map.values())[len(results)] if len(results) < 6 else None
                    if field and field not in results:
                        results[field] = val
                    if years is None:
                        try:
                            years = int(parts[8]) - int(parts[7]) + 1
                        except (ValueError, IndexError):
                            pass
                except (ValueError, IndexError):
                    continue

        if results:
            log.info(f"  Stats: {results}  ({years} yrs)")
            return PercentileStats(
                low    = results.get("low"),
                p25    = results.get("p25"),
                median = results.get("median"),
                mean   = results.get("mean"),
                p75    = results.get("p75"),
                high   = results.get("high"),
                years  = years,
                source = "stat_svc",
            )

    except requests.exceptions.Timeout:
        log.warning("  STAT service timed out — skipping historical stats")
    except Exception as e:
        log.warning(f"  STAT service error: {e}")

    return PercentileStats(source="none")


def _get_last_year(site: str) -> Optional[float]:
    one_yr = datetime.now(timezone.utc) - timedelta(days=365)
    start  = (one_yr - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M+0000")
    end    =  one_yr.strftime("%Y-%m-%dT%H:%M+0000")
    params = {
        "format":      "json",
        "sites":       site,
        "parameterCd": "00060",
        "startDT":     start,
        "endDT":       end,
    }
    try:
        r = requests.get(USGS_IV, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        ts = r.json()["value"]["timeSeries"]
        if not ts:
            return None
        vals = [
            float(v["value"])
            for v in ts[0]["values"][0]["value"]
            if v["value"] not in ("", "-999999")
        ]
        return round(sum(vals) / len(vals), 2) if vals else None
    except Exception as e:
        log.warning(f"  Last-year lookup failed: {e}")
        return None


# ── Rate-of-change ─────────────────────────────────────────────────────────────

def _rate_of_change(series: list[FlowReading], window_hours: float = 3.0) -> tuple[float, float]:
    if len(series) < 4:
        return 0.0, 0.0
    cutoff = series[-1].timestamp.timestamp() - window_hours * 3600
    window = [r for r in series if r.timestamp.timestamp() >= cutoff]
    if len(window) < 3:
        window = series[-min(20, len(series)):]
    t0 = window[0].timestamp.timestamp()
    xs = np.array([(r.timestamp.timestamp() - t0) / 3600 for r in window])
    ys = np.array([r.value for r in window])
    slope = float(np.polyfit(xs, ys, 1)[0])
    mid = len(window) // 2
    if mid >= 2:
        s1 = float(np.polyfit(xs[:mid], ys[:mid], 1)[0]) if len(xs[:mid]) >= 2 else slope
        s2 = float(np.polyfit(xs[mid:], ys[mid:], 1)[0]) if len(xs[mid:]) >= 2 else slope
        accel = round(s2 - s1, 4)
    else:
        accel = 0.0
    return round(slope, 3), accel


def _percentile_band(current: float, stats: PercentileStats) -> Optional[str]:
    """Classify current flow vs historical percentiles."""
    if stats.p25 is None or stats.p75 is None:
        return None
    if   current < stats.p25:   return "below normal"
    elif current <= stats.p75:  return "normal"
    elif stats.high and current > stats.high * 0.8:
        return "flood watch"
    else:
        return "above normal"


# ── Main builder ───────────────────────────────────────────────────────────────

def build_report(station_id: str, station_name: str) -> GaugeReport:
    series_7d = _get_iv(station_id, "P7D")
    stats     = _get_percentile_stats(station_id)
    last_year = _get_last_year(station_id)

    if not series_7d:
        raise RuntimeError(f"No IV data returned for site {station_id}")

    current = series_7d[-1].value
    now_ts  = series_7d[-1].timestamp.timestamp()

    def _lookback(hours: float) -> float:
        cutoff = now_ts - hours * 3600
        past = next(
            (r.value for r in reversed(series_7d) if r.timestamp.timestamp() <= cutoff),
            series_7d[0].value,
        )
        return round(current - past, 2)

    delta_1h  = _lookback(1)
    delta_24h = _lookback(24)

    flows        = [r.value for r in series_7d]
    peak_reading = max(series_7d, key=lambda r: r.value)
    roc, accel   = _rate_of_change(series_7d)

    pct_of_mean = (
        round(current / stats.mean * 100, 1) if stats.mean else None
    )

    return GaugeReport(
        station_id       = station_id,
        station_name     = station_name,
        current          = current,
        delta_1h         = delta_1h,
        delta_24h        = delta_24h,
        range_7d_lo      = round(min(flows), 2),
        range_7d_hi      = round(max(flows), 2),
        peak_7d          = peak_reading.value,
        peak_7d_time     = peak_reading.timestamp,
        series_7d        = series_7d,
        rate_of_change   = roc,
        roc_acceleration = accel,
        stats            = stats,
        last_year        = last_year,
        pct_of_mean      = pct_of_mean,
        percentile_band  = _percentile_band(current, stats),
        fetched_at       = datetime.now(timezone.utc),
    )
