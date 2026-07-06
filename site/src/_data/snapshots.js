"use strict";

// One entry per day of data (oldest first), each with that day's full details
// and links to the previous/next snapshot. Drives the paginated snapshot pages.
const { buildSnapshots } = require("../../lib/aggregate");

module.exports = () => buildSnapshots();
