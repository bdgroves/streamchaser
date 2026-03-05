# streamchaser

> *You don't chase the water. You read it.*

A GitHub Actions bot that monitors a USGS stream gauge and posts a daily field report — chart and stats — to Twitter/X and Bluesky. Automated. Unattended. Running whether you're watching or not.

---

## What it does

Every 6 hours (configurable), it pulls real-time streamflow data from the USGS National Water Information System, generates a chart, and posts to social media.

**Each post includes:**

- Current discharge in cfs with trend direction
- Δ 1-hour and 24-hour change
- 7-day flow record with annotated peak
- Rate of change — accelerating, holding, decelerating
- Flow vs. historical average for this date
- Last-year reference

---

## Repo layout

```
streamchaser/
├── .github/
│   └── workflows/
│       └── chase.yml               # scheduled action
├── src/
│   └── streamchaser/
│       ├── __init__.py
│       ├── __main__.py             # entry point
│       ├── gauge.py                # USGS data fetching + stat computation
│       ├── chart.py                # chart generation
│       ├── chart_preview.py        # local visual test (no API calls)
│       └── poster.py               # Twitter/X + Bluesky posting
├── pixi.toml                       # environment + task runner
├── pixi.lock                       # reproducible lockfile (commit this)
└── README.md
```

---

## Setup

### 1. Fork and clone

```bash
git clone https://github.com/YOUR_USERNAME/streamchaser.git
cd streamchaser
```

### 2. Configure your station

Open `.github/workflows/chase.yml` and set these three env vars:

```yaml
env:
  USGS_STATION_ID:   "11284400"
  USGS_STATION_NAME: "Big Creek @ Whites Gulch"
  USGS_HASHTAGS:     "#USGS #BigCreek #Groveland"
```

Find your station ID at [waterdata.usgs.gov](https://waterdata.usgs.gov/nwis/rt). Search by state, river, or location — look for a site with parameter `00060` (Discharge).

### 3. Add GitHub Secrets

**Settings → Secrets and variables → Actions → New repository secret**

#### Twitter / X

You need a free [developer account](https://developer.x.com) and an app with **Read + Write** permissions and **OAuth 1.0a** enabled.

| Secret | What it is | Where |
|---|---|---|
| `TWITTER_API_KEY` | Consumer Key | developer.x.com → Your App → Keys & Tokens |
| `TWITTER_API_SECRET` | Consumer Secret | same |
| `TWITTER_ACCESS_TOKEN` | Account Access Token | same → *Access Token & Secret* |
| `TWITTER_ACCESS_SECRET` | Account Access Token Secret | same |

> **Note:** Access tokens are tied to *your account*. The app posts as you. Tokens generated under "Read only" permission won't work — regenerate them after switching to Read + Write.

#### Bluesky

No developer account needed. Just an App Password.

| Secret | What it is | Where |
|---|---|---|
| `BLUESKY_HANDLE` | Your handle | e.g. `yourname.bsky.social` |
| `BLUESKY_APP_PASSWORD` | App-specific password | bsky.app → Settings → Privacy & Security → App Passwords → Add App Password |

> **Use an App Password, not your login password.** App Passwords are scoped and revocable.

### 4. Set posting frequency

Edit the cron in `chase.yml`:

```yaml
- cron: '0 */6 * * *'   # every 6 hours (default)
# - cron: '0 * * * *'   # every hour
# - cron: '0 15 * * *'  # once daily — 15:00 UTC / ~8am Pacific
```

### 5. Disable a platform

```yaml
POST_TWITTER: "false"
POST_BLUESKY: "true"
```

---

## Local development

Install [Pixi](https://pixi.sh) first:

```bash
curl -fsSL https://pixi.sh/install.sh | bash
```

Then:

```bash
# Install the environment (first time, or after pixi.toml changes)
pixi install

# Generate a chart from mock data — no API calls, no posting
pixi run chart
# → Chart saved to /tmp/streamchaser_11284400_YYYYMMDD_HHMM.png

# Run the full bot (will post unless you disable platforms)
export POST_TWITTER=false
export POST_BLUESKY=false
pixi run run
```

Pixi handles Python version, all dependencies, and task shortcuts in one lockfile. No virtualenv management needed.

---

## Debugging a run

Every GitHub Actions run uploads the generated chart as an artifact (kept 5 days).

**Actions tab → click the run → Artifacts → chart-N**

Download and inspect without needing to scroll your social feed.

---

## Data source

All flow data is fetched from the **USGS Water Services API** — public, no API key required.

- Instantaneous values: `waterservices.usgs.gov/nwis/iv/`
- Historical statistics: `waterservices.usgs.gov/nwis/stat/`
- Parameter `00060` = Discharge (streamflow), cubic feet per second

---

## License

MIT
