---
name: create-apartment-spider
description: "Investigate an apartment community listing page and generate a Scrapy spider that extracts every unit into the project ApartmentItem. USE FOR: create or add a spider for an apartment site, scrape an apartments / floor-plans / availability page, build a spider from a URL, find the availability API behind a dynamic page, handle JavaScript-rendered listings. Uses the chrome-devtools-mcp network tools (list_network_requests, get_network_request) to find the data source, following Scrapy dynamic-content principles: reproduce the backend request, with a headless browser only as a last resort."
---

# Create an Apartment Spider from a Listing Page

Given the URL of a page that lists the available units / floor plans for **one
apartment community**, investigate how the page serves its data and generate a
Scrapy spider in this project that yields one `ApartmentItem` per available unit.

Guiding principle (from Scrapy's *Selecting dynamically-loaded content*): **find the
real data source and reproduce that request.** It yields structured, complete data
with minimal parsing and network transfer. Fall back to a headless browser only when
the request genuinely cannot be reproduced.

## Prerequisites

- This Scrapy + `uv` project. Run every command with `uv run`.
- The `chrome-devtools-mcp` server, configured in `.vscode/mcp.json`. After the first
  setup, reload the VS Code window (or restart the MCP server) so its tools load.
  Requires **Node.js LTS** (provides `npx`) and **Chrome**. On a headless server the
  config already passes `--headless --isolated`; remove `--headless` to watch the
  browser, and add `--executablePath=/usr/bin/google-chrome` (or `--channel=stable`)
  if Chrome is not auto-detected.
- Item schema lives in `apartment_scraper/items.py` (`ApartmentItem`); numeric
  parsing helpers `to_float` / `to_int` live in `apartment_scraper/utils.py`. Spiders
  only need to `yield` items — the pipeline collects them and writes
  `data/availability.json`.

## Workflow

### 0. Reuse an existing spider if one already fits

Before building anything new, look at the spiders already in
`apartment_scraper/spiders/` (`uv run scrapy list`). Apartment communities frequently
share a hosting platform (RealPage, Entrata, Yardi/RentCafe, Funnel, AppFolio, …), so
a spider written for one community often works for another with only a different start
URL, community name, or property ID.

- Identify the platform first: check the page source or the data-request host/path
  (step 2 makes this obvious) for a vendor domain or marker.
- If an existing spider already targets that platform, prefer **extending it**
  (parameterize the community name + property ID/URL, or add the new start URL) over
  writing a brand-new spider.
- Only continue to step 1 when no existing spider fits.

### 1. Triage — is the data in the HTML that Scrapy sees?

Download exactly what Scrapy downloads (this is the page source, **not** the rendered
browser DOM):

```bash
uv run scrapy fetch --nolog "<LISTING_URL>" > /tmp/page.html
```

Search `/tmp/page.html` for a known unit number, rent, or floor-plan name shown on
the page.

- **Found** → the page is static. Go to step 4b (parse HTML with selectors).
- **Not found** → the data is loaded dynamically. Go to step 2 to find its source.

You can also explore selectors interactively: `uv run scrapy shell "<LISTING_URL>"`.

### 2. Find the data source with chrome-devtools-mcp

Open the page in the controlled browser and inspect its network traffic:

1. `new_page` (or `navigate_page`) → `<LISTING_URL>`.
2. `wait_for` the unit/price text so the data-loading requests have fired.
3. `list_network_requests` with `resourceTypes: ["fetch", "xhr"]` to list just the
   data/API calls (skipping images, CSS, fonts). Paginate with `pageIdx` / `pageSize`
   if there are many; set `includePreservedRequests: true` to keep requests across
   navigations.
4. For each promising request, call `get_network_request` with its `reqid` to inspect
   the URL, method, query string, request headers, request body, and — crucially —
   the **response body**. The right request returns JSON (or HTML) containing the
   units / floor plans.

What to look for and record:

- Availability data is usually a JSON `fetch` / `xhr` call. Common apartment
  platforms (RealPage, Entrata, Yardi/RentCafe, Funnel, AppFolio, …) all expose one.
- **Pagination** params (`page` / `offset` / `limit` / cursor) — you must reproduce
  them to get every unit.
- **Required headers / cookies** (`Referer`, `X-Requested-With`, `Authorization`,
  API keys, CSRF tokens). If the endpoint needs them, the Scrapy request must send
  them too.
- If the data is instead embedded in the original HTML inside a `<script>` (e.g.
  `window.__INITIAL_STATE__ = {…}`), there is **no extra request** — extract it from
  the script text in the spider.

### 3. Choose the extraction strategy

| What you found | Spider strategy |
|---|---|
| Units already in the static HTML | Request the page, parse with CSS/XPath selectors (4b) |
| A JSON API `fetch`/`xhr` request | **Reproduce that request** (preferred) — hit the endpoint directly, parse `response.json()` (4a) |
| JSON embedded in a `<script>` tag | Request the page, extract the script text, `json.loads` / `chompjs` (4a variant) |
| Data only appears after JS runs *and* the request can't be reproduced | Headless browser via `scrapy-playwright` — last resort (4c) |

### 4a. Reproduce a request (preferred)

In browser DevTools you can right-click the request → **Copy as cURL**. Scrapy turns
that straight into a request, preserving method, headers, and body:

```python
from scrapy import Request

request = Request.from_curl(curl_command_string)
```

(There is also the web tool **curl2scrapy** if you want to convert offline.)

Spider skeleton for an **API/JSON** source. Keep the spider generic and reusable —
the community's `start_urls` (the *data endpoint* you found in step 2, not the
human-facing page) and `community` name live in `communities.toml`, **not**
hardcoded in the spider:

```python
from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

import scrapy
from scrapy.http import Response

from apartment_scraper.items import ApartmentItem
from apartment_scraper.utils import to_float, to_int


class OakwoodSpider(scrapy.Spider):
    name = "oakwood"
    # Per-community config comes from communities.toml (via run.py); nothing
    # site-specific is hardcoded, so the same spider serves every community on
    # this platform.
    community: str | None = None
    start_urls: list[str] = []

    # Send any headers the browser request required (from get_network_request):
    custom_settings = {
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "application/json",
            "Referer": "https://oakwoodapts.com/floorplans",
        },
    }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.allowed_domains = [urlparse(url).netloc for url in self.start_urls]

    def parse(self, response: Response, **kwargs: Any) -> Iterator[Any]:
        data = response.json()
        for unit in data["units"]:
            yield ApartmentItem(
                community=self.community,
                unit=unit.get("unitNumber"),
                floor_plan=unit.get("floorplanName"),
                bedrooms=unit.get("beds"),            # often already numeric
                bathrooms=unit.get("baths"),
                square_feet=to_int(str(unit.get("sqft"))),
                rent=to_int(str(unit.get("rent"))),   # strips "$", ",", "/mo"
                available_date=unit.get("availableDate"),
                url=response.urljoin(unit.get("url", "")),
                floor_plan_image_url=response.urljoin(unit.get("image", "")),
            )

        # Reproduce pagination exactly as the site does it:
        if data.get("hasNextPage"):
            yield response.follow(data["nextPageUrl"], callback=self.parse)
```

Register the community in `communities.toml` — the runner passes `name` to the
spider as `community` and every other key (here `start_urls`) as a spider argument:

```toml
[[communities]]
name = "Oakwood"
spider = "oakwood"
start_urls = ["https://oakwoodapts.com/api/floorplans?page=1"]
```

Notes:
- Match the captured request: same method, query params, and required headers/cookies.
- For POST / GraphQL endpoints, send the same body with
  `Request(method="POST", body=…, headers=…)` or `scrapy.FormRequest`.
- For JSON embedded in a `<script>`: `raw = response.css("script::text").re_first(r"__INITIAL_STATE__\s*=\s*(\{.*\})")`
  then `json.loads(raw)` (or use `chompjs.parse_js_object` for non-strict JS objects).

### 4b. Parse static HTML

Mirror the template in `apartment_scraper/spiders/example_apartment.py`: iterate the
per-unit elements and map each into an `ApartmentItem`, using `to_float` / `to_int`
for the numeric fields. Verify each selector in `scrapy shell` first. As in 4a, keep
the `start_urls` and `community` in `communities.toml`, not hardcoded in the spider.

### 4c. Headless browser (last resort)

Only when the request cannot be reproduced (heavy anti-bot, signed/short-lived params,
or data assembled by JS). The project is already set up for `scrapy-playwright`
(download handlers + asyncio reactor are configured); the only prerequisite is the
one-time browser install, `uv run playwright install chromium` (see the README).

To render a request, mark it with `meta={"playwright": True}` and parse `response` as
usual — requests without the flag still use the normal (fast) downloader:

```python
yield scrapy.Request(url, meta={"playwright": True}, callback=self.parse)
```

### 5. Configure, run, and verify

1. Scaffold: `uv run scrapy genspider <name> <domain>`, then replace the body — or add
   the file directly under `apartment_scraper/spiders/`.
2. Map every `ApartmentItem` field you can; leave unknown fields as `None`. **Keep the
   spider generic** — don't hardcode the community name or start URL(s); the spider
   reads them from the arguments the runner passes (next step), so one spider can serve
   every community on the same platform.
3. Register the community in `communities.toml` (`name` → the spider's `community`;
   `start_urls` → the listing page or data endpoint; any platform id the spider needs
   goes in as an extra key):

   ```toml
   [[communities]]
   name = "<Community Name>"
   spider = "<name>"
   start_urls = ["<LISTING_OR_API_URL>"]
   ```

4. Run: `uv run python run.py` → crawls every configured community and writes
   `data/availability.json`.
5. Verify: the item count matches what the page shows; `rent` and `square_feet` are
   numbers; `available_date` is populated. Chase down any unexpected `null`s by
   re-checking the JSON paths / selectors.
6. Lint: `uv run ruff check` and `uv run ruff format`.

Add more communities — including ones that reuse an existing spider — as extra
`[[communities]]` entries; they crawl in parallel and write `data/availability.json`
together (see the README).

## Field mapping (`ApartmentItem`)

| Field | Source on the page/API | Notes |
|---|---|---|
| `community` | community / property name | from `communities.toml` (the entry's `name`) |
| `unit` | unit / apartment number | the pipeline drops items missing **both** `unit` and `floor_plan` |
| `floor_plan` | floor-plan / layout name | |
| `bedrooms` | bed count | `to_float` if it is text like "1 Bed"; studio = 0 |
| `bathrooms` | bath count | `to_float` (e.g. 1.5) |
| `square_feet` | size | `to_int` |
| `rent` | monthly rent | `to_int` (strips `$`, `,`, `/mo`) |
| `available_date` | move-in / available date | ISO date or the site's raw text |
| `url` | link to the unit / floor plan | wrap with `response.urljoin(...)` |
| `floor_plan_image_url` | floor-plan image | wrap with `response.urljoin(...)` |

## chrome-devtools-mcp network tools

- **`list_network_requests`** — all requests for the selected page since the last
  navigation. Filter with `resourceTypes: ["fetch", "xhr"]`, paginate with
  `pageIdx` / `pageSize`, and pass `includePreservedRequests: true` to retain requests
  across navigations. Use it to spot the data/API call among the noise.
- **`get_network_request`** — full detail (URL, method, headers, request body,
  response body) for a single request by `reqid`. Use it to confirm the endpoint, its
  pagination params, and the response JSON shape before reproducing it in Scrapy.
  (The tool name is singular — `get_network_request`.)

## References

- Scrapy — Selecting dynamically-loaded content:
  <https://docs.scrapy.org/en/latest/topics/dynamic-content.html>
  (finding the data source, reproducing requests, `Request.from_curl()`, handling
  JSON / JavaScript responses, headless browser)
- chrome-devtools-mcp tool reference:
  <https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/tool-reference.md>
