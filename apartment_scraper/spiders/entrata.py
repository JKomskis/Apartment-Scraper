"""Spider for Entrata ProspectPortal apartment communities."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlparse

import scrapy
from scrapy.http import Response
from scrapy_playwright.page import PageMethod

from apartment_scraper.items import ApartmentItem
from apartment_scraper.utils import to_int, to_number, to_whole_number


def _bedrooms(value: str | None) -> int | None:
    if value is None:
        return None
    if "studio" in value.lower():
        return 0
    return to_whole_number(value)


class EntrataSpider(scrapy.Spider):
    name = "entrata"
    community: str | None = None
    start_urls: list[str] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not self.start_urls:
            raise ValueError("entrata spider requires start_urls")
        self.allowed_domains = [urlparse(url).netloc for url in self.start_urls]

    async def start(self) -> AsyncIterator[Any]:
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                callback=self.parse,
                meta={
                    "playwright": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_selector", "li.fp-group-item", timeout=30000),
                    ],
                },
            )

    async def parse(self, response: Response, **kwargs: Any) -> AsyncIterator[ApartmentItem]:
        community = (self.community or self.name).strip()

        for floor_plan in response.css("li.fp-group-item"):
            if "sold-out" in floor_plan.attrib.get("class", ""):
                continue

            name = floor_plan.css(".fp-name").xpath("string(.)").get()
            bed_bath = floor_plan.css(".fp-col.bed-bath .fp-col-text").xpath("string(.)").get()
            rent = floor_plan.css(".fp-col.rent .fp-col-text").xpath("string(.)").get()
            square_feet = floor_plan.css(".fp-col.sq-feet .fp-col-text").xpath("string(.)").get()
            detail_url = floor_plan.css("a.fp-name-link::attr(href)").get() or ""
            image_urls = floor_plan.css(
                ".fp-image source::attr(srcset), .fp-image img::attr(src)"
            ).getall()

            yield ApartmentItem(
                community=community,
                floor_plan=name.strip() if name else None,
                bedrooms=_bedrooms(bed_bath),
                bathrooms=to_number(
                    bed_bath.split("/", 1)[1] if bed_bath and "/" in bed_bath else None
                ),
                square_feet=to_int(square_feet),
                rent=to_int(rent),
                url=response.urljoin(detail_url),
                floor_plan_image_url=response.urljoin(image_urls[-1]) if image_urls else None,
            )
