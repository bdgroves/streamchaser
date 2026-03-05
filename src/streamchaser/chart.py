"""
chart.py — Streamchaser gauge chart.

Aesthetic: field-data clean. Warm parchment, ink type, water blue.
No badge. A small muted wave mark in the header corner.
The main chart carries a percentile band overlay showing where today's
flow sits within the 56-year record (low / p25 / median / p75 / high).
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
    "parchment":     "#F4EFE4",
    "parchment_dk":  "#EAE3D2",
    "panel":         "#EDE6D5",
    "ink":           "#1A1712",
    "ink_mid":       "#3D3628",
    "ink_light":     "#7A6E5F",
    "ink_ghost":     "#B0A898",
    "usgs_blue":     "#1A558A",
    "usgs_blue_lt":  "#D6E8F5",
    "water":         "#3E7DB5",
    "water_mid":     "#6AAFD6",
    "water_fill":    "#C8DFF0",
    "water_fill_dk": "#A8C8E8",
    "peak_amber":    "#B85A18",
    "peak_lt":       "#F5E8DC",
    "rule":          "#CEC4B0",
    "rule_lt":       "#E4DDD0",
    "pct_low":       "#E8D8C8",
    "pct_normal":    "#D8EAD8",
    "pct_high":      "#D8E4F0",
    "rising":        "#B04A18",
    "falling":       "#1A558A",
    "stable":        "#5A6248",
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

def _trend_word(delta: float) -> str:
    if delta >  0.05: return "RISING"
    if delta < -0.05: return "FALLING"
    return "STABLE"

def _roc_word(roc: float, accel: float) -> str:
    if   roc >  0.5 and accel >  0.1: return "ACCELERATING ▲"
    elif roc >  0.05:                  return "RISING SLOWLY"
    elif roc < -0.5 and accel < -0.1:  return "DECELERATING ▼"
    elif roc < -0.05:                  return "FALLING SLOWLY"
    return "HOLDING STEADY"

def _smooth(values, k=7):
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
        "normal":       "NORMAL RANGE",
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


# ── Water drop icon ───────────────────────────────────────────────────────────

def _draw_waterdrop(fig, ax_header, cx_frac: float, cy_frac: float,
                    r_inch: float = 0.22, color: str = P["water"]):
    """
    Water drop drawn in figure-inch space so the circle is truly round.
    cx_frac, cy_frac — position in axes-fraction of ax_header
    r_inch           — radius of circular base in inches
    """
    import matplotlib.transforms as T

    # Convert axes-fraction → figure-fraction → figure-inch
    # ax_header bbox in figure fraction
    bbox   = ax_header.get_position()   # Bbox in figure fraction
    fig_w, fig_h = fig.get_size_inches()

    # Center in figure inches
    cx_in = (bbox.x0 + cx_frac * bbox.width)  * fig_w
    cy_in = (bbox.y0 + cy_frac * bbox.height) * fig_h

    # Build drop shape in inches
    n      = 200
    theta  = np.linspace(0, 2 * np.pi, n)
    bx     = cx_in + r_inch * np.cos(theta)
    by     = (cy_in - r_inch * 0.10) + r_inch * np.sin(theta)

    tip_x  = cx_in
    tip_y  = cy_in + r_inch * 1.90

    # Clip the top of the circle and join to tip
    cutoff = cy_in - r_inch * 0.10 + r_inch * 0.62
    mask   = by <= cutoff
    bx_bot = bx[mask]
    by_bot = by[mask]

    # Sort bottom arc by angle for clean polygon
    angles  = np.arctan2(by_bot - (cy_in - r_inch*0.10), bx_bot - cx_in)
    order   = np.argsort(angles)
    bx_bot  = bx_bot[order]
    by_bot  = by_bot[order]

    pts_in  = list(zip(bx_bot, by_bot)) + [(tip_x, tip_y)]

    # Convert inches → figure fraction
    pts_ff = [(x / fig_w, y / fig_h) for x, y in pts_in]

    fig.add_artist(mpatches.Polygon(
        pts_ff, closed=True,
        facecolor=color, edgecolor="none", alpha=0.88,
        transform=fig.transFigure, zorder=20,
    ))

    # Highlight
    hx = (cx_in - r_inch * 0.26) / fig_w
    hy = (cy_in + r_inch * 0.26) / fig_h
    fig.add_artist(mpatches.Ellipse(
        (hx, hy), r_inch * 0.30 / fig_w, r_inch * 0.18 / fig_h,
        angle=35, facecolor="white", edgecolor="none", alpha=0.48,
        transform=fig.transFigure, zorder=21,
    ))


# ── Percentile needle (right-edge gauge) ──────────────────────────────────────

def _draw_percentile_needle(ax, report):
    s = report.stats
    if s.low is None or s.high is None or s.p25 is None:
        return

    bar_x  = 0.972
    bar_w  = 0.011
    bar_lo = 0.08
    bar_hi = 0.90
    bar_h  = bar_hi - bar_lo

    lo, hi = s.low, s.high
    span   = max(hi - lo, 0.01)

    def frac(v):
        return max(0.0, min(1.0, (v - lo) / span))

    # Track background
    ax.add_patch(FancyBboxPatch(
        (bar_x - bar_w / 2, bar_lo), bar_w, bar_h,
        boxstyle="round,pad=0.002",
        facecolor=P["rule_lt"], edgecolor=P["rule"], linewidth=0.4,
        transform=ax.transAxes, zorder=6, clip_on=False,
    ))

    # Band fills
    for blo, bhi, bc in [
        (s.low,  s.p25,  P["pct_low"]),
        (s.p25,  s.p75,  P["pct_normal"]),
        (s.p75,  s.high, P["pct_high"]),
    ]:
        if blo is None or bhi is None:
            continue
        f_lo = bar_lo + frac(blo) * bar_h
        f_hi = bar_lo + frac(bhi) * bar_h
        ax.add_patch(mpatches.Rectangle(
            (bar_x - bar_w / 2, f_lo), bar_w, f_hi - f_lo,
            facecolor=bc, edgecolor="none",
            transform=ax.transAxes, zorder=7, clip_on=False,
        ))

    # Tick marks
    for val, lbl in [(s.median, "med"), (s.p25, "p25"), (s.p75, "p75")]:
        if val is None:
            continue
        fy = bar_lo + frac(val) * bar_h
        ax.plot(
            [bar_x - bar_w / 2 - 0.003, bar_x + bar_w / 2 + 0.003],
            [fy, fy],
            color=P["ink_light"], linewidth=0.6,
            transform=ax.transAxes, zorder=8, clip_on=False,
        )
        ax.text(
            bar_x + bar_w / 2 + 0.006, fy, lbl,
            ha="left", va="center", fontsize=4.2,
            color=P["ink_light"], transform=ax.transAxes, zorder=8, clip_on=False,
        )

    # Current value indicator
    fy_now = bar_lo + frac(report.current) * bar_h
    nc     = _tc(report.delta_1h)
    ax.plot(
        [bar_x - bar_w / 2 - 0.007, bar_x + bar_w / 2 + 0.007],
        [fy_now, fy_now],
        color=nc, linewidth=1.8, solid_capstyle="round",
        transform=ax.transAxes, zorder=9, clip_on=False,
    )
    ax.scatter(
        [bar_x], [fy_now], s=20,
        color=nc, edgecolors=P["parchment"], linewidths=0.8,
        transform=ax.transAxes, zorder=10, clip_on=False,
    )

    ax.text(bar_x, bar_hi + 0.045, "NOW",
            ha="center", va="bottom", fontsize=4,
            color=P["ink_ghost"], fontweight="bold",
            transform=ax.transAxes, zorder=8, clip_on=False)


# ── Main entry ────────────────────────────────────────────────────────────────

def generate_chart(report, station_url: str = "") -> str:
    fig = plt.figure(figsize=(12, 7), dpi=100, facecolor=P["parchment"])

    gs = GridSpec(
        4, 1,
        figure        = fig,
        height_ratios = [0.155, 0.545, 0.21, 0.09],
        hspace        = 0,
        left=0.052, right=0.952, top=0.97, bottom=0.03,
    )

    ax_hdr   = fig.add_subplot(gs[0])
    ax_chart = fig.add_subplot(gs[1])
    ax_stats = fig.add_subplot(gs[2])
    ax_foot  = fig.add_subplot(gs[3])

    for ax in (ax_hdr, ax_stats, ax_foot):
        ax.set_axis_off()
    ax_chart.set_facecolor(P["parchment"])

    _header(fig, ax_hdr, report)
    _chart (ax_chart, report)
    _stats (ax_stats, report)
    _footer(ax_foot,  report, station_url)

    fig.add_artist(plt.Rectangle(
        (0.012, 0.012), 0.976, 0.976,
        fill=False, edgecolor=P["rule"], linewidth=1.0,
        transform=fig.transFigure, zorder=10,
    ))
    fig.add_artist(plt.Line2D(
        [0.052, 0.952], [0.820, 0.820],
        color=P["rule"], linewidth=0.6,
        transform=fig.transFigure, zorder=10,
    ))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    out   = OUTPUT_DIR / f"streamchaser_{report.station_id}_{stamp}.png"
    fig.savefig(str(out), dpi=100, bbox_inches="tight", facecolor=P["parchment"])
    plt.close(fig)
    return str(out)


# ── Sections ──────────────────────────────────────────────────────────────────

def _header(fig, ax, report):
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    tc = _tc(report.delta_1h)

    # Water drop icon — drawn in figure-inch space for true proportions
    _draw_waterdrop(fig, ax, cx_frac=0.030, cy_frac=0.42, r_inch=0.21, color=P["water"])

    # Station name — nudged right to clear the drop
    ax.text(0.072, 0.74, report.station_name.upper(),
            ha="left", va="center", transform=ax.transAxes,
            fontsize=15, fontweight="bold", color=P["ink"], zorder=4)

    # Subtitle
    ax.text(0.072, 0.24, "USGS Monitoring Station  ·  Real-Time Streamflow",
            ha="left", va="center", transform=ax.transAxes,
            fontsize=7.5, color=P["usgs_blue"], zorder=4)

    # Right: current reading
    ax.text(0.980, 0.74, f"{report.current:.2f}",
            ha="right", va="center", transform=ax.transAxes,
            fontsize=23, fontweight="bold", color=tc, zorder=4)
    ax.text(0.980, 0.24, f"cfs  ·  {_trend_word(report.delta_1h)}",
            ha="right", va="center", transform=ax.transAxes,
            fontsize=8, color=P["ink_light"], zorder=4)


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

    lo, hi   = report.range_7d_lo, report.range_7d_hi
    span     = max(hi - lo, 1.0)

    # Anchor Y-axis to the 7-day data. Include median/mean in context but
    # exclude the historical flood high (353 cfs) which would crush the view.
    # p75 and high are shown on the percentile needle gauge instead.
    ctx = [v for v in [s.low, s.p25, s.median, s.mean, report.last_year]
           if v is not None]
    y_lo   = max(0, min(lo, min(ctx) if ctx else lo) - span * 0.10)
    p75_cap = s.p75 if (s.p75 is not None and s.p75 < hi * 3) else hi * 1.5
    y_hi   = max(hi, p75_cap) + span * 0.35
    p_span = y_hi - y_lo

    # Percentile band fills
    if s.p25 is not None and s.p75 is not None:
        ax.axhspan(max(y_lo, s.p25),  min(y_hi, s.p75),
                   facecolor=P["pct_normal"], alpha=0.30, zorder=0)
    if s.low is not None and s.p25 is not None:
        ax.axhspan(max(y_lo, s.low),  min(y_hi, s.p25),
                   facecolor=P["pct_low"],    alpha=0.22, zorder=0)
    if s.p75 is not None and s.high is not None:
        ax.axhspan(max(y_lo, s.p75),  min(y_hi, s.high),
                   facecolor=P["pct_high"],   alpha=0.22, zorder=0)

    # Percentile reference lines
    for val, lbl, color, alpha, dash in [
        (s.median, "median", P["stable"],    0.70, (4, 4)),
        (s.mean,   "mean",   P["usgs_blue"], 0.55, (3, 6)),
        (s.p25,    "p25",    P["ink_ghost"], 0.45, (2, 6)),
        (s.p75,    "p75",    P["ink_ghost"], 0.45, (2, 6)),
    ]:
        if val is None or not (y_lo < val < y_hi):
            continue
        ax.axhline(val, color=color, linewidth=0.8,
                   linestyle=(0, dash), alpha=alpha, zorder=2)
        ax.text(dates[int(len(dates) * 0.01)], val + p_span * 0.015,
                f"{lbl}  {val:.1f}",
                fontsize=6, color=color, va="bottom",
                alpha=min(1.0, alpha + 0.2), zorder=5)

    ax.yaxis.grid(True, color=P["rule_lt"], linewidth=0.4, linestyle="--", alpha=0.6)
    ax.set_axisbelow(True)

    # Flow fill + trend wash
    ax.fill_between(dates, flows_s, y_lo, color=P["water_fill"], alpha=0.50, zorder=1)
    ax.fill_between(dates, flows_s, y_lo,
                    color=_tc(report.rate_of_change), alpha=0.07, zorder=1)

    # Last-year reference
    if report.last_year and y_lo < report.last_year < y_hi:
        ax.axhline(report.last_year, color=P["ink_ghost"], linewidth=0.9,
                   linestyle=(0, (5, 4)), alpha=0.65, zorder=2)
        ax.text(dates[int(len(dates) * 0.60)],
                report.last_year + p_span * 0.018,
                f"last year  {report.last_year:.2f}",
                fontsize=6, color=P["ink_ghost"], va="bottom", zorder=5)

    # Main line
    ax.plot(dates, flows_s, color=_tc(report.delta_1h),
            linewidth=2.0, solid_capstyle="round", zorder=4)

    # Peak annotation
    if report.peak_7d_time:
        pv, pt = report.peak_7d, report.peak_7d_time
        ax.scatter([pt], [pv], s=55,
                   color=P["peak_amber"], edgecolors=P["parchment"],
                   linewidths=1.5, zorder=7)
        ha  = "right" if pt > dates[len(dates) // 2] else "left"
        off = (-6, 10) if ha == "right" else (6, 10)
        ax.annotate(
            f"Peak  {pv:.1f}\n{pt.strftime('%-m/%-d  %H:%Mz')}",
            xy=(pt, pv), xytext=off, textcoords="offset points",
            ha=ha, va="bottom", fontsize=6.5, color=P["peak_amber"],
            arrowprops=dict(arrowstyle="-", color=P["peak_amber"], lw=0.7),
            zorder=8,
        )

    # Current dot
    ax.scatter([dates[-1]], [flows[-1]], s=50,
               color=_tc(report.delta_1h), edgecolors=P["parchment"],
               linewidths=1.8, zorder=8)

    # Percentile needle
    _draw_percentile_needle(ax, report)

    # RoC label
    ax.text(0.880, 0.97, _roc_word(report.rate_of_change, report.roc_acceleration),
            ha="right", va="top", transform=ax.transAxes,
            fontsize=6.5, color=_tc(report.rate_of_change),
            fontweight="bold", alpha=0.85, zorder=6)

    # Axes
    ax.set_xlim(dates[0], dates[-1])
    ax.set_ylim(y_lo, y_hi)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-m/%-d"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    ax.yaxis.set_major_locator(MaxNLocator(integer=False, nbins=5))
    ax.tick_params(axis="x", colors=P["ink_light"], labelsize=7.5, length=0, pad=5)
    ax.tick_params(axis="y", colors=P["ink_light"], labelsize=7.5, length=0, pad=4)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.text(-0.030, 0.5, "cfs", ha="center", va="center",
            transform=ax.transAxes, fontsize=7, color=P["ink_light"], rotation=90)
    ax.text(0.002, 0.97, "7-DAY FLOW RECORD",
            transform=ax.transAxes, fontsize=6.5,
            color=P["ink_light"], fontweight="bold", va="top")


def _stats(ax, report):
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)

    s      = report.stats
    peak_t = report.peak_7d_time.strftime("%-m/%-d %H:%Mz") if report.peak_7d_time else "—"
    band   = _band_label(report.percentile_band)
    band_c = _band_color(report.percentile_band)
    pct    = f"{report.pct_of_mean:.0f}%" if report.pct_of_mean else "N/A"
    med    = f"{s.median:.1f}" if s.median else "N/A"
    yrs    = f"{s.years}yr record" if s.years else ""

    tiles = [
        {
            "label": "CURRENT FLOW",
            "value": f"{report.current:.2f}",
            "unit":  "cfs",
            "sub":   f"Δ 1h {report.delta_1h:+.2f}  ·  Δ 24h {report.delta_24h:+.2f}",
            "color": _tc(report.delta_1h),
        },
        {
            "label": "RATE OF CHANGE",
            "value": f"{report.rate_of_change:+.2f}",
            "unit":  "cfs / hr",
            "sub":   _roc_word(report.rate_of_change, report.roc_acceleration),
            "color": _tc(report.rate_of_change),
        },
        {
            "label": "7-DAY PEAK",
            "value": f"{report.peak_7d:.1f}",
            "unit":  "cfs",
            "sub":   peak_t,
            "color": P["peak_amber"],
        },
        {
            "label": "PERCENTILE STATUS",
            "value": band,
            "unit":  f"median {med} cfs",
            "sub":   yrs,
            "color": band_c,
            "small": True,
        },
        {
            "label": "VS LONG-TERM MEAN",
            "value": pct,
            "unit":  "of mean",
            "sub":   f"mean  {s.mean:.1f} cfs" if s.mean else "N/A",
            "color": P["usgs_blue"],
        },
    ]

    n = len(tiles)
    tile_w = 1.0 / n

    for i, t in enumerate(tiles):
        x0, xc = i * tile_w, i * tile_w + tile_w / 2
        pad = 0.007
        bg  = P["panel"] if i % 2 == 0 else P["parchment"]

        ax.add_patch(FancyBboxPatch(
            (x0 + pad, 0.06), tile_w - pad * 2, 0.88,
            boxstyle="round,pad=0.006",
            facecolor=bg, edgecolor=P["rule"], linewidth=0.4,
            transform=ax.transAxes,
        ))
        ax.add_patch(mpatches.Rectangle(
            (x0 + pad, 0.91), tile_w - pad * 2, 0.05,
            facecolor=t["color"], edgecolor="none",
            transform=ax.transAxes, alpha=0.75,
        ))
        ax.text(xc, 0.80, t["label"],
                ha="center", va="center", transform=ax.transAxes,
                fontsize=6, color=P["ink_light"], fontweight="bold")
        ax.text(xc, 0.51, t["value"],
                ha="center", va="center", transform=ax.transAxes,
                fontsize=10.5 if t.get("small") else 13,
                fontweight="bold", color=t["color"])
        ax.text(xc, 0.29, t["unit"],
                ha="center", va="center", transform=ax.transAxes,
                fontsize=6.8, color=P["ink_light"])
        ax.text(xc, 0.12, t["sub"],
                ha="center", va="center", transform=ax.transAxes,
                fontsize=5.8, color=P["ink_light"], style="italic")


def _footer(ax, report, station_url):
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ts  = report.fetched_at.strftime("%B %-d, %Y  %H:%M UTC")
    src = " †" if getattr(report.stats, "source", "") == "dv_computed" else ""

    ax.text(0.0, 0.68, f"USGS {report.station_id}  ·  {station_url}",
            ha="left", va="center", transform=ax.transAxes,
            fontsize=6.5, color=P["usgs_blue"])
    ax.text(0.0, 0.16,
            f"Data: USGS National Water Information System  ·  "
            f"Operated in cooperation with Turlock Irrigation District{src}",
            ha="left", va="center", transform=ax.transAxes,
            fontsize=5.8, color=P["ink_light"])
    ax.text(1.0, 0.68, ts,
            ha="right", va="center", transform=ax.transAxes,
            fontsize=6.5, color=P["ink_light"])


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

    # Real stats from USGS site for March 5 (56yr record)
    mock_stats = PS(
        low=0.03, p25=2.888, median=9.4,
        mean=30.637, p75=37.875, high=353.0,
        years=56, source="stat_svc",
    )

    mock = GR(
        station_id="11284400", station_name="Big Creek @ Whites Gulch",
        current=6.32, delta_1h=-0.12, delta_24h=-0.58,
        range_7d_lo=6.32, range_7d_hi=48.3,
        peak_7d=peak.value, peak_7d_time=peak.timestamp,
        series_7d=rng, rate_of_change=-0.18, roc_acceleration=-0.05,
        stats=mock_stats, last_year=5.70,
        pct_of_mean=round(6.32 / 30.637 * 100, 1),
        percentile_band="normal",   # 6.32 is between p25 2.888 and p75 37.875
        fetched_at=now,
    )

    path = generate_chart(
        mock,
        station_url="https://waterdata.usgs.gov/monitoring-location/11284400/",
    )
    print(f"Chart: {path}")
