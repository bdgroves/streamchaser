# streamchaser

> *You don't chase the water. You read it.*

Big Creek runs through the hills above Groveland, California — my hometown. It drains the western slope of the Sierra Nevada, feeds Don Pedro Reservoir, and in a wet year it moves. In a dry year it barely whispers. After a storm rolls through, it can go from 6 cfs to 300 cfs in a matter of hours.

This bot watches it so I don't have to.

---

## Latest reading

![Latest chart](chart/latest.png)

*Updated every 6 hours by GitHub Actions. [Live USGS page →](https://waterdata.usgs.gov/monitoring-location/11284400/)*

---

## Why this gauge

**USGS 11284400 — Big C AB Whites Gulch NR Groveland CA**

Big Creek is the kind of creek that doesn't make the news until it does. It's the creek that runs behind the properties off Ferretti Road, the one that crosses under the highway on the way into town, the one that tells you whether the hills are saturated or bone dry. When the Sierra gets hit by an atmospheric river, Big Creek is where you watch the pulse arrive first.

The gauge has been running since 1969. Fifty-six years of record. Every storm, every drought, every fire year, every flood — it's all in there. The bot plots where today sits against all of it.

Operated in cooperation with [Turlock Irrigation District](https://www.tid.org/), which manages Don Pedro downstream. They care about this number too.

---

## What the chart shows

- **Current flow** in cubic feet per second, with trend direction
- **7-day record** — the full hydrograph with annotated peak
- **Percentile bands** — green band is the normal range (p25–p75) based on 56 years of same-date data
- **Percentile needle** (right edge) — exactly where today's flow falls in the full historical distribution
- **Rate of change** — accelerating, holding, or dropping off
- **vs. long-term mean** — how this day compares to every same-date reading on record

---

## Repo layout

```
streamchaser/
├── .github/workflows/
│   └── chase.yml               # runs every 6 hours
├── chart/
│   └── latest.png              # updated by the bot on every run
├── src/streamchaser/
│   ├── __main__.py             # orchestration + post text
│   ├── gauge.py                # USGS API + stat computation
│   ├── chart.py                # matplotlib chart generation
│   ├── chart_preview.py        # local test render
│   └── poster.py               # Twitter/X + Bluesky
└── README.md
```

---

## Setup for another gauge

1. Fork the repo
2. Edit the three env vars in `chase.yml`:

```yaml
env:
  USGS_STATION_ID:   "11284400"
  USGS_STATION_NAME: "Big Creek @ Whites Gulch"
  USGS_HASHTAGS:     "#USGS #BigCreek #Groveland"
```

3. Add 6 GitHub secrets (Settings → Secrets → Actions):

| Secret | What |
|---|---|
| `TWITTER_API_KEY` | Consumer Key — developer.x.com |
| `TWITTER_API_SECRET` | Consumer Secret |
| `TWITTER_ACCESS_TOKEN` | Access Token (needs Read+Write) |
| `TWITTER_ACCESS_SECRET` | Access Token Secret |
| `BLUESKY_HANDLE` | e.g. `yourname.bsky.social` |
| `BLUESKY_APP_PASSWORD` | bsky.app → Settings → App Passwords |

4. Run workflow manually once to verify, then let the cron take over.

---

## Adjust post frequency

```yaml
- cron: '0 */6 * * *'    # every 6 hours (default)
- cron: '0 15 * * *'     # once daily at 15:00 UTC
- cron: '0 */3 * * *'    # every 3 hours during storm season
```

---

## Data source

USGS National Water Information System — public API, no key required.

- Instantaneous values: `waterservices.usgs.gov/nwis/iv/`
- Historical statistics: `waterservices.usgs.gov/nwis/stat/`
- Parameter `00060` = Discharge, cubic feet per second

---

## License

MIT. Watch your own creek.
