from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Optional

from models import Listing


class IProxyProvider(ABC):
    @abstractmethod
    def get(self) -> Optional[dict]:
        """Вернуть proxies-dict для requests или None (без прокси)."""

    @abstractmethod
    def mark_bad(self, proxy: Optional[dict]) -> None:
        """Пометить прокси как нерабочий."""


class IFetcher(ABC):
    @abstractmethod
    def fetch(self, url: str) -> Optional[str]:
        """Скачать страницу и вернуть HTML (или None при неудаче)."""


class IParser(ABC):
    @abstractmethod
    def parse(self, html: str) -> list[Listing]:
        """Извлечь объявления из HTML страницы выдачи."""


class IListingRepository(ABC):
    @abstractmethod
    def save_many(self, listings: Iterable[Listing]) -> int:
        """Сохранить объявления (upsert), вернуть число новых."""

    @abstractmethod
    def count(self) -> int:
        ...