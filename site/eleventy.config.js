"use strict";

const path = require("node:path");

/**
 * Eleventy configuration for the apartment availability dashboard.
 *
 * The site input lives in `src/`, static output is written to `_site/`, and the
 * historical scrape data is read at build time from the repository's `data/`
 * folder by `src/_data/availability.js`.
 *
 * JS and CSS are bundled by Vite (via `@11ty/eleventy-plugin-vite`): the page
 * scripts are ES modules that `import` Chart.js from npm, and Vite post-
 * processes the Eleventy output to bundle, hash and minify them.
 */
module.exports = async function (eleventyConfig) {
  const { default: EleventyVitePlugin } = await import("@11ty/eleventy-plugin-vite");

  // Base URL path the site is served under. Defaults to "/" for local dev; the
  // GitHub Pages deploy sets BASE_PATH=/Apartment-Scraper/ (a project site is
  // served under /<repo>/). Drives both Eleventy's pathPrefix (the `url` filter,
  // used for page links) and Vite's base (the emitted asset URLs).
  const basePath = process.env.BASE_PATH || "/";

  // Let Vite bundle the JS. Rather than passthrough-copying the scripts into the
  // Vite root, alias the root-absolute `/scripts/*` module URLs (used by the
  // <script type="module"> tags in the built HTML) back to the source folder so
  // Vite resolves and bundles them from there. The plugin deep-merges these
  // options, so its default `/node_modules` alias is preserved.
  eleventyConfig.addPlugin(EleventyVitePlugin, {
    viteOptions: {
      base: basePath,
      resolve: {
        alias: {
          "/scripts": path.resolve(__dirname, "src/scripts"),
        },
      },
    },
  });

  // The stylesheet is still passthrough-copied into the output so Vite can pick
  // it up (via <link rel="stylesheet" href="/styles/styles.css">) and hash it.
  eleventyConfig.addPassthroughCopy({ "src/styles": "styles" });

  // Watch the scrape data folder (outside the `src/` input dir) so `--serve`/
  // `--watch` rebuilds when new availability snapshots are added, even though
  // it's read directly off disk by lib/aggregate.js rather than templated.
  eleventyConfig.addWatchTarget(path.resolve(__dirname, "../data"));

  // Serialize a value to JSON that is safe to embed inside a <script> tag.
  // Escaping "<" prevents a "</script>" sequence in the data from closing the tag.
  eleventyConfig.addFilter("jsonify", (value) =>
    JSON.stringify(value === undefined ? null : value).replace(/</g, "\\u003c"),
  );

  // Human-friendly currency, e.g. 3265 -> "$3,265".
  eleventyConfig.addFilter("money", (value) =>
    value === null || value === undefined
      ? "\u2014"
      : "$" + Math.round(Number(value)).toLocaleString("en-US"),
  );

  // Thousands-separated integer, e.g. 1093 -> "1,093".
  eleventyConfig.addFilter("number", (value) =>
    value === null || value === undefined
      ? "\u2014"
      : Number(value).toLocaleString("en-US"),
  );

  return {
    dir: {
      input: "src",
      output: "_site",
      includes: "_includes",
      data: "_data",
    },
    pathPrefix: basePath,
    markdownTemplateEngine: "njk",
    htmlTemplateEngine: "njk",
    templateFormats: ["njk", "md", "html"],
  };
};
