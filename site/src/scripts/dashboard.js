/*
 * Renders the overview dashboard's over-time charts from window.DASHBOARD_DATA.
 * Only the Chart.js pieces these two charts need (bar + line) are imported and
 * registered here, so this page never bundles the doughnut/arc controllers.
 */
import {
  Chart,
  BarController,
  BarElement,
  LineController,
  LineElement,
  PointElement,
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
} from "./charts.js";

Chart.register(
  BarController,
  BarElement,
  LineController,
  LineElement,
  PointElement,
  CategoryScale,
  LinearScale,
  Legend,
  Tooltip,
  htmlLegendPlugin,
);

(function () {
  "use strict";

  var data = window.DASHBOARD_DATA || {};
  applyDefaults(Chart);

  var dates = Array.isArray(data.dates) ? data.dates : [];
  var communities = data.communities || [];
  var byBedroom = data.byBedroom || {};
  var hasPoints = dates.length > 0;
  var singlePoint = dates.length === 1;

  var charts = [];
  function reset() {
    charts.forEach(function (c) {
      if (c) c.destroy();
    });
    charts = [];
    // A destroyed chart leaves its HTML legend behind; clear them first.
    ["unitsOverTime-legend", "rentOverTime-legend"].forEach(function (id) {
      var el = byId(id);
      if (el) el.innerHTML = "";
    });
  }

  // (Re)draw both over-time charts for the given bedroom filter.
  function render(bed) {
    reset();
    var series = byBedroom[bed] || byBedroom.all || {};
    if (!hasPoints || !series.unitsByCommunityOverTime) return;

    // 1. Available units over time — stacked bars by community. Bars (rather than
    // a stacked area line) keep each community's segment at its true height,
    // which reads correctly whether there is a single snapshot or many.
    if (byId("unitsOverTime")) {
      var unitDatasets = communities.map(function (community, i) {
        return {
          label: community,
          data: series.unitsByCommunityOverTime[community],
          backgroundColor: withAlpha(color(i), 0.85),
          borderColor: color(i),
          borderWidth: 1,
          borderRadius: 4,
          maxBarThickness: 72,
        };
      });
      charts.push(
        new Chart(byId("unitsOverTime"), {
          type: "bar",
          data: { labels: dates, datasets: unitDatasets },
          options: {
            interaction: { mode: "nearest", intersect: true },
            plugins: {
              legend: { display: false },
              htmlLegend: { containerID: "unitsOverTime-legend" },
            },
            scales: {
              x: { stacked: true },
              y: {
                stacked: true,
                beginAtZero: true,
                title: { display: true, text: "Units" },
              },
            },
          },
        }),
      );
    }

    // 2. Average rent over time — overall + per community.
    if (byId("rentOverTime")) {
      var rentDatasets = [
        {
          label: "All communities",
          data: series.avgRent,
          borderColor: "#1a1a1a",
          backgroundColor: "#1a1a1a",
          borderWidth: 3,
          tension: 0.25,
          pointRadius: singlePoint ? 5 : 3,
          spanGaps: true,
        },
      ].concat(
        communities.map(function (community, i) {
          return {
            label: community,
            data: series.avgRentByCommunityOverTime[community],
            borderColor: color(i),
            backgroundColor: color(i),
            borderWidth: 1.5,
            borderDash: [5, 4],
            tension: 0.25,
            pointRadius: singlePoint ? 3 : 0,
            spanGaps: true,
          };
        }),
      );
      charts.push(
        new Chart(byId("rentOverTime"), {
          type: "line",
          data: { labels: dates, datasets: rentDatasets },
          options: {
            interaction: { mode: "nearest", intersect: false },
            plugins: {
              legend: { display: false },
              htmlLegend: { containerID: "rentOverTime-legend" },
              tooltip: {
                callbacks: {
                  label: function (ctx) {
                    return ctx.dataset.label + ": " + money(ctx.parsed.y);
                  },
                },
              },
            },
            scales: {
              y: {
                title: { display: true, text: "Avg rent" },
                ticks: { callback: function (v) { return money(v); } },
              },
            },
          },
        }),
      );
    }
  }

  // Populate the Bedrooms filter (its "all" option is already in the markup) and
  // re-render the charts whenever the selection changes.
  var select = byId("dashBeds");
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
})();
