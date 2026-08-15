import { HtmlBasePlugin } from "@11ty/eleventy";

export default function (eleventyConfig) {
  // makes all internal links respect pathPrefix (GitHub Pages subpath)
  eleventyConfig.addPlugin(HtmlBasePlugin);

  eleventyConfig.addPassthroughCopy({ "site/static": "/" });

  eleventyConfig.addFilter("seasonSlug", (label) => String(label).replace("/", "-"));
  eleventyConfig.addFilter("nf", (n) => new Intl.NumberFormat("sv-SE").format(n));
  eleventyConfig.addFilter("svDate", (iso) => {
    if (!iso) return "";
    const d = new Date(iso + (iso.length === 10 ? "T12:00:00Z" : ""));
    return new Intl.DateTimeFormat("sv-SE", { dateStyle: "long" }).format(d);
  });

  return {
    dir: {
      input: "site",
      output: "site/_site",
      includes: "_includes",
      data: "_data",
    },
    pathPrefix: process.env.PATH_PREFIX || "/",
    markdownTemplateEngine: "njk",
    htmlTemplateEngine: "njk",
  };
}
