# streamchaser

> *You don't chase the water. You read it.*

Groveland, California sits at 2,800 feet on the western slope of the Sierra Nevada, halfway between the Central Valley floor and Yosemite Valley. The Tuolumne River runs through the canyon a thousand feet below town. Big Creek drains the hills right behind the fire station. Cherry Creek drops out of the high country from the north, cold and fast, before it meets the mainstem below.

All of it flows down to Don Pedro Reservoir. All of it tells a story if you know how to read it.

This bot watches three gauges on that watershed — simultaneously, around the clock — and says nothing unless something is worth saying.

---

## Latest readings

### Big Creek @ Whites Gulch
*The hometown gauge. The one right out the back door.*

![Big Creek](chart/big_creek.png)
*[Live USGS page →](https://waterdata.usgs.gov/monitoring-location/11284400/)*

### Tuolumne River Below Early Intake
*The mainstem. The big one. When this moves, the whole canyon moves.*

![Tuolumne at Early Intake](chart/tuolumne_early_intake.png)
*[Live USGS page →](https://waterdata.usgs.gov/monitoring-location/11276900/)*

### Cherry Creek Near Early Intake
*The high-country canary. Spikes first. Drops fast. Drains the granite.*

![Cherry Creek](chart/cherry_creek.png)
*[Live USGS page →](https://waterdata.usgs.gov/monitoring-location/11278300/)*

*Charts updated every hour by GitHub Actions. Posted to social when something notable happens.*

---

## Why these three gauges

When an atmospheric river comes off the Pacific and hits the Sierra, it doesn't flood all at once. It moves in sequence — and if you're watching the right gauges, you can see it coming.

**Cherry Creek** responds first. It drains the high country above 4,000 feet — bare granite, thin soil, nowhere for the rain to go but down. When a storm hits, Cherry Creek shows it within hours. It's the warning shot. Active since 1956, it drains terrain that doesn't forgive.

**Tuolumne River at Early Intake** is the mainstem, the sum of everything upstream — Cherry Creek plus the Tuolumne's headwaters in Yosemite, all of it converging before the canyon narrows toward Don Pedro. Average flow around 400 cfs in a normal year. During a good storm it can run ten times that. It's been gauged since 1963 and operated in cooperation with [Turlock Irrigation District](https://www.tid.org/), which manages the reservoir downstream. When this gauge rises, Don Pedro is filling.

**Big Creek at Whites Gulch** is the local gauge — the one that tells you what's happening right behind town. It drains the oak and pine foothills west of the main Sierra crest, a smaller, flashier watershed that swings from barely alive in August to a serious roar after a good December storm. Six to three hundred cfs in the same creek, same season, different years. Gauged since 1969. In a wet year this creek is worth watching every day.

Together they cover the full picture: the high country feeding the mainstem, and the foothill creeks doing their own thing. Between them, over 180 years of combined USGS record.

---

## What the charts show

Each chart renders the last 7 days of instantaneous flow against 50+ years of historical context:

- **The hydrograph** — current flow in cfs, with annotated 7-day peak and trend direction
- **Percentile bands** — the green band is the normal range (p25–p75) for this exact day of the year, drawn from the full period of record
- **Percentile needle** on the right edge — where today's flow sits in the historical distribution, from record low to record high
- **Rate of change** — whether the gauge is accelerating, holding, or dropping
- **vs. long-term mean** — today's flow as a percentage of the historical average for this date

---

## When it posts

The bot stays silent unless one of five things is true:

| Trigger | What it means |
|---|---|
| **Rising fast** | Flow increasing ≥10% of the gauge's historical mean per hour — storm is hitting |
| **New 7-day peak** | Just set a new high water mark for the week |
| **Above normal** | Current flow exceeds the p75 historical percentile for this date |
| **Going dry** | Flow drops below 1.0 cfs — drought watch |
| **Flow returning** | Was below 1.0 cfs yesterday, now rising — the creek woke up |

Thresholds scale proportionally to each gauge's historical mean — so "rising fast" means something different for a 30 cfs foothill creek than it does for an 800 cfs mainstem river.

When a trigger fires: Bluesky and Twitter get a post with the chart. A text goes to the phone. Then silence again until the next event.

---

## How it's built

```
streamchaser/
├── .github/workflows/
│   └── chase.yml                   # runs every hour via cron
├── chart/
│   ├── big_creek.png               # updated every run
│   ├── tuolumne_early_intake.png
│   ├── cherry_creek.png
│   └── latest.png                  # = big_creek.png
├── src/streamchaser/
│   ├── __main__.py                 # orchestration, stations, notability logic
│   ├── gauge.py                    # USGS API calls + stat computation
│   ├── chart.py                    # matplotlib chart generation
│   └── poster.py                   # Twitter/X, Bluesky, SMS
└── README.md
```

Runs on GitHub Actions free tier — about 240 minutes/month out of the 2,000 allotted. No server. No database. Just a cron job and some USGS JSON.

---

## Fork it for your own watershed

1. Fork the repo
2. Edit the `STATIONS` list in `__main__.py`:

```python
STATIONS = [
    ("11284400", "Big Creek @ Whites Gulch",        "#USGS #BigCreek #Groveland"),
    ("11276900", "Tuolumne R BL Early Intake",      "#USGS #Tuolumne #Groveland"),
    ("11278300", "Cherry Creek NR Early Intake",    "#USGS #CherryCreek #Tuolumne"),
    # Add your station — find IDs at waterdata.usgs.gov
]
```

3. Add your secrets to GitHub (Settings → Secrets → Actions):

| Secret | What |
|---|---|
| `TWITTER_API_KEY` | Consumer Key — developer.x.com |
| `TWITTER_API_SECRET` | Consumer Secret |
| `TWITTER_ACCESS_TOKEN` | Access Token (Read+Write) |
| `TWITTER_ACCESS_SECRET` | Access Token Secret |
| `BLUESKY_HANDLE` | e.g. `yourname.bsky.social` |
| `BLUESKY_APP_PASSWORD` | bsky.app → Settings → App Passwords |
| `GMAIL_USER` | Gmail address for sending SMS alerts |
| `GMAIL_APP_PASSWORD` | Google App Password (16 chars) |
| `SMS_ADDRESS` | Your carrier SMS gateway, e.g. `2065551234@vtext.com` |

Common carrier gateways: `@vtext.com` (Verizon) · `@tmomail.net` (T-Mobile) · `@txt.att.net` (AT&T) · `@sms.cricketwireless.net` (Cricket)

---

## Data source

USGS National Water Information System — public domain, no API key required.

- Instantaneous values: `waterservices.usgs.gov/nwis/iv/`
- Historical statistics: `waterservices.usgs.gov/nwis/stat/`
- Parameter `00060` = Discharge, cubic feet per second

---

## License

MIT. Watch your own creek.
