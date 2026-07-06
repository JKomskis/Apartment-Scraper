"""Data model for a single available apartment unit.

A dataclass-based Scrapy item keeps the schema explicit and type-checked while
still being serialized to JSON by Scrapy's feed exporter.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ApartmentItem:
    """One available unit at an apartment community."""

    community: str | None = None
    """Name of the apartment community / complex."""

    unit: str | None = None
    """Unit or apartment number, e.g. "B-204"."""

    floor_plan: str | None = None
    """Marketing name of the floor plan, e.g. "The Aspen"."""

    bedrooms: int | None = None
    """Number of bedrooms (use 0 for a studio)."""

    bathrooms: int | float | None = None
    """Number of bathrooms; a float only when there's a half bathroom (e.g. 1.5)."""

    square_feet: int | None = None
    """Interior size in square feet."""

    rent: int | None = None
    """Advertised monthly rent in dollars."""

    available_date: str | None = None
    """When the unit becomes available (ISO date or the site's raw text)."""

    url: str | None = None
    """Link to the unit / floor-plan listing."""

    floor_plan_image_url: str | None = None
    """Link to the floor-plan image / layout diagram."""
