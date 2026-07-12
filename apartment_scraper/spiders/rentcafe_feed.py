"""Spider for public RentCafe JSON feeds published by Mixed Media Creations."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import scrapy
from scrapy.http import Response

from apartment_scraper.items import ApartmentItem
from apartment_scraper.utils import to_int, to_number, to_whole_number


def _available_date(value: str | None) -> str | None:
    """Convert RentCafe's ``M/D/YYYY`` date to ISO; keep raw text otherwise."""
    if not value:
        return None
    value = value.strip()
    try:
        return datetime.strptime(value, "%m/%d/%Y").date().isoformat()
    except ValueError:
        return value or None


class RentCafeFeedSpider(scrapy.Spider):
    name = "rentcafe_feed"
    community: str | None = None
    start_urls: list[str] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not self.start_urls:
            raise ValueError("rentcafe_feed spider requires start_urls (the JSON feed URL)")
        self.allowed_domains = [urlparse(url).netloc for url in self.start_urls]

    def parse(self, response: Response, **kwargs: Any) -> Iterator[ApartmentItem]:
        for unit in response.json().get("floorplans", {}).values():
            yield ApartmentItem(
                community=(self.community or self.name).strip(),
                unit=unit.get("ApartmentName"),
                floor_plan=unit.get("FloorplanName"),
                bedrooms=to_whole_number(unit.get("Beds")),
                bathrooms=to_number(unit.get("Baths")),
                square_feet=to_int(unit.get("SQFT")),
                rent=to_int(unit.get("MinimumRent")),
                available_date=_available_date(unit.get("AvailableDate")),
                url=unit.get("ApplyOnlineURL"),
                floor_plan_image_url=next(
                    (url for url in (unit.get("UnitImageURLs") or []) if url), None
                ),
            )
