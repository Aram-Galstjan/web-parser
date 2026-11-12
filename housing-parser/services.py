from __future__ import annotations

import logging
import random
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from schems import IFetcher, IListingRepository, IParser, IProxyProvider
from models import Listing, parse_price_eur

log = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]

BLOCK_MARKERS = ("captcha", "access denied", "unusual traffic", "are you a robot")


# ÐŸÑ€Ð¾ÐºÑÐ¸

class ProxyRotator(IProxyProvider):
    """Round-robin Ñ€Ð¾Ñ‚Ð°Ñ†Ð¸Ñ. Ð¤Ð¾Ñ€Ð¼Ð°Ñ‚ ÑÑ‚Ñ€Ð¾ÐºÐ¸: http://user:pass@host:port"""

    def __init__(self, proxies: list[str]):
        self._all = list(proxies)
        self._bad: set[str] = set()
        self._idx = 0

    @classmethod
    def from_file(cls, path: str | Path) -> "ProxyRotator":
        p = Path(path)
        if not p.exists():
            return cls([])
        lines = [
            ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        return cls(lines)

    def get(self) -> Optional[dict]:
        alive = [p for p in self._all if p not in self._bad]
        if not alive:
            return None
        proxy = alive[self._idx % len(alive)]
        self._idx += 1
        return {"http": proxy, "https": proxy}

    def mark_bad(self, proxy: Optional[dict]) -> None:
        if proxy:
            url = proxy.get("https")
            self._bad.add(url)
            log.warning("ÐŸÑ€Ð¾ÐºÑÐ¸ Ð¸ÑÐºÐ»ÑŽÑ‡Ñ‘Ð½: %s (Ð¶Ð¸Ð²Ñ‹Ñ…: %d)", url, len(self._all) - len(self._bad))



# Ð—Ð°Ð³Ñ€ÑƒÐ·ÐºÐ° ÑÑ‚Ñ€Ð°Ð½Ð¸Ñ†

class HttpFetcher(IFetcher):
    def __init__(
        self,
        proxies: IProxyProvider,
        timeout: int = 20,
        retries: int = 4,
        delay_range: tuple[float, float] = (2.0, 5.0),
        debug_path: str | Path | None = None,
    ):
        self.proxies = proxies
        self.timeout = timeout
        self.retries = retries
        self.delay_range = delay_range
        self.debug_path = Path(debug_path) if debug_path else None
        self.session = requests.Session()

    def _headers(self) -> dict:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.7",
            "Referer": "https://www.kleinanzeigen.de/",
        }

    def _dump_debug(self, html: str) -> None:
        if self.debug_path:
            try:
                self.debug_path.write_text(html, encoding="utf-8")
                log.info("HTML ÑÐ¾Ñ…Ñ€Ð°Ð½Ñ‘Ð½ Ð´Ð»Ñ Ð¾Ñ‚Ð»Ð°Ð´ÐºÐ¸: %s", self.debug_path)
            except OSError:
                pass

    def fetch(self, url: str) -> Optional[str]:
        last_html = ""
        for attempt in range(1, self.retries + 1):
            proxy = self.proxies.get()
            try:
                resp = self.session.get(
                    url, headers=self._headers(), proxies=proxy, timeout=self.timeout
                )
                last_html = resp.text
                lowered = resp.text.lower()
                has_ads = "aditem" in lowered or "ad-listitem" in lowered
                blocked = resp.status_code in (403, 429) or (not has_ads and any(m in lowered for m in BLOCK_MARKERS))

                if resp.status_code == 200 and not blocked:
                    time.sleep(random.uniform(*self.delay_range))  # Ð²ÐµÐ¶Ð»Ð¸Ð²Ð°Ñ Ð¿Ð°ÑƒÐ·Ð°
                    return resp.text

                log.warning("ÐŸÐ¾Ð¿Ñ‹Ñ‚ÐºÐ° %d/%d: HTTP %s / Ð±Ð»Ð¾ÐºÐ¸Ñ€Ð¾Ð²ÐºÐ° (%s)",
                            attempt, self.retries, resp.status_code, url)
                self.proxies.mark_bad(proxy)
            except requests.RequestException as exc:
                log.warning("ÐŸÐ¾Ð¿Ñ‹Ñ‚ÐºÐ° %d/%d: Ð¾ÑˆÐ¸Ð±ÐºÐ° ÑÐµÑ‚Ð¸: %s", attempt, self.retries, exc)
                self.proxies.mark_bad(proxy)

            time.sleep(min(2 ** attempt, 30) + random.random())  # ÑÐºÑÐ¿Ð¾Ð½ÐµÐ½Ñ†Ð¸Ð°Ð»ÑŒÐ½Ñ‹Ð¹ backoff

        if last_html:
            self._dump_debug(last_html)
        return None



# ÐŸÐ°Ñ€ÑÐµÑ€ HTML

class KleinanzeigenParser(IParser):
    BASE = "https://www.kleinanzeigen.de"

    def parse(self, html: str) -> list[Listing]:
        soup = BeautifulSoup(html, "lxml")
        items = soup.select("article[data-adid]")
        result: list[Listing] = []

        for art in items:
            href = art.get("data-href")
            if not href:
                a = art.select_one("a[href*='/s-anzeige/']")
                href = a.get("href") if a else None
            if not href:
                continue

            ext_id = art.get("data-adid") or self._id_from_url(href)
            if not ext_id:
                continue

            title = self._extract_title(art)
            if not title:
                continue

            for tag in art.select("script, style"):
                tag.decompose()
            texts = [re.sub(r"\s+", " ", s) for s in art.stripped_strings]

            price = next(
                (t for t in texts if re.fullmatch(r"\d[\d.,]*\s*â‚¬(\s*VB)?", t)), ""
            )
            address = next((t for t in texts if re.match(r"\d{5}\s+\S", t)), "")

            result.append(
                Listing(
                    external_id=str(ext_id),
                    title=title,
                    price=price,
                    price_eur=parse_price_eur(price),
                    address=address,
                    url=urljoin(self.BASE, href),
                )
            )
        return result

    @staticmethod
    def _extract_title(art) -> str:
        h2 = art.select_one("h2")
        if h2 and h2.get_text(strip=True):
            return h2.get_text(" ", strip=True)
        for a in art.select("a[href*='/s-anzeige/']"):
            text = a.get_text(" ", strip=True)
            if text:
                return text
        img = art.select_one("img[alt]")
        if img:
            return re.sub(r"\s*VorschÐ°Ñƒ$", "", img["alt"]).strip()
        return ""

    @staticmethod
    def _id_from_url(href: str) -> Optional[str]:
        m = re.search(r"/(\d{6,})-\d+-\d+", href)
        return m.group(1) if m else None



# ÐžÑ€ÐºÐµÑÑ‚Ñ€Ð°Ñ†Ð¸Ñ

class ParserService:
    def __init__(
        self,
        fetcher: IFetcher,
        parser: IParser,
        repository: IListingRepository,
        base_url: str,
        search_path: str,
        category_code: str,
        max_listings: int = 1000,
        max_pages: int = 50,
    ):
        self.fetcher = fetcher
        self.parser = parser
        self.repo = repository
        self.base_url = base_url.rstrip("/")
        self.search_path = search_path.strip("/")
        self.category_code = category_code
        self.max_listings = max_listings
        self.max_pages = max_pages

    def page_url(self, page: int) -> str:
        if page <= 1:
            return f"{self.base_url}/{self.search_path}/{self.category_code}"
        return f"{self.base_url}/{self.search_path}/seite:{page}/{self.category_code}"

    def _diagnose(self, html: str) -> None:
        (Path(__file__).resolve().parent / "debug_page.html").write_text(html, encoding="utf-8")
        soup = BeautifulSoup(html, "lxml")
        log.warning("title: %s | size: %d",
                    soup.title.get_text(strip=True) if soup.title else None, len(html))
        for sel in ["article.aditem", "article", "li.ad-listitem",
                    "[data-adid]", "a[href*='/s-anzeige/']"]:
            log.warning("%s -> %d", sel, len(soup.select(sel)))
        a = soup.select_one("[data-adid]") or soup.select_one("a[href*='/s-anzeige/']")
        if a:
            block = a.find_parent("article") or a
            log.warning("Ð¿Ñ€Ð¸Ð¼ÐµÑ€ Ð±Ð»Ð¾ÐºÐ°: %s", str(block)[:2000])

    def run(self) -> int:
        seen: set[str] = set()
        collected = 0
        new_total = 0

        for page in range(1, self.max_pages + 1):
            url = self.page_url(page)
            log.info("Ð¡Ñ‚Ñ€Ð°Ð½Ð¸Ñ†Ð° %d: %s", page, url)
            html = self.fetcher.fetch(url)
            if html is None:
                log.error("ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð·Ð°Ð³Ñ€ÑƒÐ·Ð¸Ñ‚ÑŒ ÑÑ‚Ñ€Ð°Ð½Ð¸Ñ†Ñƒ %d â€” Ð¾ÑÑ‚Ð°Ð½Ð°Ð²Ð»Ð¸Ð²Ð°ÑŽÑÑŒ", page)
                break

            listings = [l for l in self.parser.parse(html) if l.external_id not in seen]
            if not listings:
                if page == 1:
                    self._diagnose(html)
                log.info("ÐÐ¾Ð²Ñ‹Ñ… Ð¾Ð±ÑŠÑÐ²Ð»ÐµÐ½Ð¸Ð¹ Ð½Ð° ÑÑ‚Ñ€Ð°Ð½Ð¸Ñ†Ðµ Ð½ÐµÑ‚ â€” ÐºÐ¾Ð½ÐµÑ† Ð²Ñ‹Ð´Ð°Ñ‡Ð¸")
                break

            listings = listings[: self.max_listings - collected]
            seen.update(l.external_id for l in listings)
            collected += len(listings)
            new_total += self.repo.save_many(listings)
            log.info("Ð¡Ð¾Ð±Ñ€Ð°Ð½Ð¾ %d / %d", collected, self.max_listings)

            if collected >= self.max_listings:
                break

        log.info("Ð“Ð¾Ñ‚Ð¾Ð²Ð¾: ÑÐ¾Ð±Ñ€Ð°Ð½Ð¾ %d, Ð½Ð¾Ð²Ñ‹Ñ… Ð² Ð‘Ð”: %d, Ð²ÑÐµÐ³Ð¾ Ð² Ð‘Ð”: %d",
                 collected, new_total, self.repo.count())
        return collected
