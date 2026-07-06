# Common tasks for Apartment-Scraper.
#
# The Python crawlers are managed with uv; the static site (in site/) with npm.
# Run `make` (or `make help`) to list the available targets.
#
# `make scrape` uses xvfb-run because the spiders drive a *headed* browser and so
# need a display (install with `apt-get install xvfb`). On a desktop with a real
# display you can instead run `uv run python run.py` to watch the browser.

.DEFAULT_GOAL := help

# Optional config file for `make scrape`; run.py defaults to communities.toml.
CONFIG ?=

.PHONY: help install spiders scrape crawl lint fix format \
	site-install site-build site-serve site-clean clean

help: ## List the available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# --- Scraper (Python / uv) ---

install: ## Install Python deps + the Playwright Chromium browser
	uv sync
	uv run playwright install chromium

spiders: ## List the available spiders
	uv run scrapy list

crawl: ## Crawl every community into data/availability.json (make crawl CONFIG=other.toml)
	xvfb-run -a uv run python run.py $(CONFIG)

scrape: ## Run one spider standalone: make scrape SPIDER=avalon
	uv run scrapy crawl $(SPIDER)

lint: ## Check the Python code with ruff
	uv run ruff check

fix: ## Auto-fix lint issues with ruff
	uv run ruff check --fix

format: ## Format the Python code with ruff
	uv run ruff format

# --- Static site (Node / npm, in site/) ---

site-install: ## Install the site's npm dependencies
	cd site && npm install

site-build: ## Build the static site into site/_site
	cd site && npm run build

site-serve: ## Serve the site with live reload (http://localhost:8080)
	cd site && npm run serve

site-clean: ## Remove the built site output (site/_site)
	cd site && npm run clean

clean: site-clean ## Remove build artifacts
