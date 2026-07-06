"use strict";

/**
 * Shared, build-time aggregation for the availability dashboard.
 *
 * Both the overview dashboard (`_data/availability.js`) and the per-day snapshot
 * pages (`_data/snapshots.js`) are derived from the same source: the dated,
 * gzipped snapshots the scraper archives under `data/<YYYY>/<MM>/`. The most
 * recent snapshot doubles as the overview's "current" cards and charts — it is
 * identical to the live `data/availability.json`, so that file is not read here.
 * Keeping the loading and summarising logic in one module avoids the two data
 * files drifting apart.
 *
 * The data directory defaults to the repository's `data/` folder (two levels up
 * from this file) but can be overridden with the DATA_DIR environment variable.
 */

const fs = require("node:fs");
const path = require("node:path");
const zlib = require("node:zlib");

// Snapshot files carry the capture date in their name, e.g.
// `availability_2026_06_30.json.gzip` or `inventory_2026_06_30.json.gz`.
const SNAPSHOT_RE = /_(\d{4})[_-](\d{2})[_-](\d{2})\.json(\.gz(?:ip)?)?$/i;

function defaultDataDir() {
  return process.env.DATA_DIR
    ? path.resolve(process.env.DATA_DIR)
    : path.resolve(__dirname, "../../data");
}

/** Recursively collect snapshot file paths beneath `dir`. */
function findSnapshots(dir) {
  let entries;
  try {
    entries = fs.readdirSync(dir, { recursive: true, withFileTypes: true });
  } catch {
    return [];
  }
  return entries
    .filter((entry) => entry.isFile() && SNAPSHOT_RE.test(entry.name))
    .map((entry) => path.join(entry.parentPath, entry.name));
}

/** Parse the ISO date (YYYY-MM-DD) encoded in a snapshot file name. */
function dateFromName(name) {
  const m = name.match(SNAPSHOT_RE);
  return m ? `${m[1]}-${m[2]}-${m[3]}` : null;
}

/** Read a snapshot file, transparently gunzipping `.gz` / `.gzip` archives. */
function loadSnapshot(file) {
  const raw = fs.readFileSync(file);
  const text = /\.gz(?:ip)?$/i.test(file)
    ? zlib.gunzipSync(raw).toString("utf8")
    : raw.toString("utf8");
  const records = JSON.parse(text);
  return Array.isArray(records) ? records : [];
}

const mean = (nums) =>
  nums.length ? nums.reduce((a, b) => a + b, 0) / nums.length : null;

function median(nums) {
  if (!nums.length) return null;
  const sorted = [...nums].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function bedroomLabel(bedrooms) {
  if (bedrooms === 0) return "Studio";
  if (bedrooms === null || bedrooms === undefined) return "Unknown";
  return `${bedrooms} BR`;
}

// Studio first, then bedroom count ascending, Unknown last.
function bedroomSortKey(label) {
  if (label === "Studio") return -1;
  if (label === "Unknown") return Number.POSITIVE_INFINITY;
  const n = Number.parseFloat(label);
  return Number.isNaN(n) ? 1e6 : n;
}

// Records whose bedroom label matches `bed` ("all" keeps every record).
function filterByBedroom(records, bed) {
  return bed === "all"
    ? records
    : records.filter((r) => bedroomLabel(r.bedrooms) === bed);
}

// Distinct bedroom labels in `records`, ordered Studio < N BR < Unknown.
function distinctBedrooms(records) {
  const set = new Set();
  for (const r of records) set.add(bedroomLabel(r.bedrooms));
  return [...set].sort((a, b) => bedroomSortKey(a) - bedroomSortKey(b));
}

const numericRents = (records) =>
  records
    .map((r) => r.rent)
    .filter((r) => typeof r === "number" && !Number.isNaN(r));

/** Aggregate one snapshot's records into the numbers the dashboard needs. */
function summarize(records) {
  const rents = numericRents(records);

  const byCommunity = {};
  const byBedrooms = {};
  const rentsByCommunity = {};
  const rentsByBedrooms = {};

  for (const r of records) {
    const community = r.community || "Unknown";
    byCommunity[community] = (byCommunity[community] || 0) + 1;

    const beds = bedroomLabel(r.bedrooms);
    byBedrooms[beds] = (byBedrooms[beds] || 0) + 1;

    if (typeof r.rent === "number" && !Number.isNaN(r.rent)) {
      (rentsByCommunity[community] ||= []).push(r.rent);
      (rentsByBedrooms[beds] ||= []).push(r.rent);
    }
  }

  const roundMap = (obj) =>
    Object.fromEntries(
      Object.entries(obj).map(([k, v]) => [k, Math.round(mean(v))]),
    );

  return {
    totalUnits: records.length,
    avgRent: mean(rents),
    medianRent: median(rents),
    minRent: rents.length ? Math.min(...rents) : null,
    maxRent: rents.length ? Math.max(...rents) : null,
    byCommunity,
    byBedrooms,
    avgRentByCommunity: roundMap(rentsByCommunity),
    avgRentByBedrooms: roundMap(rentsByBedrooms),
  };
}

/** Bucket rents into fixed-width bins for a distribution histogram. */
function buildHistogram(rents, bucketSize = 250) {
  const sorted = [...rents].sort((a, b) => a - b);
  if (!sorted.length) return { labels: [], counts: [] };

  const min = Math.floor(sorted[0] / bucketSize) * bucketSize;
  const max = Math.ceil((sorted[sorted.length - 1] + 1) / bucketSize) * bucketSize;
  const buckets = [];
  for (let start = min; start < max; start += bucketSize) {
    buckets.push({ start, end: start + bucketSize, count: 0 });
  }
  if (!buckets.length) buckets.push({ start: min, end: min + bucketSize, count: 0 });

  for (const rent of sorted) {
    let idx = Math.floor((rent - min) / bucketSize);
    if (idx < 0) idx = 0;
    if (idx >= buckets.length) idx = buckets.length - 1;
    buckets[idx].count += 1;
  }

  return {
    labels: buckets.map(
      (b) => `$${b.start.toLocaleString()}\u2013${b.end.toLocaleString()}`,
    ),
    counts: buckets.map((b) => b.count),
  };
}

const orderedBedrooms = (summary) =>
  Object.keys(summary.byBedrooms).sort((a, b) => bedroomSortKey(a) - bedroomSortKey(b));

const orderedCommunities = (summary) =>
  Object.keys(summary.byCommunity).sort(
    (a, b) => summary.byCommunity[b] - summary.byCommunity[a],
  );

/** Client-ready chart payload (doughnuts, bar, histogram) for one snapshot. */
function chartPayload(records, summary = summarize(records)) {
  const bedroomLabels = orderedBedrooms(summary);
  const communityLabels = orderedCommunities(summary);
  return {
    communityLabels,
    communityCounts: communityLabels.map((c) => summary.byCommunity[c]),
    bedroomLabels,
    bedroomCounts: bedroomLabels.map((b) => summary.byBedrooms[b]),
    bedroomAvgRent: bedroomLabels.map((b) => summary.avgRentByBedrooms[b] ?? null),
    histogram: buildHistogram(numericRents(records)),
  };
}

/** Listings sorted by community, then rent ascending. */
function sortListings(records) {
  return [...records].sort((a, b) => {
    const byName = (a.community || "").localeCompare(b.community || "");
    if (byName) return byName;
    return (a.rent ?? Infinity) - (b.rent ?? Infinity);
  });
}

/** Load every snapshot keyed by capture date. */
function loadByDate(dataDir) {
  const byDate = new Map();
  for (const file of findSnapshots(dataDir)) {
    const date = dateFromName(path.basename(file));
    if (!date) continue;
    try {
      byDate.set(date, loadSnapshot(file));
    } catch (err) {
      console.warn(`[aggregate] skipping ${file}: ${err.message}`);
    }
  }
  return byDate;
}

/** Overview dashboard data: per-bedroom time series across all days. */
function buildDashboard(dataDir = defaultDataDir()) {
  const byDate = loadByDate(dataDir);
  const dates = [...byDate.keys()].sort();

  // Union of communities and bedroom labels across every record.
  const communitySet = new Set();
  const bedroomSet = new Set();
  for (const records of byDate.values()) {
    for (const r of records) {
      communitySet.add(r.community || "Unknown");
      bedroomSet.add(bedroomLabel(r.bedrooms));
    }
  }
  const communities = [...communitySet].sort();
  const bedroomOptions = [
    "all",
    ...[...bedroomSet].sort((a, b) => bedroomSortKey(a) - bedroomSortKey(b)),
  ];

  // Over-time series for one bedroom filter ("all" == every unit).
  function seriesForBedroom(bed) {
    const summaries = dates.map((date) =>
      summarize(filterByBedroom(byDate.get(date), bed)),
    );
    const unitsByCommunityOverTime = {};
    const avgRentByCommunityOverTime = {};
    for (const community of communities) {
      unitsByCommunityOverTime[community] = summaries.map(
        (s) => s.byCommunity[community] || 0,
      );
      avgRentByCommunityOverTime[community] = summaries.map(
        (s) => s.avgRentByCommunity[community] ?? null,
      );
    }
    return {
      avgRent: summaries.map((s) => (s.avgRent == null ? null : Math.round(s.avgRent))),
      unitsByCommunityOverTime,
      avgRentByCommunityOverTime,
    };
  }
  const byBedroom = {};
  for (const bed of bedroomOptions) byBedroom[bed] = seriesForBedroom(bed);

  const latestDate = dates.length ? dates[dates.length - 1] : null;
  const currentSummary = summarize(latestDate ? byDate.get(latestDate) : []);

  return {
    generatedAt: new Date().toISOString(),
    dataDir,
    snapshotCount: dates.length,
    firstDate: dates.length ? dates[0] : null,
    latestDate,
    communities,
    current: { ...currentSummary },
    charts: {
      dates,
      communities,
      bedroomOptions,
      byBedroom,
    },
  };
}

/**
 * One entry per day of data, oldest first, each carrying that day's full
 * details plus links to the previous (older) and next (newer) snapshot.
 */
function buildSnapshots(dataDir = defaultDataDir()) {
  const byDate = loadByDate(dataDir);
  const dates = [...byDate.keys()].sort();

  return dates.map((date, i) => {
    const records = byDate.get(date);
    const summary = summarize(records);
    const prevDate = i > 0 ? dates[i - 1] : null;
    const nextDate = i < dates.length - 1 ? dates[i + 1] : null;

    // Pre-compute a chart payload for every bedroom filter ("all" + each size)
    // so the page can switch the charts client-side without re-aggregating.
    const options = distinctBedrooms(records);
    const byBedroom = { all: chartPayload(records, summary) };
    for (const bed of options) {
      byBedroom[bed] = chartPayload(filterByBedroom(records, bed));
    }

    return {
      date,
      slug: date,
      url: `/snapshots/${date}/`,
      totalUnits: summary.totalUnits,
      communityCount: Object.keys(summary.byCommunity).length,
      avgRent: summary.avgRent,
      medianRent: summary.medianRent,
      minRent: summary.minRent,
      maxRent: summary.maxRent,
      listings: sortListings(records),
      charts: { bedroomOptions: ["all", ...options], byBedroom },
      prev: prevDate ? { date: prevDate, url: `/snapshots/${prevDate}/` } : null,
      next: nextDate ? { date: nextDate, url: `/snapshots/${nextDate}/` } : null,
    };
  });
}

module.exports = { buildDashboard, buildSnapshots };
