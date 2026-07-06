"""Spider for RentCafe apartment communities.

RentCafe-hosted sites (e.g. Vue 22 Apartments, vue22apts.com) are recognisable by
their ``cdngeneralmvc.rentcafe.com`` scripts, ``resource.rentcafe.com`` images and
the ``/availableunits`` listing page. They often sit behind a Cloudflare managed
challenge, so a plain HTTP request is served the "Just a moment..." interstitial
instead of the data. Once the challenge clears, every available apartment is
rendered straight into the page HTML, grouped by floor plan: each
``div.floorplan-section`` carries the plan name/bed/bath and contains one
``tr.unit-container`` row per unit (apartment number, sq. ft., rent, date).

The listing itself has no floor-plan image, so we first load the sibling
``/floorplans`` page -- whose ``fp-container`` cards carry the plan image keyed by
the same floor-plan id -- and tag each unit with its plan's image.

Because Cloudflare blocks the plain downloader we render with a real (non-headless)
browser via scrapy-playwright -- the project's documented last resort. Headless
Chromium is detected and blocked, so the project always drives a headed browser
(configured globally in settings.py, shared across spiders by run.py); run it
under a virtual display: ``xvfb-run -a uv run python run.py`` (see README).
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import scrapy
from scrapy.http import Response
from scrapy_playwright.page import PageMethod

from apartment_scraper.items import ApartmentItem
from apartment_scraper.utils import to_int, to_number, to_whole_number


def _bedrooms(value: str | None) -> int | None:
    """Bedroom count as a whole number; a "Studio" counts as 0."""
    if value is None:
        return None
    if "studio" in value.lower():
        return 0
    return to_whole_number(value)


def _available_date(value: str | None) -> str | None:
    """Convert RentCafe's ``M/D/YYYY`` date to ISO; keep raw text otherwise."""
    if not value:
        return None
    value = value.strip()
    try:
        return datetime.strptime(value, "%m/%d/%Y").date().isoformat()
    except ValueError:
        return value or None


# RentCafe serves images through Cloudinary, where the path segment between
# ``/image/upload/`` and ``/s3/`` is the transform. Floor-plan cards use a
# size-limited transform (e.g. ``q_auto,f_auto,c_limit,w_576,h_260``); replacing
# it with just ``q_auto,f_auto`` returns the full-resolution image -- the same one
# the site's own floor-plan gallery shows.
_IMAGE_TRANSFORM_RE = re.compile(r"(/image/upload/).*?(/s3/)")


def _full_res_image(url: str | None) -> str | None:
    """Upgrade a RentCafe image URL to full resolution (drop the size transform)."""
    if not url:
        return None
    return _IMAGE_TRANSFORM_RE.sub(r"\1q_auto,f_auto\2", url)


class RentCafeSpider(scrapy.Spider):
    name = "rentcafe"
    # Nothing site-specific is hardcoded: the per-community `community` name and
    # `start_urls` come from communities.toml (via run.py), so this spider is
    # reusable for any RentCafe community's /availableunits page.
    community: str | None = None
    start_urls: list[str] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not self.start_urls:
            raise ValueError(
                "RentCafeSpider has no start_urls. Add the community (name + start_urls) "
                "to communities.toml and run `xvfb-run -a uv run python run.py` (see README)."
            )
        self.allowed_domains = [urlparse(url).netloc for url in self.start_urls]

    async def start(self) -> AsyncIterator[Any]:
        # Fetch /floorplans first: it carries the floor-plan images (keyed by
        # floor-plan id), which the /availableunits listing does not.
        for url in self.start_urls:
            yield scrapy.Request(
                urljoin(url, "/floorplans"),
                callback=self.parse_floorplans,
                meta={
                    "playwright": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_selector", "div.fp-container", timeout=60000),
                    ],
                    "units_url": url,
                },
                errback=self._floorplans_failed,
            )

    async def parse_floorplans(self, response: Response, **kwargs: Any) -> AsyncIterator[Any]:
        # Map floor-plan id -> image URL; /availableunits sections share the id
        # (data-id), so each unit can be tagged with its plan's image.
        images: dict[str, str] = {}
        for container in response.css("div.fp-container"):
            plan_id = container.attrib.get("id", "").removeprefix("fp-container-")
            src = container.css("img.card-img-top::attr(src)").get()
            if plan_id and src:
                images[plan_id] = _full_res_image(response.urljoin(src))
        yield self._units_request(response.meta["units_url"], images)

    def _floorplans_failed(self, failure: Any) -> scrapy.Request:
        # If /floorplans can't load, still scrape the units (the primary data);
        # they just won't carry a floor-plan image.
        units_url = failure.request.meta["units_url"]
        self.logger.warning("floorplans fetch failed (%s); units get no images", failure.value)
        return self._units_request(units_url, {})

    def _units_request(self, units_url: str, images: dict[str, str]) -> scrapy.Request:
        return scrapy.Request(
            units_url,
            callback=self.parse,
            meta={
                "playwright": True,
                "playwright_page_methods": [
                    PageMethod("wait_for_selector", "tr.unit-container", timeout=60000),
                ],
                "floor_plan_images": images,
            },
            dont_filter=True,
        )

    async def parse(self, response: Response, **kwargs: Any) -> AsyncIterator[Any]:
        community = (self.community or self.name).strip()
        images = response.meta.get("floor_plan_images", {})

        for section in response.css("div.floorplan-section"):
            floor_plan = section.attrib.get("data-name")
            image_url = images.get(section.attrib.get("data-id", ""))
            header = " ".join(section.css("h2 + div ::text").getall())
            bedrooms = _bedrooms(header)
            bathrooms = to_number(header.split("|", 1)[1]) if "|" in header else None

            for row in section.css("tr.unit-container"):
                unit = "".join(row.css("td.td-card-name::text").getall())
                rent = "".join(row.css("td.td-card-rent::text").getall())
                available = "".join(row.css("td.td-card-available::text").getall())
                apply_url = row.css("td.td-card-footer a::attr(href)").get() or ""
                yield ApartmentItem(
                    community=community,
                    unit=re.sub(r"[#\s]", "", unit) or None,
                    floor_plan=floor_plan,
                    bedrooms=bedrooms,
                    bathrooms=bathrooms,
                    square_feet=to_int("".join(row.css("td.td-card-sqft::text").getall())),
                    rent=to_int(rent),
                    available_date=_available_date(available),
                    url=response.urljoin(apply_url.strip()),
                    floor_plan_image_url=image_url,
                )
