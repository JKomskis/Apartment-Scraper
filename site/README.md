# Availability dashboard (Eleventy + Chart.js)

A static dashboard that visualizes the apartment availability data collected by
the scraper. [Eleventy](https://www.11ty.dev/) builds the site at compile time,
reading the JSON snapshots the scraper archives under the repository's `data/`
folder, [Chart.js](https://www.chartjs.org/) draws the charts, and
[Vite](https://vite.dev/) (via `@11ty/eleventy-plugin-vite`) bundles the
JavaScript and CSS.

## What it shows

The site has two sections:

### Overview (`/`)

A trends-over-time dashboard:

- **Key metrics** — available units, communities tracked, and median / average /
  low / high rent for the latest snapshot.
- **Available units over time** — stacked bars by community (one bar per daily
  snapshot).
- **Average rent over time** — overall trend plus a dashed line per community.
- **Bedrooms filter** — a dropdown that re-draws both charts for a single
  floor-plan size (Studio / 1 BR / …) or all bedrooms.

The current-snapshot breakdown charts and the full unit listing live on the
snapshot pages (the latest day is one click away under **Snapshots**).

### Snapshots (`/snapshots/`)

- A **list of every day** of archived data (newest first).
- One **page per day** at `/snapshots/<date>/` with that day's metrics, charts
  (community / size doughnuts, average-rent-by-size, rent distribution) with a
  **Bedrooms filter**, and the full listings table — filterable (search +
  Community / Beds / Baths) and **sortable** (click any column header; click
  again to reverse) — plus **previous / next** links to neighbouring days.

## Where the data comes from

At build time, [lib/aggregate.js](lib/aggregate.js):

1. Recursively reads every dated snapshot under `data/<YYYY>/<MM>/`
   (`*_YYYY_MM_DD.json.gz` / `.json.gzip`, transparently gunzipped) to build the
   time series.
2. Uses the most recent snapshot for the "current state" cards, doughnuts, and
   listings table. (It is identical to the live `data/availability.json`, so that
   file is not read separately.)

Both the dashboard time series and each snapshot's charts are pre-computed once
**per bedroom count** (plus an "all" bucket), so the Bedrooms dropdown just swaps
which pre-aggregated dataset the charts draw — no client-side re-aggregation.

Two Eleventy data files expose it to templates: [src/_data/availability.js](src/_data/availability.js)
(`buildDashboard` — the overview) and [src/_data/snapshots.js](src/_data/snapshots.js)
(`buildSnapshots` — one entry per day, each with prev/next links).

The data directory defaults to `../data` (the repo root's `data/` folder) and can
be overridden with the `DATA_DIR` environment variable.

## Develop

```bash
cd site
npm install
npm run serve   # live-reloading dev server at http://localhost:8080
```

## Build

```bash
cd site
npm run build   # writes the static site to site/_site/
```

Serve `_site/` with any static file host. The pages use root-relative asset paths,
so serve from the site root (e.g. `npx @11ty/eleventy --serve`) rather than opening
`_site/index.html` directly via `file://`. To host under a sub-path (for example a
GitHub Pages project site), set the `BASE_PATH` environment variable — it drives
both Eleventy's path prefix (page links) and Vite's base (bundled asset URLs):

```bash
BASE_PATH=/Apartment-Scraper/ npm run build
```

## Deploy (GitHub Pages)

[.github/workflows/build-site.yml](../.github/workflows/build-site.yml) builds the
production site on every push to `main` (the daily scrape commits new snapshots,
triggering a redeploy) and on manual dispatch. It builds with
`BASE_PATH=/Apartment-Scraper/` and publishes `site/_site/` to the root of the
`gh-pages` branch.

[.github/workflows/preview-site.yml](../.github/workflows/preview-site.yml) builds
every pull request with its own base path and publishes a preview at
`https://jkomskis.github.io/Apartment-Scraper/pr-preview/pr-<number>/`. The action
adds or updates a sticky preview link on the pull request, rebuilds it after new
commits, and removes its files when the pull request closes.

Before building, it calls
[.github/workflows/daily-scrape.yml](../.github/workflows/daily-scrape.yml) in
preview mode against the PR's exact commit. That runs every community configured
by the PR (including newly added spiders), creates a current UTC-dated snapshot,
and passes the refreshed `data/` directory to the Eleventy build as a temporary
artifact. Preview-mode scrape results are never committed to the repository.

Fork pull requests are supported without exposing a write token to their code:
the untrusted scrape and build run in isolated read-only jobs with dependency
caches disabled, and a fresh job deploys only the resulting static artifact.

One-time setup (after the production workflow has created `gh-pages`): open the
repository's **Settings → Pages → Build and deployment**, choose **Deploy from a
branch**, select **gh-pages** and **/(root)**, then save. Both workflows use
non-force pushes, and production deployments preserve the `pr-preview/`
directory so active previews remain available.

## How it's wired

- [eleventy.config.js](eleventy.config.js) — input/output dirs, a `jsonify` filter
  for safely embedding data in a `<script>` tag, and the `@11ty/eleventy-plugin-vite`
  plugin (Vite bundles/hashes the JS + CSS). The `/scripts/*` module URLs are
  resolved to `src/scripts` via a Vite `resolve.alias`; the stylesheet is exposed
  to Vite with a passthrough copy of `src/styles`. `BASE_PATH` sets Eleventy's
  `pathPrefix` (page links, via the `url` filter) and Vite's `base` (asset URLs);
  asset tags in `base.njk` are deliberately plain (no `url` filter) so Vite — not
  the path prefix — rewrites them, keeping the `/scripts` alias resolvable.
- [lib/aggregate.js](lib/aggregate.js) — shared loading + aggregation used by both
  data files.
- [src/_includes/base.njk](src/_includes/base.njk) — page shell (small header +
  nav); embeds the per-page chart payload and loads the page script
  (`dashboard.js` or `snapshot.js`) as an ES module.
- [src/_includes/partials/listings.njk](src/_includes/partials/listings.njk) —
  the reusable listings-table macro shared by the overview and snapshot pages.
- [src/index.njk](src/index.njk) — the overview dashboard.
- [src/snapshots.njk](src/snapshots.njk) — the snapshots list;
  [src/snapshot.njk](src/snapshot.njk) — the per-day page (Eleventy pagination,
  one page per snapshot).
- [src/scripts/charts.js](src/scripts/charts.js) — a small, Chart.js-agnostic
  shared module: colour palette, DOM helpers, the `htmlLegend` plugin (renders
  clickable legends as HTML into a `<div id="<canvasId>-legend">`), an
  `applyDefaults(Chart)` configurator, and the listings-table filters.
- [src/scripts/dashboard.js](src/scripts/dashboard.js) (over-time bar + line) and
  [src/scripts/snapshot.js](src/scripts/snapshot.js) (doughnut + bar) each
  `import` and `register` only the Chart.js controllers/elements/scales their own
  charts need — so Chart.js is tree-shaken to just the pieces in use (no
  `chart.js/auto`), and each page carries only its own chart code.
