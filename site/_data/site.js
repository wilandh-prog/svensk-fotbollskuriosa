export default {
  title: "Svensk Fotbollskuriosa",
  tagline: "Statistiska egendomligheter ur Allsvenskans historia sedan 1924",
  // set SITE_URL in CI (e.g. https://<user>.github.io/<repo>) for correct
  // canonical/sitemap URLs; empty string keeps links relative locally
  url: process.env.SITE_URL || "",
  // GA4 measurement ID, supplied by the deploy workflow; empty locally so
  // `npm run serve` and local builds never send hits to the live property
  analyticsId: process.env.GA_MEASUREMENT_ID || "",
};
