from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from repositories import SqliteListingRepository
from services import HttpFetcher, KleinanzeigenParser, ParserService, ProxyRotator

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(ROOT / "parser.log", encoding="utf-8"),
        ],
    )


def main() -> int:
    load_dotenv(ROOT / ".env")
    cfg = json.loads((HERE / "config.json").read_text(encoding="utf-8"))

    ap = argparse.ArgumentParser(description="Kleinanzeigen Berlin apartments parser")
    ap.add_argument("--limit", type=int, default=cfg["max_listings"],
                    help="сколько объявлений собрать (по умолчанию из config.json)")
    ap.add_argument("--no-proxy", action="store_true", help="работать без прокси")
    args = ap.parse_args()

    setup_logging(os.getenv("LOG_LEVEL", "INFO"))

    use_proxy = not args.no_proxy and os.getenv("USE_PROXIES", "true").lower() == "true"
    proxies = ProxyRotator.from_file(HERE / "proxies.txt") if use_proxy else ProxyRotator([])

    fetcher = HttpFetcher(
        proxies=proxies,
        timeout=cfg["timeout"],
        retries=cfg["retries"],
        delay_range=tuple(cfg["delay_range"]),
        debug_path=HERE / "debug_page.html",
    )
    repo = SqliteListingRepository(ROOT / os.getenv("DB_PATH", cfg["db_path"]))

    service = ParserService(
        fetcher=fetcher,
        parser=KleinanzeigenParser(),
        repository=repo,
        base_url=cfg["base_url"],
        search_path=cfg["search_path"],
        category_code=cfg["category_code"],
        max_listings=min(args.limit, 1000),
        max_pages=cfg["max_pages"],
    )
    service.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())