"""Spider for Equity Residential (EQR) apartment communities.

equityapartments.com community pages sit behind a Cloudflare Turnstile challenge:
headless Chromium is detected and the challenge loops forever ("Just a moment..."
with a fresh Ray ID each time), so this needs a real, headed browser -- the
project's documented last resort (scrapy-playwright). Run under a virtual
display: ``xvfb-run -a uv run python run.py`` (see README).

Once the challenge clears there is no separate availability API call to
reproduce: every bedroom type/unit for the whole community is rendered straight
into the page as one JSON blob assigned to a global in the page's own
``<script>``:

    var ea5 = ea5 || {};
    ea5.unitAvailability = {"BedroomTypes": [...], "PremiumUnits": [...], ...};

So the strategy is "load the page (past Cloudflare), extract that JSON, parse
it" -- ``json.JSONDecoder().raw_decode`` grabs exactly one JSON value starting
at the marker, regardless of what follows the closing brace, which is safer
than a regex match against free-text unit descriptions that could themselves
contain ``};``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import scrapy
from scrapy.http import Response
from scrapy_playwright.page import PageMethod

from apartment_scraper.items import ApartmentItem

_DATA_MARKER = "ea5.unitAvailability = "


def _available_date(value: str | None) -> str | None:
    """Convert EQR's ``M/D/YYYY`` date to ISO; keep raw text otherwise."""
    if not value:
        return None
    value = value.strip()
    try:
        return datetime.strptime(value, "%m/%d/%Y").date().isoformat()
    except ValueError:
        return value or None


def _rent(unit: dict[str, Any]) -> int | None:
    """Monthly rent: the site's best advertised lease term, else the first term."""
    best = unit.get("BestTerm") or {}
    if best.get("Price") is not None:
        return int(best["Price"])
    terms = unit.get("Terms") or []
    return int(terms[0]["Price"]) if terms else None


class EquityResidentialSpider(scrapy.Spider):
    name = "equity"
    # Per-community config comes from communities.toml (via run.py); nothing
    # site-specific is hardcoded, so the same spider serves every community on
    # equityapartments.com.
    community: str | None = None
    start_urls: list[str] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not self.start_urls:
            raise ValueError(
                "EquityResidentialSpider has no start_urls. Add the community (name + "
                "start_urls) to communities.toml and run `xvfb-run -a uv run python run.py` "
                "(see README)."
            )
        self.allowed_domains = [urlparse(url).netloc for url in self.start_urls]

    async def start(self) -> AsyncIterator[Any]:
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                callback=self.parse,
                meta={
                    "playwright": True,
                    "playwright_page_methods": [
                        # A <script> tag is never "visible", so wait_for_selector
                        # (which defaults to state="visible") would hang forever;
                        # wait_for_function checks the raw HTML text instead.
                        PageMethod(
                            "wait_for_function",
                            f"document.documentElement.outerHTML.includes({_DATA_MARKER!r})",
                            timeout=30000,
                        ),
                    ],
                },
            )

    async def parse(self, response: Response, **kwargs: Any) -> AsyncIterator[Any]:
        community = (self.community or self.name).strip()

        marker = response.text.find(_DATA_MARKER)
        if marker == -1:
            self.logger.warning("No ea5.unitAvailability data found on %s", response.url)
            return
        data, _ = json.JSONDecoder().raw_decode(response.text, marker + len(_DATA_MARKER))

        for bedroom_type in data.get("BedroomTypes", []):
            for unit in bedroom_type.get("AvailableUnits", []):
                ledger_id = (unit.get("LedgerId") or "").strip()
                building_id = (unit.get("BuildingId") or "").strip()
                unit_id = (unit.get("UnitId") or "").strip()
                yield ApartmentItem(
                    community=community,
                    unit=unit_id or None,
                    floor_plan=unit.get("FloorplanName"),
                    bedrooms=unit.get("Bed"),
                    bathrooms=unit.get("Bath"),
                    square_feet=unit.get("SqFt"),
                    rent=_rent(unit),
                    available_date=_available_date(unit.get("AvailableDate")),
                    url=response.urljoin(f"/UnitFees/{ledger_id}/{building_id}/{unit_id}"),
                    floor_plan_image_url=response.urljoin((unit.get("Floorplan") or "").strip()),
                )
