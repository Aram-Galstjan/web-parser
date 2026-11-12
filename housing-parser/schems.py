from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Optional

from models import Listing


class IProxyProvider(ABC):
    @abstractmethod
    def get(self) -> Optional[dict]:
        """Return a proxy dict for requests or None (without proxy)."""

    @abstractmethod
    def mark_bad(self, proxy: Optional[dict]) -> None:
        """Mark a proxy as unusable."""


class IFetcher(ABC):
    @abstractmethod
    def fetch(self, url: str) -> Optional[str]:
        """Download a page and return HTML (or None on failure)."""


class IParser(ABC):
    @abstractmethod
    def parse(self, html: str) -> list[Listing]:
        """Extract listings from the search results HTML."""


class IListingRepository(ABC):
    @abstractmethod
    def save_many(self, listings: Iterable[Listing]) -> int:
        """Save listings (upsert) and return the number of new ones."""

    @abstractmethod
    def count(self) -> int:
        ...