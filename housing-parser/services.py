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

BLOCK_MARKERS = ("captcha", "access denied", "unusual traffic", "robot")


# Прокси

class ProxyRotator(IProxyProvider):
    """Round-robin ротация. Формат строки: http://user:pass@host:port"""

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
            log.warning("Прокси исключён: %s (живых: %d)", url, len(self._all) - len(self._bad))


# --------------------------------------------------------------------------- #
# Загрузка страниц
# --------------------------------------------------------------------------- #
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
                log.info("HTML сохранён для отладки: %s", self.debug_path)
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
                lowered = resp.text[:5000].lower()
                blocked = resp.status_code in (403, 429) or any(m in lowered for m in BLOCK_MARKERS)

                if resp.status_code == 200 and not blocked:
                    time.sleep(random.uniform(*self.delay_range))  # вежливая пауза
                    return resp.text

                log.warning("Попытка %d/%d: HTTP %s / блокировка (%s)",
                            attempt, self.retries, resp.status_code, url)
                self.proxies.mark_bad(proxy)
            except requests.RequestException as exc:
                log.warning("Попытка %d/%d: ошибка сети: %s", attempt, self.retries, exc)
                self.proxies.mark_bad(proxy)

            time.sleep(min(2 ** attempt, 30) + random.random())  # экспоненциальный backoff

        if last_html:
            self._dump_debug(last_html)
        return None



# Парсер HTML

class KleinanzeigenParser(IParser):
    BASE = "https://www.kleinanzeigen.de"

    def parse(self, html: str) -> list[Listing]:
        soup = BeautifulSoup(html, "lxml")
        items = soup.select("article.aditem, li.ad-listitem article")
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

            title_el = art.select_one(".aditem-main--middle--title, h2 a, a.ellipsis")
            price_el = art.select_one(
                ".aditem-main--middle--price-shipping--price, p.aditem-main--middle--price"
            )
            addr_el = art.select_one(".aditem-main--top--left")

            title = title_el.get_text(" ", strip=True) if title_el else ""
            if not title:
                continue
            price = price_el.get_text(" ", strip=True) if price_el else ""
            address = addr_el.get_text(" ", strip=True) if addr_el else ""

            result.append(
                Listing(
                    external_id=str(ext_id),
                    title=title,
                    price=price,
                    price_eur=parse_price_eur(price),
                    address=re.sub(r"\s+", " ", address),
                    url=urljoin(self.BASE, href),
                )
            )
        return result

    @staticmethod
    def _id_from_url(href: str) -> Optional[str]:
        m = re.search(r"/(\d{6,})-\d+-\d+", href)
        return m.group(1) if m else None



# Оркестрация

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

    def run(self) -> int:
        seen: set[str] = set()
        collected = 0
        new_total = 0

        for page in range(1, self.max_pages + 1):
            url = self.page_url(page)
            log.info("Страница %d: %s", page, url)
            html = self.fetcher.fetch(url)
            if html is None:
                log.error("Не удалось загрузить страницу %d — останавливаюсь", page)
                break

            listings = [l for l in self.parser.parse(html) if l.external_id not in seen]
            if not listings:
                log.info("Новых объявлений на странице нет — конец выдачи")
                break

            listings = listings[: self.max_listings - collected]
            seen.update(l.external_id for l in listings)
            collected += len(listings)
            new_total += self.repo.save_many(listings)
            log.info("Собрано %d / %d", collected, self.max_listings)

            if collected >= self.max_listings:
                break

        log.info("Готово: собрано %d, новых в БД: %d, всего в БД: %d",
                 collected, new_total, self.repo.count())
        return collected