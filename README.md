# Apartment Scraper

[Scrapy](https://scrapy.org/) crawlers that collect apartment **availability** from
apartment community websites and export it to JSON. The JSON files in `data/` are
the source data for a (separate) static availability website.

Tooling: [uv](https://docs.astral.sh/uv/) for environment/dependency management and
[Ruff](https://docs.astral.sh/ruff/) for linting + formatting.

## Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/) (`uv --version`)
- Python 3.13 (uv will fetch it automatically if missing)

## Setup

```bash
uv sync
```

This creates a virtual environment in `.venv/` and installs Scrapy,
scrapy-playwright, and Ruff.

Some apartment sites only render their availability with JavaScript. The project is
already configured for [scrapy-playwright](https://github.com/scrapy-plugins/scrapy-playwright);
to scrape those sites, install the browser once:

```bash
uv run playwright install chromium
```

## Usage

List available spiders:

```bash
uv run scrapy list
```

Run a spider. Items are collected and written to a single
`data/availability.json`, sorted by community then unit:

```bash
uv run scrapy crawl example
```

> The included `example` spider is a template pointing at `example.com`; it will
> not return real data until you point it at a real site and update its selectors.

All spiders running in one process collect their items into a shared store, which
is written **once, after the last spider closes** — sorted by community then unit,
not once per spider. Each run **replaces** the output file (it is not merged with
earlier contents), so run every spider you want represented together in a single
process (e.g. one `CrawlerProcess`); a lone `scrapy crawl X` writes a file holding
just X's results.

## Scrape many communities at once

List the communities in `communities.toml` — each entry picks a spider (often a
shared platform spider) and passes per-community arguments to it:

```toml
[[communities]]
name = "Example Community"
spider = "example"
start_urls = ["https://example.com/floorplans"]
```

Then run them all in parallel — one process, so they share a single
`data/availability.json` (and a single browser):

`run.py` launches **one headed Chromium** that spiders can drive over CDP
(headed is needed to get past challenges such as Cloudflare). Headed needs a
display, so run it under a virtual one:

```bash
xvfb-run -a uv run python run.py             # uses communities.toml
xvfb-run -a uv run python run.py other.toml  # or a specific config file
```

`name` is passed to the spider as `community`; every key other than `name` and
`spider` is passed to the spider as a constructor argument (e.g. `start_urls`).

## Add a spider for a new apartment website

```bash
uv run scrapy genspider oakwood oakwoodapts.com
```

Then edit the generated file in `apartment_scraper/spiders/` to:

1. set `start_urls` to the availability/floor-plans page, and
2. parse each unit into an `ApartmentItem` (see `spiders/example_apartment.py`).

Each unit is yielded as an [`ApartmentItem`](apartment_scraper/items.py) with fields
like `community`, `unit`, `floor_plan`, `bedrooms`, `bathrooms`, `square_feet`,
`rent`, `available_date`, `url`, and `floor_plan_image_url`. The pipeline drops
records that are missing both a unit and a floor plan.

## Lint & format

```bash
uv run ruff check          # lint
uv run ruff check --fix    # lint + autofix
uv run ruff format         # format
```

## Project structure

```text
apartment_scraper/
├── __init__.py
├── items.py            # ApartmentItem data model
├── pipelines.py        # validation + single-file JSON export
├── settings.py         # politeness + output config
├── utils.py            # shared parsing helpers
└── spiders/
    └── example_apartment.py   # template spider
data/
├── availability.json   # combined output (sorted by community, then unit)
└── <YYYY>/<MM>/        # dated, gzipped daily snapshots
site/                   # Eleventy + Chart.js availability dashboard
scrapy.cfg              # Scrapy project config
pyproject.toml          # dependencies + Ruff config
```

## Availability dashboard

The [`site/`](site/) folder is a static [Eleventy](https://www.11ty.dev/)
dashboard that visualizes the scraped data with [Chart.js](https://www.chartjs.org/):
availability and rent trends over time, plus the current unit / floor-plan mix and
a filterable listings table. It reads the JSON snapshots in `data/` at build time.

```bash
cd site
npm install
npm run serve   # dev server at http://localhost:8080
npm run build   # static output in site/_site/
```

See [`site/README.md`](site/README.md) for details.
