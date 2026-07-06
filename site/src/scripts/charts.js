/*
 * Shared, Chart.js-agnostic helpers: colour palette, small DOM helpers, the HTML
 * legend plugin, a defaults configurator, and the listings-table filters.
 *
 * This module imports NOTHING from chart.js, so it stays a tiny shared chunk.
 * Each page entry (dashboard.js / snapshot.js) imports and registers only the
 * Chart.js controllers/elements/scales its own charts need and owns its
 * chart-building code, so a page bundles only the parts of Chart.js it uses.
 */

/*
 * Chart.js plugin that renders a chart's legend as clickable HTML *outside* the
 * canvas. Set `options.plugins.htmlLegend.containerID` to a DOM element id and
 * disable the built-in legend (`legend.display = false`); clicking a legend item
 * toggles that segment/series. Adapted from Car-Inventory-Scraper's chart-setup.
 */
export const htmlLegendPlugin = {
  id: "htmlLegend",
  afterUpdate(chart, _args, options) {
    const container = document.getElementById(options.containerID);
    if (!container) return;

    container.innerHTML = "";

    const ul = document.createElement("ul");
    ul.className = "chart-legend";

    const items = chart.options.plugins.legend.labels.generateLabels(chart);

    items.forEach((item) => {
      const li = document.createElement("li");
      li.className = "chart-legend-item";
      if (item.hidden) li.classList.add("legend-hidden");

      // Colour swatch (prefer a non-transparent fill/stroke).
      const swatch = document.createElement("span");
      swatch.className = "legend-swatch";
      const skip = new Set(["transparent", "#fff", "#ffffff", "rgba(0,0,0,0)"]);
      const usable = (c) => c && !skip.has(c.toLowerCase().replace(/\s/g, ""));
      swatch.style.background =
        [item.fillStyle, item.strokeStyle].find(usable) ||
        item.fillStyle ||
        item.strokeStyle;

      const label = document.createElement("span");
      label.className = "legend-label";
      label.textContent = item.text;

      // Toggle visibility on click (per-segment for pie/doughnut, per-dataset
      // otherwise).
      li.addEventListener("click", () => {
        const { type } = chart.config;
        if (type === "pie" || type === "doughnut") {
          chart.toggleDataVisibility(item.index);
        } else {
          chart.setDatasetVisibility(
            item.datasetIndex,
            !chart.isDatasetVisible(item.datasetIndex),
          );
        }
        chart.update();
      });

      li.appendChild(swatch);
      li.appendChild(label);
      ul.appendChild(li);
    });

    container.appendChild(ul);
  },
};

const PALETTE = [
  "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
  "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
  "#86bcb6", "#8cd17d", "#b6992d", "#499894", "#d37295",
];

export function color(i) {
  return PALETTE[i % PALETTE.length];
}

export function withAlpha(hex, alpha) {
  var n = parseInt(hex.slice(1), 16);
  return (
    "rgba(" +
    ((n >> 16) & 255) + "," +
    ((n >> 8) & 255) + "," +
    (n & 255) + "," +
    alpha + ")"
  );
}

export function byId(id) {
  return document.getElementById(id);
}

export function money(value) {
  return "$" + Math.round(value).toLocaleString("en-US");
}

// Apply shared Chart.js defaults on the given Chart class. Call after the page
// registers its components (legend label defaults need the Legend plugin first).
export function applyDefaults(Chart) {
  Chart.defaults.font.family =
    "system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";
  Chart.defaults.color = "#495057";
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.boxWidth = 10;
  Chart.defaults.maintainAspectRatio = false;
}

// Distinct, non-empty values of a data-* attribute across the given rows.
function distinct(rows, attr) {
  var seen = {};
  var out = [];
  for (var i = 0; i < rows.length; i++) {
    var v = rows[i].getAttribute("data-" + attr);
    if (v !== null && v !== "" && !seen[v]) {
      seen[v] = true;
      out.push(v);
    }
  }
  return out;
}

function bedsLabel(v) {
  if (v === "0") return "Studio";
  return v + (v === "1" ? " bed" : " beds");
}

function bathsLabel(v) {
  return v + (v === "1" ? " bath" : " baths");
}

// Fill a <select> with options, numerically or alphabetically sorted.
function fillSelect(select, values, labelFn, numeric) {
  if (!select) return;
  values.sort(
    numeric
      ? function (a, b) { return parseFloat(a) - parseFloat(b); }
      : function (a, b) { return a.localeCompare(b); },
  );
  for (var i = 0; i < values.length; i++) {
    var opt = document.createElement("option");
    opt.value = values[i];
    opt.textContent = labelFn(values[i]);
    select.appendChild(opt);
  }
}

/*
 * Wire the search box and Community / Beds / Baths dropdowns for a listings
 * table (all ids namespaced by `idBase`). Options are derived from the rows'
 * data-* attributes, and every control is combined with AND semantics.
 */
export function initListingFilters(idBase) {
  var table = byId(idBase + "-table");
  if (!table || !table.tBodies.length) return;

  var search = byId(idBase + "-search");
  var community = byId(idBase + "-community");
  var beds = byId(idBase + "-beds");
  var baths = byId(idBase + "-baths");
  var count = byId(idBase + "-count");
  var rows = Array.prototype.slice.call(table.tBodies[0].rows);

  fillSelect(community, distinct(rows, "community"), function (v) { return v; }, false);
  fillSelect(beds, distinct(rows, "bedrooms"), bedsLabel, true);
  fillSelect(baths, distinct(rows, "bathrooms"), bathsLabel, true);

  function apply() {
    var q = search ? search.value.trim().toLowerCase() : "";
    var c = community ? community.value : "";
    var b = beds ? beds.value : "";
    var ba = baths ? baths.value : "";
    var shown = 0;
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var visible =
        (!q || row.textContent.toLowerCase().indexOf(q) !== -1) &&
        (!c || row.getAttribute("data-community") === c) &&
        (!b || row.getAttribute("data-bedrooms") === b) &&
        (!ba || row.getAttribute("data-bathrooms") === ba);
      row.style.display = visible ? "" : "none";
      if (visible) shown += 1;
    }
    if (count) {
      count.textContent =
        shown === rows.length
          ? rows.length + " units"
          : shown + " of " + rows.length + " units";
    }
  }

  [search, community, beds, baths].forEach(function (el) {
    if (!el) return;
    el.addEventListener("input", apply);
    el.addEventListener("change", apply);
  });
  apply();
}

/*
 * Make a listings table sortable by clicking (or Enter/Space on) its column
 * headers; clicking the active column again reverses the direction. The last
 * (actions) column is skipped. A cell's `data-sort` attribute is used as the
 * sort key when present, otherwise its visible text; columns whose header has
 * the `num` class sort numerically. Empty/"—" values always sort to the end.
 */
export function initTableSort(idBase) {
  var table = byId(idBase + "-table");
  if (!table || !table.tHead || !table.tBodies.length) return;
  var ths = Array.prototype.slice.call(table.tHead.rows[0].cells);
  var tbody = table.tBodies[0];
  var active = { col: -1, dir: 1 };

  function valueOf(cell, numeric) {
    if (!cell) return numeric ? null : "";
    var raw = cell.getAttribute("data-sort");
    if (raw === null) raw = cell.textContent.trim();
    if (raw === "" || raw === "\u2014") return numeric ? null : "";
    if (numeric) {
      var n = parseFloat(raw.replace(/[^0-9.\-]/g, ""));
      return isNaN(n) ? null : n;
    }
    return raw.toLowerCase();
  }

  ths.forEach(function (th, col) {
    if (col === ths.length - 1) return; // actions column: nothing to sort
    var numeric = th.classList.contains("num");
    th.classList.add("sortable");
    th.setAttribute("role", "button");
    th.setAttribute("tabindex", "0");
    th.setAttribute("aria-label", "Sort by " + th.textContent.trim());

    function sort() {
      var dir = active.col === col ? -active.dir : 1;
      active = { col: col, dir: dir };
      ths.forEach(function (h) { h.removeAttribute("data-sort-dir"); });
      th.setAttribute("data-sort-dir", dir === 1 ? "asc" : "desc");

      var rows = Array.prototype.slice.call(tbody.rows);
      rows.sort(function (a, b) {
        var av = valueOf(a.cells[col], numeric);
        var bv = valueOf(b.cells[col], numeric);
        var ae = av === null || av === "";
        var be = bv === null || bv === "";
        if (ae && be) return 0;
        if (ae) return 1; // empties last regardless of direction
        if (be) return -1;
        var cmp = numeric ? av - bv : String(av).localeCompare(String(bv));
        return cmp * dir;
      });
      rows.forEach(function (row) { tbody.appendChild(row); });
    }

    th.addEventListener("click", sort);
    th.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        sort();
      }
    });
  });
}
