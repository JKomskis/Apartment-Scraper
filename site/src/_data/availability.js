"use strict";

// Overview dashboard data. See ../../lib/aggregate.js for the derivation.
const { buildDashboard } = require("../../lib/aggregate");

module.exports = () => buildDashboard();
