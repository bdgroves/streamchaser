"""
chart.py — Streamchaser gauge chart.

Feed-optimized portrait format: 1080x1350 (4:5 ratio, Instagram/Bluesky native).
Bold type, high contrast, readable at thumbnail size.
"""

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot    as plt
import matplotlib.patches   as mpatches
import matplotlib.dates     as mdates
import numpy                as np
from matplotlib.gridspec   import GridSpec
from matplotlib.ticker     import MaxNLocator
from matplotlib.patches    import FancyBboxPatch

OUTPUT_DIR = Path(os.getenv("CHART_OUTPUT_DIR", "/tmp"))

# ── Palette ────────────────────────────────────────────────────────────────────
P = {
    "bg":            "#0D1B2A",   # deep navy — dark card background
    "bg_panel":      "#122030",   # slightly lighter panel
    "bg_chart":      "#0F1E2E",   # chart area
    "rule":          "#1E3A50",   # subtle grid lines
    "rule_lt":       "#162C40",
    "ink":           "#F0EBE0",   # warm white for primary text
    "ink_mid":       "#C8BFB0",
    "ink_light":     "#8A8070",
    "ink_ghost":     "#4A4438",
    "water":         "#4AA8E0",   # sky blue — main flow line
    "water_fill":    "#1A3C55",   # fill under curve
    "water_mid":     "#2E6890",
    "peak_amber":    "#F0A030",   # amber for peaks
    "peak_lt":       "#3A2A10",
    "pct_normal":    "#1A4020",   # green band (normal range)
    "pct_low":       "#2A1A10",   # brown-red band (below normal)
    "pct_high":      "#102030",   # blue band (above normal)
    "rising":        "#E06030",   # orange-red for rising
    "falling":       "#4AA8E0",   # blue for falling
    "stable":        "#60A060",   # green for stable
    "accent":        "#4AA8E0",
    "usgs":          "#6ABCF0",
}

FONTS = ["Liberation Sans", "Helvetica Neue", "Helvetica", "DejaVu Sans", "Arial"]
plt.rcParams.update({
    "font.family":     "sans-serif",
    "font.sans-serif": FONTS,
})


# ── Helpers ────────────────────────────────────────────────────────────────────

def _tc(delta: float) -> str:
    if delta >  0.1: return P["rising"]
    if delta < -0.1: return P["falling"]
    return P["stable"]

def _trend_arrow(delta: float) -> str:
    if delta >  0.05: return "↑"
    if delta < -0.05: return "↓"
    return "→"

def _roc_word(roc: float) -> str:
    if   roc >  2.0:  return "RISING FAST ▲"
    elif roc >  0.05: return "RISING"
    elif roc < -2.0:  return "FALLING FAST ▼"
    elif roc < -0.05: return "FALLING"
    return "STEADY"

def _smooth(values, k=5):
    if len(values) <= k:
        return np.array(values)
    kernel = np.ones(k) / k
    s = np.convolve(values, kernel, mode="same")
    s[:k//2]  = values[:k//2]
    s[-k//2:] = values[-k//2:]
    return s

def _band_label(band: Optional[str]) -> str:
    return {
        "below normal": "BELOW NORMAL",
        "normal":       "NORMAL",
        "above normal": "ABOVE NORMAL",
        "flood watch":  "FLOOD WATCH",
    }.get(band or "", "—")

def _band_color(band: Optional[str]) -> str:
    return {
        "below normal": P["peak_amber"],
        "normal":       P["stable"],
        "above normal": P["water"],
        "flood watch":  P["rising"],
    }.get(band or "", P["ink_light"])


# ── Main entry ────────────────────────────────────────────────────────────────

def generate_chart(report, station_url: str = "") -> str:
    # 1080x1350 @ 108dpi = 10x12.5 inches — native 4:5 portrait
    fig = plt.figure(figsize=(10, 12.5), dpi=108, facecolor=P["bg"])

    gs = GridSpec(
        5, 1,
        figure        = fig,
        height_ratios = [0.14, 0.10, 0.46, 0.22, 0.08],
        hspace        = 0,
        left=0.06, right=0.94, top=0.97, bottom=0.03,
    )

    ax_hdr    = fig.add_subplot(gs[0])
    ax_hero   = fig.add_subplot(gs[1])
    ax_chart  = fig.add_subplot(gs[2])
    ax_stats  = fig.add_subplot(gs[3])
    ax_foot   = fig.add_subplot(gs[4])

    for ax in (ax_hdr, ax_hero, ax_stats, ax_foot):
        ax.set_axis_off()
    ax_chart.set_facecolor(P["bg_chart"])

    _header(ax_hdr, report)
    _hero  (ax_hero, report)
    _chart (ax_chart, report)
    _stats (ax_stats, report)
    _footer(ax_foot, report, station_url)

    # Outer border
    fig.add_artist(plt.Rectangle(
        (0.008, 0.008), 0.984, 0.984,
        fill=False, edgecolor=P["rule"], linewidth=1.2,
        transform=fig.transFigure, zorder=10,
    ))
    # Divider below header
    fig.add_artist(plt.Line2D(
        [0.06, 0.94], [0.835, 0.835],
        color=P["rule"], linewidth=0.8,
        transform=fig.transFigure, zorder=10,
    ))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    out   = OUTPUT_DIR / f"streamchaser_{report.station_id}_{stamp}.png"
    fig.savefig(str(out), dpi=108, bbox_inches="tight", facecolor=P["bg"])
    plt.close(fig)
    return str(out)


# ── Sections ──────────────────────────────────────────────────────────────────

def _header(ax, report):
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    tc = _tc(report.delta_1h)

    # Station name — bold, large
    name = report.station_name.upper()
    ax.text(0.0, 0.72, name,
            ha="left", va="center", transform=ax.transAxes,
            fontsize=16, fontweight="bold", color=P["ink"], zorder=4)
    ax.text(0.0, 0.18, f"USGS {report.station_id}  ·  REAL-TIME STREAMFLOW",
            ha="left", va="center", transform=ax.transAxes,
            fontsize=7, color=P["usgs"], zorder=4,
            fontweight="bold", alpha=0.85)

    # Timestamp top right
    ts = report.fetched_at.strftime("%-m/%-d  %H:%M UTC")
    ax.text(1.0, 0.72, ts,
            ha="right", va="center", transform=ax.transAxes,
            fontsize=7.5, color=P["ink_light"], zorder=4)

    # Wave mark
    ax.text(1.0, 0.18, "~",
            ha="right", va="center", transform=ax.transAxes,
            fontsize=11, color=P["water"], alpha=0.5, zorder=4)


def _hero(ax, report):
    """Big current flow number — the scroll-stopper."""
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    tc    = _tc(report.delta_1h)
    arrow = _trend_arrow(report.delta_1h)
    roc   = _roc_word(report.rate_of_change)

    # Giant flow number
    ax.text(0.0, 0.60, f"{report.current:.1f}",
            ha="left", va="center", transform=ax.transAxes,
            fontsize=52, fontweight="bold", color=tc, zorder=4,
            linespacing=0.9)
    ax.text(0.0, 0.08, "CFS",
            ha="left", va="center", transform=ax.transAxes,
            fontsize=10, fontweight="bold", color=P["ink_mid"], zorder=4)

    # Trend arrow + roc
    ax.text(0.38, 0.60, arrow,
            ha="left", va="center", transform=ax.transAxes,
            fontsize=36, color=tc, zorder=4)
    ax.text(0.38, 0.08, roc,
            ha="left", va="center", transform=ax.transAxes,
            fontsize=9, fontweight="bold", color=tc, zorder=4)

    # Delta pills
    d1c  = _tc(report.delta_1h)
    d24c = _tc(report.delta_24h)
    ax.text(0.72, 0.68, f"Δ 1h  {report.delta_1h:+.1f}",
            ha="left", va="center", transform=ax.transAxes,
            fontsize=9, color=d1c, fontweight="bold", zorder=4)
    ax.text(0.72, 0.28, f"Δ 24h  {report.delta_24h:+.1f}",
            ha="left", va="center", transform=ax.transAxes,
            fontsize=9, color=d24c, fontweight="bold", zorder=4)

    # Percentile status badge
    band  = _band_label(report.percentile_band)
    bandc = _band_color(report.percentile_band)
    ax.add_patch(FancyBboxPatch(
        (0.72, 0.38), 0.27, 0.22,
        boxstyle="round,pad=0.01",
        facecolor=bandc, edgecolor="none", alpha=0.18,
        transform=ax.transAxes, zorder=3,
    ))
    ax.text(0.855, 0.50, band,
            ha="center", va="center", transform=ax.transAxes,
            fontsize=7.5, fontweight="bold", color=bandc, zorder=4)


def _chart(ax, report):
    series = report.series_7d
    if not series:
        ax.text(0.5, 0.5, "NO DATA", ha="center", va="center",
                transform=ax.transAxes, color=P["ink_light"])
        return

    dates   = [r.timestamp for r in series]
    flows   = [r.value     for r in series]
    flows_s = _smooth(np.array(flows))
    s       = report.stats

    lo, hi = report.range_7d_lo, report.range_7d_hi
    span   = max(hi - lo, 1.0)

    ctx  = [v for v in [s.low, s.p25, s.median, s.mean, report.last_year]
            if v is not None]
    y_lo = max(0, min(lo, min(ctx) if ctx else lo) - span * 0.08)
    p75_cap = s.p75 if (s.p75 is not None and s.p75 < hi * 3) else hi * 1.5
    y_hi    = max(hi, p75_cap) + span * 0.30
    p_span  = y_hi - y_lo

    # Percentile band fills
    if s.p25 is not None and s.p75 is not None:
        ax.axhspan(max(y_lo, s.p25), min(y_hi, s.p75),
                   facecolor=P["pct_normal"], alpha=0.35, zorder=0)
    if s.low is not None and s.p25 is not None:
        ax.axhspan(max(y_lo, s.low), min(y_hi, s.p25),
                   facecolor=P["pct_low"], alpha=0.30, zorder=0)
    if s.p75 is not None and s.high is not None:
        ax.axhspan(max(y_lo, s.p75), min(y_hi, s.high),
                   facecolor=P["pct_high"], alpha=0.30, zorder=0)

    # Reference lines
    for val, lbl, color, alpha, dash in [
        (s.median, "median", P["stable"],    0.55, (4, 4)),
        (s.mean,   "mean",   P["usgs"],      0.45, (3, 6)),
        (s.p25,    "p25",    P["ink_ghost"], 0.40, (2, 6)),
        (s.p75,    "p75",    P["ink_ghost"], 0.40, (2, 6)),
    ]:
        if val is None or not (y_lo < val < y_hi):
            continue
        ax.axhline(val, color=color, linewidth=0.8,
                   linestyle=(0, dash), alpha=alpha, zorder=2)
        ax.text(dates[int(len(dates) * 0.01)], val + p_span * 0.015,
                f"{lbl}  {val:.1f}",
                fontsize=6.5, color=color, va="bottom",
                alpha=min(1.0, alpha + 0.2), zorder=5)

    ax.yaxis.grid(True, color=P["rule"], linewidth=0.4,
                  linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)

    # Fill under curve — two layers for depth
    ax.fill_between(dates, flows_s, y_lo,
                    color=P["water_fill"], alpha=0.80, zorder=1)
    ax.fill_between(dates, flows_s, y_lo,
                    color=_tc(report.delta_1h), alpha=0.08, zorder=1)

    # Last year reference line
    if report.last_year and y_lo < report.last_year < y_hi:
        ax.axhline(report.last_year, color=P["ink_ghost"], linewidth=1.0,
                   linestyle=(0, (5, 4)), alpha=0.55, zorder=2)
        ax.text(dates[int(len(dates) * 0.60)],
                report.last_year + p_span * 0.018,
                f"last year  {report.last_year:.1f}",
                fontsize=6.5, color=P["ink_ghost"], va="bottom", zorder=5)

    # Main flow line
    ax.plot(dates, flows_s,
            color=P["water"], linewidth=2.5,
            solid_capstyle="round", zorder=4)

    # Peak annotation
    if report.peak_7d_time:
        pv, pt = report.peak_7d, report.peak_7d_time
        ax.scatter([pt], [pv], s=70,
                   color=P["peak_amber"], edgecolors=P["bg"],
                   linewidths=1.8, zorder=7)
        ha  = "right" if pt > dates[len(dates) // 2] else "left"
        off = (-8, 12) if ha == "right" else (8, 12)
        ax.annotate(
            f"Peak  {pv:.1f}\n{pt.strftime('%-m/%-d  %H:%Mz')}",
            xy=(pt, pv), xytext=off, textcoords="offset points",
            ha=ha, va="bottom", fontsize=7, color=P["peak_amber"],
            arrowprops=dict(arrowstyle="-", color=P["peak_amber"], lw=0.8),
            zorder=8,
        )

    # Current dot — glowing effect with two scatter layers
    ax.scatter([dates[-1]], [flows[-1]], s=120,
               color=_tc(report.delta_1h), alpha=0.25,
               edgecolors="none", zorder=7)
    ax.scatter([dates[-1]], [flows[-1]], s=45,
               color=_tc(report.delta_1h), edgecolors=P["bg"],
               linewidths=1.8, zorder=8)

    # Axes styling
    ax.set_xlim(dates[0], dates[-1])
    ax.set_ylim(y_lo, y_hi)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-m/%-d"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    ax.yaxis.set_major_locator(MaxNLocator(integer=False, nbins=5))
    ax.tick_params(axis="x", colors=P["ink_light"], labelsize=8, length=0, pad=5)
    ax.tick_params(axis="y", colors=P["ink_light"], labelsize=8, length=0, pad=4)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_facecolor(P["bg_chart"])

    ax.text(-0.04, 0.5, "cfs", ha="center", va="center",
            transform=ax.transAxes, fontsize=7.5,
            color=P["ink_light"], rotation=90)
    ax.text(0.01, 0.97, "7-DAY FLOW RECORD",
            transform=ax.transAxes, fontsize=7,
            color=P["ink_light"], fontweight="bold", va="top")


def _stats(ax, report):
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    s      = report.stats
    pct    = f"{report.pct_of_mean:.0f}%" if report.pct_of_mean else "N/A"
    med    = f"{s.median:.1f}" if s.median else "N/A"
    yrs    = f"{s.years} yr record" if s.years else ""
    peak_t = report.peak_7d_time.strftime("%-m/%-d %H:%Mz") if report.peak_7d_time else "—"

    tiles = [
        {
            "label": "CURRENT",
            "value": f"{report.current:.1f}",
            "unit":  "cfs",
            "sub":   f"Δ1h {report.delta_1h:+.1f}  ·  Δ24h {report.delta_24h:+.1f}",
            "color": _tc(report.delta_1h),
        },
        {
            "label": "7-DAY PEAK",
            "value": f"{report.peak_7d:.1f}",
            "unit":  "cfs",
            "sub":   peak_t,
            "color": P["peak_amber"],
        },
        {
            "label": "MEDIAN",
            "value": med,
            "unit":  "cfs",
            "sub":   yrs,
            "color": P["stable"],
        },
        {
            "label": "VS MEAN",
            "value": pct,
            "unit":  "of avg",
            "sub":   f"mean {s.mean:.0f} cfs" if s.mean else "N/A",
            "color": P["usgs"],
        },
    ]

    n = len(tiles)
    tile_w = 1.0 / n

    for i, t in enumerate(tiles):
        x0 = i * tile_w
        xc = x0 + tile_w / 2
        pad = 0.008

        ax.add_patch(FancyBboxPatch(
            (x0 + pad, 0.08), tile_w - pad * 2, 0.84,
            boxstyle="round,pad=0.008",
            facecolor=P["bg_panel"], edgecolor=P["rule"], linewidth=0.5,
            transform=ax.transAxes,
        ))
        # Color bar top
        ax.add_patch(mpatches.Rectangle(
            (x0 + pad, 0.88), tile_w - pad * 2, 0.055,
            facecolor=t["color"], edgecolor="none", alpha=0.70,
            transform=ax.transAxes,
        ))

        ax.text(xc, 0.76, t["label"],
                ha="center", va="center", transform=ax.transAxes,
                fontsize=6.5, color=P["ink_light"], fontweight="bold")
        ax.text(xc, 0.50, t["value"],
                ha="center", va="center", transform=ax.transAxes,
                fontsize=15, fontweight="bold", color=t["color"])
        ax.text(xc, 0.28, t["unit"],
                ha="center", va="center", transform=ax.transAxes,
                fontsize=7, color=P["ink_mid"])
        ax.text(xc, 0.12, t["sub"],
                ha="center", va="center", transform=ax.transAxes,
                fontsize=6, color=P["ink_light"], style="italic")


def _footer(ax, report, station_url):
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.text(0.0, 0.60,
            f"USGS National Water Information System  ·  {report.station_id}",
            ha="left", va="center", transform=ax.transAxes,
            fontsize=6.5, color=P["usgs"], alpha=0.80)
    ax.text(0.0, 0.15,
            "Operated in cooperation with Turlock Irrigation District",
            ha="left", va="center", transform=ax.transAxes,
            fontsize=5.8, color=P["ink_ghost"])
    ax.text(1.0, 0.60, "streamchaser",
            ha="right", va="center", transform=ax.transAxes,
            fontsize=6.5, color=P["ink_ghost"], style="italic")


# ── Standalone preview ────────────────────────────────────────────────────────

if __name__ == "__main__":
    from dataclasses import dataclass
    import math, random

    @dataclass
    class FR:
        value: float; timestamp: datetime

    @dataclass
    class PS:
        low: float; p25: float; median: float; mean: float
        p75: float; high: float; years: int; source: str

    @dataclass
    class GR:
        station_id: str; station_name: str; current: float
        delta_1h: float; delta_24h: float
        range_7d_lo: float; range_7d_hi: float
        peak_7d: float; peak_7d_time: object
        series_7d: list; rate_of_change: float; roc_acceleration: float
        stats: object; last_year: object
        pct_of_mean: object; percentile_band: str
        fetched_at: datetime

    now = datetime.now(timezone.utc)
    rng = []
    for i in range(7 * 24):
        t = now - timedelta(hours=(7 * 24 - i))
        v = 12 + 36 * math.exp(-((i - 55) ** 2) / (2 * 28 ** 2)) + random.uniform(-0.3, 0.3)
        rng.append(FR(value=round(max(0.1, v), 2), timestamp=t))

    peak = max(rng, key=lambda r: r.value)
    mock_stats = PS(low=0.03, p25=2.888, median=9.4,
                    mean=30.637, p75=37.875, high=353.0,
                    years=56, source="stat_svc")
    mock = GR(
        station_id="11284400", station_name="Big Creek @ Whites Gulch",
        current=6.32, delta_1h=-0.12, delta_24h=-0.58,
        range_7d_lo=6.32, range_7d_hi=48.3,
        peak_7d=peak.value, peak_7d_time=peak.timestamp,
        series_7d=rng, rate_of_change=-0.18, roc_acceleration=-0.05,
        stats=mock_stats, last_year=5.70,
        pct_of_mean=round(6.32 / 30.637 * 100, 1),
        percentile_band="normal",
        fetched_at=now,
    )

    path = generate_chart(
        mock,
        station_url="https://waterdata.usgs.gov/monitoring-location/11284400/",
    )
    print(f"Chart: {path}")
