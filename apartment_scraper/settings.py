"""Scrapy settings for the apartment_scraper project.

Only a curated subset of settings is shown here. For the full list see:
https://docs.scrapy.org/en/latest/topics/settings.html
"""

from typing import Any

LOG_LEVEL = "INFO"   # DEBUG | INFO | WARNING | ERROR | CRITICAL

BOT_NAME = "apartment_scraper"

SPIDER_MODULES = ["apartment_scraper.spiders"]
NEWSPIDER_MODULE = "apartment_scraper.spiders"

ADDONS = {}

ROBOTSTXT_OBEY = False

# Throttle requests so we do not hammer the apartment sites.
CONCURRENT_REQUESTS_PER_DOMAIN = 2
DOWNLOAD_DELAY = 1.0

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1.0
AUTOTHROTTLE_MAX_DELAY = 30.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

# --- Pipelines -------------------------------------------------------------
ITEM_PIPELINES = {
    "apartment_scraper.pipelines.AvailabilityPipeline": 300,
    "apartment_scraper.pipelines.SingleJsonExportPipeline": 800,
}

# --- JSON output -----------------------------------------------------------
# Every spider merges its results into this one file, sorted by community then
# unit. The static-site build reads this single file to render availability.
AVAILABILITY_OUTPUT = "data/availability.json"

# --- JavaScript rendering (scrapy-playwright) ------------------------------
# Only requests marked meta={"playwright": True} are routed through a browser;
# all other requests use the normal (fast) downloader. Needs a one-time
# `uv run playwright install chromium` (see README).
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}

# Always drive a *headed* browser: some targets (e.g. RentCafe behind Cloudflare)
# flag headless Chromium and never clear their challenge. Headed needs a display,
# so run under a virtual one (xvfb-run, see README). `run.py` goes further and
# launches a *single shared* headed browser for the whole run (it sets
# PLAYWRIGHT_CDP_URL, in which case these launch options are unused).
PLAYWRIGHT_LAUNCH_OPTIONS = {"headless": False, "args": ["--no-sandbox"]}
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 60000

# A real browser user agent + viewport; Scrapy's default UA is flagged by the bot
# challenges, after which they never clear.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
PLAYWRIGHT_CONTEXTS = {
    "default": {"viewport": {"width": 1366, "height": 900}, "locale": "en-US"},
}

# Speed up every browser-rendered page by aborting heavyweight sub-resources the
# spiders never read. They only need the page HTML/DOM or a captured data XHR, so
# the images, fonts, stylesheets and media a page pulls in are pure overhead.
PLAYWRIGHT_ABORT_RESOURCE_TYPES = {"image", "media", "font", "stylesheet"}


def _should_abort_request(request: Any) -> bool:
    """Return True to abort a Playwright request for an unused heavy resource.

    Documents, scripts and XHR/fetch are always kept so the page still renders
    and fires the requests the spiders rely on. Bot-challenge resources (e.g.
    Cloudflare's) are also always allowed through, so a challenged page (such as
    RentCafe's) can still clear instead of stalling.
    """
    challenge_markers = ("challenges.cloudflare.com", "/cdn-cgi/")
    if any(marker in request.url for marker in challenge_markers):
        return False
    return request.resource_type in PLAYWRIGHT_ABORT_RESOURCE_TYPES


PLAYWRIGHT_ABORT_REQUEST = _should_abort_request

# --- Modern defaults -------------------------------------------------------
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
