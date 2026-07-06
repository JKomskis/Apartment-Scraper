"""Example apartment spider.

This is a **template** that shows the shape of a real spider. The CSS selectors
below are placeholders -- copy this file, point it at a real apartment website,
and update the selectors to match that site's markup.

Run it with::

    uv run scrapy crawl example

Output is written to ``data/availability.json``.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

import scrapy
from scrapy.http import Response

from apartment_scraper.items import ApartmentItem
from apartment_scraper.utils import to_int, to_number, to_whole_number


class ExampleApartmentSpider(scrapy.Spider):
    name = "example"
    # Set per community by the runner (communities.toml); falls back to the page
    # heading or the spider name.
    community: str | None = None
    start_urls = ["https://example.com/floorplans"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Keep the crawl on the domains of the configured start URLs.
        self.allowed_domains = [urlparse(url).netloc for url in self.start_urls]

    def parse(self, response: Response, **kwargs: Any) -> Iterator[Any]:
        community = (self.community or response.css("h1::text").get() or self.name).strip()

        # Each ".unit-card" is one available unit. Adjust to the real site.
        for card in response.css(".unit-card"):
            yield ApartmentItem(
                community=community,
                unit=card.css(".unit-number::text").get(),
                floor_plan=card.css(".floor-plan-name::text").get(),
                bedrooms=to_whole_number(card.css(".beds::text").get()),
                bathrooms=to_number(card.css(".baths::text").get()),
                square_feet=to_int(card.css(".sqft::text").get()),
                rent=to_int(card.css(".rent::text").get()),
                available_date=card.css(".available-date::text").get(),
                url=response.urljoin(card.css("a::attr(href)").get() or ""),
                floor_plan_image_url=response.urljoin(
                    card.css("img.floor-plan::attr(src)").get() or ""
                ),
            )

        # Follow pagination if the site splits results across pages.
        next_page = response.css("a.next::attr(href)").get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)
