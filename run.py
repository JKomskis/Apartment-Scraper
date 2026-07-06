"""Run spiders for several apartment communities in parallel.

Reads a TOML file that lists communities -- which spider each one uses plus any
per-community arguments -- and runs them all in a single Scrapy ``CrawlerProcess``.
Because they share one process, the export pipeline writes ``data/availability.json``
once, after the last spider finishes.

Usage:
    uv run python run.py [communities.toml]
"""

from __future__ import annotations

import contextlib
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

DEFAULT_CONFIG = Path("communities.toml")

# Keys consumed by the runner itself; every other key is passed to the spider.
RESERVED_KEYS = {"name", "spider"}


def load_communities(config_path: Path) -> list[dict[str, Any]]:
    """Read and validate the community entries from a TOML config file."""
    if not config_path.is_file():
        raise SystemExit(f"Config file not found: {config_path}")

    with config_path.open("rb") as config_file:
        config = tomllib.load(config_file)

    communities = config.get("communities", [])
    if not communities:
        raise SystemExit(f"No [[communities]] entries found in {config_path}")

    for entry in communities:
        missing = RESERVED_KEYS - entry.keys()
        if missing:
            raise SystemExit(f"Community {entry!r} is missing required key(s): {sorted(missing)}")

    return communities


# --- Shared browser --------------------------------------------------------
# scrapy-playwright launches one browser per crawler, so running several
# communities would spawn several browsers. Instead we launch a *single* headed
# Chromium with remote debugging enabled and point every spider at it (via
# PLAYWRIGHT_CDP_URL), so the whole run shares one browser process. Headed -- not
# headless -- is what gets past bot challenges such as Cloudflare, and that needs
# a display, so run under a virtual one (xvfb-run, see README).


def _free_port() -> int:
    """Pick an unused localhost TCP port for the browser's debugging endpoint."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _chromium_executable() -> str:
    """Path to the Chromium that ``playwright install`` downloaded."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        return playwright.chromium.executable_path


def _wait_for_cdp(cdp_url: str, timeout: float = 30.0) -> None:
    """Block until the browser's CDP endpoint is accepting connections."""
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{cdp_url}/json/version", timeout=2) as response:
                if response.status == 200:
                    return
        except Exception as error:  # noqa: BLE001 - keep polling until it is ready
            last_error = error
        time.sleep(0.3)
    raise SystemExit(
        f"Shared browser never exposed CDP at {cdp_url} ({last_error}). A display is "
        "required -- run under xvfb (e.g. `xvfb-run -a uv run python run.py`)."
    )


@contextlib.contextmanager
def shared_browser() -> Iterator[str]:
    """Launch one headed Chromium with CDP enabled and yield its CDP URL.

    The browser (and its temporary profile) is torn down when the run finishes.
    A fresh ``--user-data-dir`` is mandatory: recent Chromium refuses remote
    debugging on the default profile.
    """
    port = _free_port()
    profile_dir = tempfile.mkdtemp(prefix="apartment-scraper-chromium-")
    process = subprocess.Popen(
        [
            _chromium_executable(),
            f"--remote-debugging-port={port}",
            "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    cdp_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_cdp(cdp_url)
        yield cdp_url
    finally:
        process.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=10)
        if process.poll() is None:
            process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    config_path = Path(args[0]) if args else DEFAULT_CONFIG

    communities = load_communities(config_path)

    settings = get_project_settings()
    # Every spider connects to this one headed browser over CDP instead of
    # launching its own (see shared_browser).
    with shared_browser() as cdp_url:
        settings.set("PLAYWRIGHT_CDP_URL", cdp_url, priority="cmdline")
        process = CrawlerProcess(settings)
        for entry in communities:
            spider_kwargs = {key: value for key, value in entry.items() if key not in RESERVED_KEYS}
            # `name` becomes the spider's `community`; the rest are spider arguments.
            process.crawl(entry["spider"], community=entry["name"], **spider_kwargs)

        # crawl() schedules each spider; start() runs them all concurrently and blocks
        # until every spider has finished (then the pipeline writes the output file).
        process.start()


if __name__ == "__main__":
    main()
