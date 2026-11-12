from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Listing:
    """A single real-estate listing."""

    external_id: str
    title: str
    price: str
    address: str
    url: str
    price_eur: Optional[int] = None
    scraped_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def to_dict(self) -> dict:
        return asdict(self)


def parse_price_eur(raw: str) -> Optional[int]:
    """'1.250 € VB' -> 1250, 'Zu verschenken' -> None."""
    if not raw:
        return None
    match = re.search(r"\d[\d.]*", raw)
    if not match:
        return None
    digits = match.group(0).replace(".", "")
    return int(digits) if digits.isdigit() else None