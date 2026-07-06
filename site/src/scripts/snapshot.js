/*
 * Renders one day's charts on a snapshot page from window.SNAPSHOT_DATA. Only
 * the Chart.js pieces these charts need (doughnut + bar) are imported and
 * registered here, so this page never bundles the line-chart controller.
 */
import {
  Chart,
  DoughnutController,
  ArcElement,
  BarController,
  BarElement,
  CategoryScale,
  LinearScale,
  Legend,
  Tooltip,
} from "chart.js";
import {
  applyDefaults,
  htmlLegendPlugin,
  color,
  withAlpha,
  byId,
  money,
  initListingFilters,
  initTableSort,
} from "./charts.js";

Chart.register(
  DoughnutController,
  ArcElement,
  BarController,
  BarElement,
  CategoryScale,
  LinearScale,
  Legend,
  Tooltip,
  htmlLegendPlugin,
);

(function () {
  "use strict";

  var data = window.SNAPSHOT_DATA || {};
  applyDefaults(Chart);

  // Community doughnut colours from palette[0..]; bedrooms doughnut shifts by 2
  // so the two doughnuts on the page don't lead with the same colours.
  function doughnut(id, labels, counts, shift) {
    if (!byId(id) || !labels || !labels.length) return;
    return new Chart(byId(id), {
      type: "doughnut",
      data: {
        labels: labels,
        datasets: [
          {
            data: counts,
            backgroundColor: labels.map(function (_, i) {
              return color(i + shift);
            }),
            borderColor: "#fff",
            borderWidth: 2,
          },
        ],
      },
      options: {
        plugins: {
          legend: { display: false },
          htmlLegend: { containerID: id + "-legend" },
        },
        cutout: "58%",
      },
    });
  }

  function rentByBedroomsBar(id, labels, values) {
    if (!byId(id) || !labels || !labels.length) return;
    return new Chart(byId(id), {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Average rent",
            data: values,
            backgroundColor: labels.map(function (_, i) {
              return withAlpha(color(i + 2), 0.85);
            }),
            borderRadius: 6,
          },
        ],
      },
      options: {
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                return money(ctx.parsed.y);
              },
            },
          },
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: { callback: function (v) { return money(v); } },
          },
        },
      },
    });
  }

  function rentHistogram(id, histogram) {
    if (!byId(id) || !histogram || !histogram.labels.length) return;
    return new Chart(byId(id), {
      type: "bar",
      data: {
        labels: histogram.labels,
        datasets: [
          {
            label: "Units",
            data: histogram.counts,
            backgroundColor: withAlpha(color(0), 0.8),
            borderRadius: 4,
          },
        ],
      },
      options: {
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, title: { display: true, text: "Units" } },
          x: { ticks: { maxRotation: 60, minRotation: 0 } },
        },
      },
    });
  }

  var byBedroom = data.byBedroom || {};

  var charts = [];
  function reset() {
    charts.forEach(function (c) {
      if (c) c.destroy();
    });
    charts = [];
    // A destroyed chart leaves its HTML legend behind; clear them first.
    ["snapUnitsByCommunity-legend", "snapUnitsByBedrooms-legend"].forEach(function (id) {
      var el = byId(id);
      if (el) el.innerHTML = "";
    });
  }

  // (Re)draw the four snapshot charts for the given bedroom filter.
  function render(bed) {
    reset();
    var p = byBedroom[bed] || byBedroom.all || {};
    charts.push(doughnut("snapUnitsByCommunity", p.communityLabels, p.communityCounts, 0));
    charts.push(doughnut("snapUnitsByBedrooms", p.bedroomLabels, p.bedroomCounts, 2));
    charts.push(rentByBedroomsBar("snapRentByBedrooms", p.bedroomLabels, p.bedroomAvgRent));
    charts.push(rentHistogram("snapRentHistogram", p.histogram));
  }

  // Populate the Bedrooms filter (its "all" option is already in the markup) and
  // re-render the charts whenever the selection changes.
  var select = byId("snapBeds");
  if (select && Array.isArray(data.bedroomOptions)) {
    data.bedroomOptions
      .filter(function (o) {
        return o !== "all";
      })
      .forEach(function (opt) {
        var o = document.createElement("option");
        o.value = opt;
        o.textContent = opt;
        select.appendChild(o);
      });
    select.addEventListener("change", function () {
      render(select.value);
    });
  }

  render("all");
  initListingFilters("snap");
  initTableSort("snap");
})();
