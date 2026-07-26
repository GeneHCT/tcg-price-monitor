# AGENTS.md

## Project overview

Python scraper that pulls Gundam Card Game prices from yuyu-tei.jp via ScraperAPI, appends rows to `data/prices.csv`, and posts a Discord summary. `index.html` is a static viewer for that CSV.

## Cursor Cloud specific instructions

### Install

Dependencies are installed by `.cursor/environment.json` via:

```bash
pip3 install -r requirements.txt
```

Python 3.12 is expected (same as CI).

### Required secrets

Configure these in the Cloud Agents Secrets tab (do not commit values):

- `SCRAPER_API_KEY` — ScraperAPI key used by `scraper.py`
- `DISCORD_WEBHOOK_URL` — Discord webhook for daily price summaries (optional for local dry runs)

### Useful commands

```bash
# Full scrape + CSV update + Discord post
python3 scraper.py

# Serve the static price viewer
python3 -m http.server 8000
```

### Notes

- Prefer not to run a full scrape unless the task needs live price data; it hits many product pages through ScraperAPI.
- CI runs the scraper on a schedule in `.github/workflows/scrape.yml`.
