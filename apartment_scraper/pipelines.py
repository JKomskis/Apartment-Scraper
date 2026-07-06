"""Item pipelines.

See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem

if TYPE_CHECKING:
    from scrapy import Spider
    from scrapy.crawler import Crawler


class AvailabilityPipeline:
    """Drop incomplete availability records."""

    def process_item(self, item: object, spider: Spider) -> object:
        adapter = ItemAdapter(item)

        # A unit with neither an identifier nor a floor plan is not useful.
        if not adapter.get("unit") and not adapter.get("floor_plan"):
            raise DropItem("Missing unit / floor_plan identifier")

        return item


def _sort_key(record: dict[str, Any]) -> tuple[str, str]:
    """Sort by community, then unit (ascending, case-insensitive)."""
    return (
        (record.get("community") or "").casefold(),
        (record.get("unit") or "").casefold(),
    )


class SingleJsonExportPipeline:
    """Collect every spider's items and write one sorted JSON file per process.

    Items from all spiders running in the same process are gathered into shared
    class-level state and written to ``AVAILABILITY_OUTPUT`` (default
    ``data/availability.json``) when the last spider closes -- sorted by community
    then unit. Each run replaces the file; it is not merged with earlier contents.

    The state is class-level because Scrapy creates a separate pipeline instance
    per spider, and one ``CrawlerProcess`` may run several spiders at once.
    """

    _lock: ClassVar = threading.Lock()
    _records: ClassVar[list[dict[str, Any]]] = []
    _open_spiders: ClassVar[int] = 0
    _output_path: ClassVar[str] = "data/availability.json"

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> SingleJsonExportPipeline:
        output = crawler.settings.get("AVAILABILITY_OUTPUT", "data/availability.json")
        with cls._lock:
            cls._output_path = output
        return cls()

    def open_spider(self, spider: Spider) -> None:
        cls = type(self)
        with cls._lock:
            cls._open_spiders += 1

    def process_item(self, item: object, spider: Spider) -> object:
        record = ItemAdapter(item).asdict()
        cls = type(self)
        with cls._lock:
            cls._records.append(record)
        return item

    def close_spider(self, spider: Spider) -> None:
        cls = type(self)
        with cls._lock:
            cls._open_spiders -= 1
            if cls._open_spiders <= 0:
                cls._write()

    @classmethod
    def _write(cls) -> None:
        """Write all collected records, sorted, replacing the file.

        The caller must hold ``cls._lock``.
        """
        output_path = Path(cls._output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        records = sorted(cls._records, key=_sort_key)
        output_path.write_text(
            json.dumps(records, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
