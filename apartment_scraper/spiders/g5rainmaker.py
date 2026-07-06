"""Spider for apartment communities on G5 Marketing Cloud's Rainmaker inventory
platform.

The floor-plans page renders its "Choose Your Floor Plan" section (and the
Engrain SightMap widget) from data fetched client-side, via GraphQL, from
``inventory.g5marketingcloud.com/graphql``. Two queries do the work:

- ``ApartmentComplex(locationUrn)`` -- the community's floor plans (name,
  beds/baths/sqft, image, and how many units of each are currently available).
- ``Units(floorplanId)`` -- the individual available units for one floor plan
  (unit number, availability date, price).

The ``locationUrn`` both queries need isn't a URL parameter -- it's embedded as
plain JSON in the static page HTML (inside a
``<script class="... contact-info-sheet-config">`` block used by an unrelated
contact widget), so it can be pulled out of the normal Scrapy response with no
browser needed; this spider then reproduces the two GraphQL requests directly.

Every G5/Rainmaker community shares this platform, so this one spider is
reusable: configure each community's ``name`` and ``start_urls`` (its
human-facing floor-plans page) in communities.toml and run them together::

    uv run python run.py

Output is written to ``data/availability.json``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

import scrapy
from scrapy.http import Response

from apartment_scraper.items import ApartmentItem
from apartment_scraper.utils import to_int, to_number, to_whole_number

_GRAPHQL_URL = "https://inventory.g5marketingcloud.com/graphql"

# The live site's queries request far more fields than we need; the schema
# allows any subset, so these are trimmed down to just what maps to ApartmentItem.
_APARTMENT_COMPLEX_QUERY = """
query ApartmentComplex($locationUrn: String!) {
  apartmentComplex(locationUrn: $locationUrn) {
    floorplans {
      id
      name
      totalAvailableUnits
      beds
      baths
      sqft
      imageUrl
    }
  }
}
"""

_UNITS_QUERY = """
query Units($floorplanId: Int!, $locationUrn: String, $limit: Int) {
  units(floorplanId: $floorplanId, locationUrn: $locationUrn, limit: $limit) {
    name
    displayName
    availabilityDate
    sqftDisplay
    prices {
      priceType
      value
    }
  }
}
"""


def _rate(unit: dict[str, Any]) -> Any:
    """The unit's advertised monthly rate value from its ``prices`` list."""
    for price in unit.get("prices") or []:
        if price.get("priceType") == "rate":
            return price.get("value")
    return None


class G5RainmakerSpider(scrapy.Spider):
    name = "g5rainmaker"
    # Nothing site-specific is hardcoded: the per-community `community` name and
    # `start_urls` (the floor-plans page) come from communities.toml (via
    # run.py), so this one spider is reusable for every G5/Rainmaker community.
    community: str | None = None
    start_urls: list[str] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not self.start_urls:
            raise ValueError("g5rainmaker spider requires start_urls (the floor-plans page)")
        self.allowed_domains = [urlparse(url).netloc for url in self.start_urls]
        self.allowed_domains.append(urlparse(_GRAPHQL_URL).netloc)

    def parse(self, response: Response, **kwargs: Any) -> Iterator[Any]:
        location_urn = response.css("script.contact-info-sheet-config::text").re_first(
            r'"locationUrn"\s*:\s*"([^"]+)"'
        )
        if not location_urn:
            self.logger.error("No locationUrn found on %s", response.url)
            return

        yield self._graphql_request(
            response.url,
            "ApartmentComplex",
            _APARTMENT_COMPLEX_QUERY,
            {"locationUrn": location_urn},
            callback=self.parse_floorplans,
            cb_kwargs={"page_url": response.url, "location_urn": location_urn},
        )

    def parse_floorplans(
        self, response: Response, page_url: str, location_urn: str, **kwargs: Any
    ) -> Iterator[Any]:
        floorplans = json.loads(response.text)["data"]["apartmentComplex"]["floorplans"]
        for floorplan in floorplans:
            if not floorplan.get("totalAvailableUnits"):
                continue
            yield self._graphql_request(
                page_url,
                "Units",
                _UNITS_QUERY,
                {"floorplanId": floorplan["id"], "locationUrn": location_urn, "limit": 999},
                callback=self.parse_units,
                cb_kwargs={"page_url": page_url, "floorplan": floorplan},
            )

    def parse_units(
        self, response: Response, page_url: str, floorplan: dict[str, Any], **kwargs: Any
    ) -> Iterator[Any]:
        units = json.loads(response.text)["data"]["units"]
        for unit in units:
            yield ApartmentItem(
                community=self.community,
                unit=unit.get("displayName") or unit.get("name"),
                floor_plan=floorplan.get("name"),
                bedrooms=to_whole_number(floorplan.get("beds")),
                bathrooms=to_number(floorplan.get("baths")),
                square_feet=to_int(unit.get("sqftDisplay")) or to_int(str(floorplan.get("sqft"))),
                rent=to_int(str(_rate(unit))),
                available_date=unit.get("availabilityDate"),
                url=f"{page_url.split('#', 1)[0]}#/floorplans/{floorplan['id']}/",
                floor_plan_image_url=floorplan.get("imageUrl"),
            )

    @staticmethod
    def _graphql_request(
        page_url: str,
        operation_name: str,
        query: str,
        variables: dict[str, Any],
        callback: Any,
        cb_kwargs: dict[str, Any],
    ) -> scrapy.Request:
        origin = "{0.scheme}://{0.netloc}".format(urlparse(page_url))
        return scrapy.Request(
            _GRAPHQL_URL,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "*/*",
                "Referer": f"{origin}/",
                "Origin": origin,
            },
            body=json.dumps(
                {"operationName": operation_name, "variables": variables, "query": query}
            ),
            callback=callback,
            cb_kwargs=cb_kwargs,
        )
