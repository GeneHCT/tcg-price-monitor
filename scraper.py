#!/usr/bin/env python3
"""Daily price scraper for yuyu-tei.jp Gundam Card Game listings."""

import csv
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# --- CSS selectors (update if the site markup changes) ---
CARD_CONTAINER_SELECTOR = "div.cards-list div.card-product"
CARD_ID_SELECTOR = "span.d-block.border.border-dark"
CARD_NAME_SELECTOR = "h4.text-primary.fw-bold"
CARD_PRICE_SELECTOR = "strong.d-block.text-end"

URLS = [
    # Boosters
    "https://yuyu-tei.jp/sell/gcg/s/gd01",
    "https://yuyu-tei.jp/sell/gcg/s/gd02",
    "https://yuyu-tei.jp/sell/gcg/s/gd03",
    "https://yuyu-tei.jp/sell/gcg/s/gd04",
    # Starters
    *[f"https://yuyu-tei.jp/sell/gcg/s/st{i:02d}" for i in range(1, 11)],
    # Extra
    "https://yuyu-tei.jp/sell/gcg/s/eb01",
    # Promos
    "https://yuyu-tei.jp/sell/gcg/s/promo-gd10",
    "https://yuyu-tei.jp/sell/gcg/s/rp-100",
    "https://yuyu-tei.jp/sell/gcg/s/exbp-100",
    "https://yuyu-tei.jp/sell/gcg/s/exrp-100",
]

CSV_PATH = Path("data/prices.csv")
CSV_FIELDS = ["Date", "URL_Identifier", "Card_ID", "Card_Name", "Price"]
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}
DISCORD_LIMIT = 2000
MAX_SUMMARY_LINES = 40


def url_identifier(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def parse_price(text: str) -> int:
    cleaned = text.replace(",", "").replace("円", "").replace("¥", "").strip()
    return int(cleaned)


def scrape_page(url: str) -> list[dict]:
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    rows = []
    for card in soup.select(CARD_CONTAINER_SELECTOR):
        id_el = card.select_one(CARD_ID_SELECTOR)
        name_el = card.select_one(CARD_NAME_SELECTOR)
        price_el = card.select_one(CARD_PRICE_SELECTOR)
        if not id_el or not name_el or not price_el:
            continue
        rows.append(
            {
                "URL_Identifier": url_identifier(url),
                "Card_ID": id_el.get_text(strip=True),
                "Card_Name": name_el.get_text(strip=True),
                "Price": parse_price(price_el.get_text()),
            }
        )
    return rows


def load_csv() -> list[dict]:
    if not CSV_PATH.exists():
        return []
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_csv(rows: list[dict]) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def card_key(row: dict) -> tuple[str, str, str]:
    return (row["URL_Identifier"], row["Card_ID"], row["Card_Name"])


def prices_by_date(rows: list[dict]) -> dict[str, dict[tuple, int]]:
    by_date: dict[str, dict[tuple, int]] = defaultdict(dict)
    for row in rows:
        by_date[row["Date"]][card_key(row)] = int(row["Price"])
    return by_date


def build_summary(today: str, by_date: dict[str, dict[tuple, int]]) -> str:
    today_prices = by_date.get(today, {})
    prior_dates = sorted(d for d in by_date if d < today)
    if not prior_dates:
        return f"**Yuyu-tei prices** ({today})\nFirst scrape: {len(today_prices)} cards recorded."

    yesterday = prior_dates[-1]
    yesterday_prices = by_date[yesterday]

    ups, downs, news = [], [], []
    for key, price in today_prices.items():
        set_id, card_id, name = key
        label = f"`{card_id}` {name} ({set_id})"
        if key not in yesterday_prices:
            news.append(f"• NEW {label}: {price:,}円")
        else:
            old = yesterday_prices[key]
            delta = price - old
            if delta > 0:
                ups.append(f"• ↑ {label}: {old:,} → {price:,}円 (+{delta:,})")
            elif delta < 0:
                downs.append(f"• ↓ {label}: {old:,} → {price:,}円 ({delta:,})")

    lines = [
        f"**Yuyu-tei prices** ({today} vs {yesterday})",
        f"{len(ups)} up · {len(downs)} down · {len(news)} new · {len(today_prices)} cards",
        "",
    ]
    for section in (ups, downs, news):
        lines.extend(section[:MAX_SUMMARY_LINES])
        if len(section) > MAX_SUMMARY_LINES:
            lines.append(f"…and {len(section) - MAX_SUMMARY_LINES} more")
        if section:
            lines.append("")

    if len(ups) + len(downs) + len(news) == 0:
        lines.append("No price changes.")

    return "\n".join(lines).strip()


def post_discord(message: str) -> None:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        print("DISCORD_WEBHOOK_URL not set; skipping Discord.")
        return

    # Discord content max is 2000 chars; split if needed.
    chunks = []
    while message:
        chunks.append(message[:DISCORD_LIMIT])
        message = message[DISCORD_LIMIT:]

    for chunk in chunks:
        resp = requests.post(webhook, json={"content": chunk}, timeout=30)
        resp.raise_for_status()


def main() -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    existing = load_csv()

    # Drop any prior rows for today so re-runs replace instead of duplicating.
    existing = [r for r in existing if r["Date"] != today]

    scraped = []
    for url in URLS:
        print(f"Scraping {url} …")
        page_rows = scrape_page(url)
        print(f"  {len(page_rows)} cards")
        for row in page_rows:
            scraped.append({"Date": today, **row})
        time.sleep(0.5)

    all_rows = existing + scraped
    all_rows.sort(key=lambda r: (r["Date"], r["URL_Identifier"], r["Card_ID"], r["Card_Name"]))
    save_csv(all_rows)

    summary = build_summary(today, prices_by_date(all_rows))
    print(summary)
    post_discord(summary)


if __name__ == "__main__":
    main()
