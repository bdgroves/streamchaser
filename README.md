# streamchaser

> *You don't chase the water. You read it.*

Groveland, California sits at 2,800 feet on the western slope of the Sierra Nevada, halfway between the Central Valley floor and Yosemite Valley. The Tuolumne River runs through the canyon a thousand feet below town. Big Creek drains the hills right behind the fire station. Cherry Creek drops out of the high country from the north, cold and fast, before it meets the mainstem below.

All of it flows down to Don Pedro Reservoir, through the valley, and into the San Joaquin. All of it tells a story if you know how to read it.

This bot watches eleven gauges across three Sierra Nevada watersheds — simultaneously, around the clock — and says nothing unless something is worth saying.

---

## Latest readings

### 〰 Tuolumne Watershed

#### Tuolumne R at Hetch Hetchy
*Headwaters. First to spike. Downstream from O'Shaughnessy Dam.*

![Hetch Hetchy](https://raw.githubusercontent.com/bdgroves/streamchaser/charts/hetch_hetchy.png)
*[Live USGS page →](https://waterdata.usgs.gov/monitoring-location/11276500/)*

#### Tuolumne R Grand Canyon
*Wild canyon reach. Below Hetch Hetchy, above any valley influence.*

![Grand Canyon](https://raw.githubusercontent.com/bdgroves/streamchaser/charts/tuolumne_grand_canyon.png)
*[Live USGS page →](https://waterdata.usgs.gov/monitoring-location/11274790/)*

#### Tuolumne R BL Early Intake
*Pre–Don Pedro. Above Cherry Creek confluence.*

![Early Intake](https://raw.githubusercontent.com/bdgroves/streamchaser/charts/tuolumne_early_intake.png)
*[Live USGS page →](https://waterdata.usgs.gov/monitoring-location/11276900/)*

#### Tuolumne R BL LaGrange Dam
*Below all major dams. What actually enters the valley.*

![LaGrange](https://raw.githubusercontent.com/bdgroves/streamchaser/charts/tuolumne_lagrange.png)
*[Live USGS page →](https://waterdata.usgs.gov/monitoring-location/11289650/)*

#### Tuolumne R at Modesto
*Valley floor. The bottom line for Central Valley water.*

![Modesto](https://raw.githubusercontent.com/bdgroves/streamchaser/charts/tuolumne_modesto.png)
*[Live USGS page →](https://waterdata.usgs.gov/monitoring-location/11290000/)*

---

### 〰 Merced Watershed

#### Merced R at Happy Isles
*Raw Yosemite backcountry signal. Above Pohono Bridge.*

![Happy Isles](https://raw.githubusercontent.com/bdgroves/streamchaser/charts/merced_happy_isles.png)
*[Live USGS page →](https://waterdata.usgs.gov/monitoring-location/11264500/)*

#### Merced R at Pohono Bridge
*Classic Yosemite Valley gauge. Spectacular in flood years.*

![Pohono Bridge](https://raw.githubusercontent.com/bdgroves/streamchaser/charts/merced_pohono.png)
*[Live USGS page →](https://waterdata.usgs.gov/monitoring-location/11266500/)*

---

### 〰 Stanislaus Watershed

#### Stanislaus R at Ripon
*Valley floor. Below New Melones Reservoir.*

![Ripon](https://raw.githubusercontent.com/bdgroves/streamchaser/charts/stanislaus_ripon.png)
*[Live USGS page →](https://waterdata.usgs.gov/monitoring-location/11303000/)*

---

### 〰 Local Tributaries

#### Big Creek @ Whites Gulch
*The hometown gauge. No dams. Pure signal. The canary in the watershed.*

![Big Creek](https://raw.githubusercontent.com/bdgroves/streamchaser/charts/big_creek.png)
*[Live USGS page →](https://waterdata.usgs.gov/monitoring-location/11284400/)*

#### Cherry Creek NR Early Intake
*The high-country canary. Spikes first. Drops fast. Drains the granite.*

![Cherry Creek](https://raw.githubusercontent.com/bdgroves/streamchaser/charts/cherry_creek.png)
*[Live USGS page →](https://waterdata.usgs.gov/monitoring-location/11278300/)*

*Charts updated every hour by GitHub Actions. Posted to Bluesky only when a river does something unusual.*

---

## How a storm moves through the Sierra

When an atmospheric river comes off the Pacific and hits the Sierra, it doesn't flood all at once. It moves in sequence — and if you're watching the right gauges, you can see it coming.

**Happy Isles and Hetch Hetchy** respond first. They drain bare granite above 4,000 feet — thin soil, nowhere for the rain to go but down. When a storm hits, these show it within hours.

**Grand Canyon of the Tuolumne and Early Intake** catch the pulse next as it consolidates in the canyon. This is where you start to see the full shape of the hydrograph forming.

**Cherry Creek** — the high-country canary — spikes fast and drops fast. It's the warning shot for the local watershed, draining terrain that doesn't forgive.

**LaGrange and Modesto** tell you what the valley is actually going to receive — after the reservoirs have taken their cut, after the diversions have started, after the pulse has smoothed out over days of travel.

**Pohono Bridge** shows the Merced doing its own thing — Yosemite Valley floods independently of the Tuolumne, and the two watersheds don't always move together.

**Ripon** is the Stanislaus at the valley floor — a different watershed, different reservoir system, different behavior, but part of the same Central Valley water story.

**Big Creek** is the honest gauge. No dams. No regulation. Whatever the Sierra is doing, Big Creek shows it directly.

Watch a big storm event: a spike at Hetch Hetchy on Monday becomes a spike at Modesto by Thursday.

Between all eleven gauges: over 400 years of combined USGS record.

---

## When it posts

Only when a river is doing something unusual for the time of year:

| Post | When |
|---|---|
| 🔴 High water | A big river at or above 5,000 cfs |
| 📈 Highest ever for the date | Above the highest flow ever measured on today's date (gauges with 20+ years of record, and at least 10 cfs) |
| 🌧️ Storm rise | A free-flowing stream (Merced at Happy Isles and Pohono Bridge, Big Creek) more than doubles in 24 hours and is now above normal for the date |

Most of these reaches sit below dams (Hetch Hetchy, Early Intake, Cherry, La Grange, Ripon), and their releases change every day. So a "new 7-day peak" or a fast rise on its own doesn't post anymore. Before October 2026 it did, about once a day, mostly for routine fall releases.

At most one post per run (the biggest event wins), and a gauge won't post the same thing again for 3 days. A bigger event still posts. Charts redraw every run whether or not anything posts.

**Where it posts:** Bluesky. X is **standing by**: it posts there only when the repository variable `POST_TO_X` is set to `on` (Settings → Secrets and variables → Actions → Variables). It's off while the X developer account has no API credits.

**Checking on it:** `state.json` has what posted last at each gauge, and `logs/posts.jsonl` has every post attempt with any error. If Bluesky starts refusing posts, the run fails once so GitHub sends an email. **Run workflow** with *Dry run* ticked shows what would post.

---

## How it's built

```
streamchaser/
├── .github/workflows/
│   └── chase.yml                   # runs every hour via cron
├── chart/  (not in main — published to the `charts` branch each run)
│   ├── big_creek.png
│   ├── cherry_creek.png
│   ├── hetch_hetchy.png
│   ├── tuolumne_grand_canyon.png
│   ├── tuolumne_early_intake.png
│   ├── tuolumne_lagrange.png
│   ├── tuolumne_modesto.png
│   ├── merced_happy_isles.png
│   ├── merced_pohono.png
│   ├── stanislaus_ripon.png
│   └── latest.png                  # = big_creek.png
├── src/streamchaser/
│   ├── __main__.py                 # stations and the posting rules
│   ├── gauge.py                    # USGS API calls + stat computation
│   ├── chart.py                    # portrait chart generation
│   └── poster.py                   # Twitter/X + Bluesky
├── tests/test_rules.py             # offline tests of the posting rules
├── state.json                      # last post per gauge + network status
├── logs/posts.jsonl                # every post attempt
└── README.md
```

Runs on GitHub Actions free tier — about 600 minutes/month out of the 2,000 allotted (11 gauges × ~3 min each × 24 runs/day). No server. No database. Just a cron job and some USGS JSON.

---

## Fork it for your own watershed

1. Fork the repo
2. Edit the `STATIONS` list in `__main__.py` — add any USGS station ID, set `mode` to `"proportional"` for small streams or `"absolute"` for large rivers
3. Find station IDs at [waterdata.usgs.gov](https://waterdata.usgs.gov)
4. Add secrets to GitHub (Settings → Secrets → Actions):

| Secret | What |
|---|---|
| `TWITTER_API_KEY` | Consumer Key — developer.x.com |
| `TWITTER_API_SECRET` | Consumer Secret |
| `TWITTER_ACCESS_TOKEN` | Access Token (Read+Write) |
| `TWITTER_ACCESS_SECRET` | Access Token Secret |
| `BLUESKY_HANDLE` | e.g. `yourname.bsky.social` |
| `BLUESKY_APP_PASSWORD` | bsky.app → Settings → App Passwords |

---

## Data source

USGS National Water Information System — public domain, no API key required.

- Instantaneous values: `waterservices.usgs.gov/nwis/iv/`
- Historical statistics: `waterservices.usgs.gov/nwis/stat/`
- Parameter `00060` = Discharge, cubic feet per second

---

## License

MIT. Watch your own creek.
