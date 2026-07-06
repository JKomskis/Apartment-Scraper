"""Spider for Avalon (AvalonBay) apartment communities.

Avalon community pages on ``avaloncommunities.com`` are built on Arc Publishing's
Fusion platform, which embeds the page's full availability data as JSON in a
``Fusion.globalContent = {...};`` assignment in the HTML. Scrapy downloads that
JSON together with the page, so there is no separate API request to reproduce and
no need for a headless browser -- we just pull the script blob out and parse it.

Every Avalon community shares this structure, so this one spider works for any of
them. Nothing site-specific is hardcoded here: configure each community (its
``name`` and ``start_urls``) in ``communities.toml`` and run them all together::

    uv run python run.py

Output is written to ``data/availability.json``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import scrapy
from scrapy.http import Response

from apartment_scraper.items import ApartmentItem
from apartment_scraper.utils import to_number, to_whole_number

# Fusion stores the page's data model in ``Fusion.globalContent = {...};`` right
# before ``Fusion.globalContentConfig =``. That terminator is unique on the page,
# so a non-greedy capture of the object between them is unambiguous.
_GLOBAL_CONTENT_RE = re.compile(
    r"Fusion\.globalContent\s*=\s*(\{.*?\})\s*;\s*Fusion\.globalContentConfig",
    re.DOTALL,
)


def _starting_rent(unit: dict[str, Any]) -> int | None:
    """Return the advertised monthly "starting at" rent for ``unit``.

    Prefers the unfurnished offer (the standard listing); falls back to the
    furnished one. Mirrors the site's own display logic: ``useTotalPrice`` picks
    the all-in ``totalPrice``, otherwise the base ``price``.
    """
    pricing = unit.get("startingAtPricesUnfurnished") or unit.get("startingAtPricesFurnished")
    if not pricing:
        return None
    prices = pricing.get("prices") or {}
    value = prices.get("totalPrice" if unit.get("useTotalPrice") else "price")
    return int(value) if value is not None else None


def _iso_date(value: str | None) -> str | None:
    """Trim a Fusion ISO datetime ("2026-07-01T04:00:00+00:00") to its date."""
    return value.split("T", 1)[0] if value else None


def _unit_label(unit: dict[str, Any]) -> str | None:
    """Building-prefixed unit name as shown on the site, e.g. "001-318".

    The site labels each home ``<building>-<unitName>`` to disambiguate identical
    unit numbers in different buildings. That pair is the ``unitId`` with the
    ``propertyId`` prefix removed (unitId == ``<propertyId>-<building>-<unitName>``);
    falls back to the bare ``unitName`` if the ids don't line up.
    """
    unit_id = unit.get("unitId") or ""
    property_id = unit.get("propertyId") or ""
    if unit_id and property_id and unit_id.startswith(f"{property_id}-"):
        return unit_id.removeprefix(f"{property_id}-")
    return unit.get("unitName")


# Floor-plan images live on AvalonBay's resource host, not the page's
# www.avaloncommunities.com domain; the Fusion JSON only carries the path.
_IMAGE_BASE_URL = "https://resource.avalonbay.com"


def _image_url(floor_plan: dict[str, Any]) -> str | None:
    """Absolute floor-plan image URL on AvalonBay's resource host.

    The Fusion data stores only a path (e.g. "/floorplans/wa027/s4x582x2.jpg/1024/768"),
    which may contain spaces, so percent-encode it before joining it to the host.
    """
    path = floor_plan.get("highResolution") or floor_plan.get("lowResolution")
    if not path:
        return None
    return urljoin(_IMAGE_BASE_URL, quote(path))


class AvalonSpider(scrapy.Spider):
    name = "avalon"
    # Nothing site-specific is hardcoded: the per-community `community` name and
    # `start_urls` come from communities.toml (via run.py), so this one spider is
    # reusable for every Avalon community. Falls back to the name embedded in the
    # page data when `community` is not supplied.
    community: str | None = None
    start_urls: list[str] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not self.start_urls:
            raise ValueError(
                "AvalonSpider has no start_urls. Add the community (name + start_urls) "
                "to communities.toml and run `uv run python run.py` (see README)."
            )
        # Keep the crawl on the domains of the configured start URLs.
        self.allowed_domains = [urlparse(url).netloc for url in self.start_urls]

    def parse(self, response: Response, **kwargs: Any) -> Iterator[Any]:
        match = _GLOBAL_CONTENT_RE.search(response.text)
        if match is None:
            self.logger.error("Fusion.globalContent not found on %s", response.url)
            return
        data = json.loads(match.group(1))

        community = (self.community or data.get("name") or self.name).strip()

        for unit in data.get("units", []):
            floor_plan = unit.get("floorPlan") or {}
            available_date = unit.get("availableDateUnfurnished") or unit.get(
                "availableDateFurnished"
            )

            yield ApartmentItem(
                community=community,
                unit=_unit_label(unit),
                floor_plan=floor_plan.get("name"),
                bedrooms=to_whole_number(unit.get("bedroomNumber")),
                bathrooms=to_number(unit.get("bathroomNumber")),
                square_feet=unit.get("squareFeet"),
                rent=_starting_rent(unit),
                available_date=_iso_date(available_date),
                url=response.urljoin(unit.get("url") or ""),
                floor_plan_image_url=_image_url(floor_plan),
            )
