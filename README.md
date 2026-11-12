# Housing Parser — Kleinanzeigen Berlin

A Python scraper that collects apartment rental listings in Berlin from
[kleinanzeigen.de](https://www.kleinanzeigen.de). A single run gathers up to **1,000 listings**
and stores them in a local SQLite database.

| Field | Example |
|---|---|
| Title | `2-Zimmer-Penthouse in Berlin Gesundbrunnen` |
| Price | `1.649 €` (also stored as a number: `1649`) |
| Address | `13357 Berlin - Mitte` |
| Link | `https://www.kleinanzeigen.de/s-anzeige/...` |

## Features

- Walks through the search result pages until the limit is reached (default: 1,000 listings)
- SQLite storage without duplicates: re-running the parser updates existing records by listing ID
- Proxy rotation, User-Agent rotation, retries with exponential backoff, randomized delays
- Saves the raw HTML to `housing-parser/debug_page.html` when the site returns a block or captcha page
- Built-in analytics (min / median / max price, top districts) and CSV export
- Runs locally or in Docker
- Layered design: models, interfaces, repository and service are separated, so each part is easy to replace or test

## Project structure

```
web-parser/
├── housing-parser/
│   ├── main.py          # entry point, CLI, logging
│   ├── models.py        # Listing model, price parsing
│   ├── schems.py        # abstract interfaces (fetcher, parser, repository, proxy provider)
│   ├── repositories.py  # SQLite storage
│   ├── services.py      # proxy rotation, HTTP fetching, HTML parser, pagination
│   ├── config.json      # parser settings
│   └── proxies.txt      # proxy list (optional, git-ignored)
├── analytics.py         # statistics and CSV export
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## Installation

Requires Python 3.10 or newer.

```bash
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # macOS / Linux

pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
```

## Usage

Run all commands from the project root.

```bash
# quick test: 50 listings, no proxies
python housing-parser/main.py --limit 50 --no-proxy

# full run: up to 1,000 listings
python housing-parser/main.py --no-proxy
```

Results are saved to `apartments.db`, logs go to `parser.log`.
A full run takes about 5 minutes because of the delays between requests.

### Analytics and CSV export

```bash
python analytics.py                     # print statistics
python analytics.py --csv listings.csv  # also export all listings to CSV
```

Example output:

```
Total listings: 50
Min / median / mean / max: 710 / 1385 / 1415 / 2990 €

Top districts by number of listings:
  Reinickendorf     13 listings   median 1392 €
  Neukölln           7 listings   median 1050 €
  Tempelhof          5 listings   median 1378 €
```

To browse the database, open `apartments.db` with the **SQLite Viewer** extension for VS Code
or with [DB Browser for SQLite](https://sqlitebrowser.org).

### Docker

```bash
# create empty files first, otherwise Docker creates directories in their place
touch apartments.db parser.log   # Windows: type nul > apartments.db

docker compose up --build
```

## Configuration

### `.env`

| Variable | Default | Description |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`) |
| `USE_PROXIES` | `false` | Set to `true` to use the proxies from `proxies.txt` |
| `DB_PATH` | `apartments.db` | Database path relative to the project root |

### `housing-parser/config.json`

| Parameter | Description |
|---|---|
| `search_path`, `category_code` | Parts of the search URL (`s-wohnung-mieten/berlin` and `c203l3331`) |
| `max_listings` | Listings per run (capped at 1,000) |
| `max_pages` | Maximum number of result pages (the site serves at most 50) |
| `timeout`, `retries` | Request timeout in seconds and number of retries |
| `delay_range` | Delay between requests in seconds, `[min, max]` |

To scrape a different search, open the desired results page on the site and copy the relevant
URL parts into `search_path` and `category_code`.

### Proxies

Create `housing-parser/proxies.txt` with one proxy per line and set `USE_PROXIES=true` in `.env`:

```
http://user:password@123.45.67.89:8080
socks5://11.22.33.44:1080
```

Dead proxies are removed from the rotation automatically.
The file contains credentials, so it is git-ignored. Never commit it.

## How it works

1. `ParserService` builds the URL of each result page and asks the fetcher for its HTML.
2. `HttpFetcher` downloads the page with a random User-Agent and an optional proxy,
   retries on errors or blocks, and waits a random time between requests.
3. `KleinanzeigenParser` extracts the listings. It relies on stable attributes
   (`data-adid`, `data-href`) and on the shape of the text (price and postal code patterns)
   instead of CSS classes, which change frequently.
4. `SqliteListingRepository` saves the batch with an upsert keyed by the listing ID.

## Troubleshooting

| Symptom | What to do |
|---|---|
| `Failed to load the page` or block warnings in the log | The site restricted access. Inspect `housing-parser/debug_page.html`, enable proxies, increase `delay_range` |
| 0 listings collected, no errors | The site layout has probably changed. Update the extraction logic in `KleinanzeigenParser` (`services.py`) |
| Empty price or address for some listings | Expected for listings without a price (e.g. "Zu verschenken") |
| `ModuleNotFoundError` | The virtual environment is not active, or `pip install -r requirements.txt` was not run |
| `FileNotFoundError: config.json` | The file must be located in `housing-parser/` |

## Limitations

- Kleinanzeigen serves at most 50 result pages of about 25 listings each, which is enough for 1,000 listings.
- The parser depends on the website's markup and may need updates when the site changes.

## Disclaimer

This project is for educational and personal use. Scraping may violate the website's terms of
service. You are responsible for complying with them and with applicable law. Keep the request
delays enabled, do not overload the site, and do not publish or redistribute collected personal data.

## License

MIT
