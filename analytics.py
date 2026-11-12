"""Fast analytics.
python analytics.py [--csv out.csv]
"""
from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import statistics
from pathlib import Path

DB = Path(__file__).resolve().parent / "apartments.db"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="export all listings to CSV")
    args = ap.parse_args()

    conn = sqlite3.connect(DB)
    total = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    prices = [r[0] for r in conn.execute(
        "SELECT price_eur FROM listings WHERE price_eur IS NOT NULL AND price_eur > 0")]

    print(f"Total listings: {total}")
    if prices:
        print(f"With price: {len(prices)}")
        print(f"Min / median / mean / max: "
              f"{min(prices)} / {int(statistics.median(prices))} / "
              f"{int(statistics.mean(prices))} / {max(prices)} €")

    # Top districts/postal codes (address format: "10115 Mitte")
    counts: dict[str, list[int]] = {}
    for addr, price in conn.execute("SELECT address, price_eur FROM listings"):
        m = re.search(r"\d{5}\s+(.+)", addr or "")
        if m and price:
            counts.setdefault(m.group(1).strip(), []).append(price)
    print("\nTop districts by number of listings:")
    for area, vals in sorted(counts.items(), key=lambda kv: -len(kv[1]))[:10]:
        print(f"  {area:<30} {len(vals):>4} items  median {int(statistics.median(vals))} €")

    if args.csv:
        rows = conn.execute(
            "SELECT title, price, address, url FROM listings ORDER BY scraped_at DESC").fetchall()
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["title", "price", "address", "url"])
            w.writerows(rows)
        print(f"\nCSV saved: {args.csv}")


if __name__ == "__main__":
    main()