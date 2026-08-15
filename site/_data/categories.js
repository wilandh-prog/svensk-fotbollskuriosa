import fs from "node:fs";
import path from "node:path";

const META = {
  records: {
    slug: "rekord",
    name: "Rekord",
    description: "Största segrarna, tätaste försvaren och andra ytterligheter.",
  },
  anomalies: {
    slug: "egendomligheter",
    name: "Egendomligheter",
    description: "Säsonger och resultat som trotsar all logik.",
  },
  streaks: {
    slug: "sviter",
    name: "Sviter",
    description: "Obesegrade sviter, förlustrader och ointagliga hemmaplaner.",
  },
  derbies: {
    slug: "derbyn",
    name: "Derbyn",
    description: "Inbördes möten och långa uppehåll i de klassiska rivaliteterna.",
  },
  seasons: {
    slug: "sasonger",
    name: "Säsonger",
    description: "Titelstrider, målfester och historiska säsonger.",
  },
  clubs: {
    slug: "klubbar",
    name: "Klubbar",
    description: "Maratontabellen, seriesegrar och klubbarnas öden.",
  },
};

const COMP_ORDER = ["allsvenskan", "superettan", "damallsvenskan"];

export default function () {
  const dir = path.join(process.cwd(), "site", "_data", "generated");
  const curiosities = JSON.parse(
    fs.readFileSync(path.join(dir, "curiosities.json"), "utf-8")
  );

  return Object.entries(META).map(([key, m]) => {
    const inCategory = curiosities.filter((c) => c.category === key);
    // one entry per statistic: the primary competition's variant carries
    // the table, the others are offered as links
    const seen = new Map();
    for (const comp of COMP_ORDER) {
      for (const c of inCategory.filter((x) => x.comp === comp)) {
        if (!seen.has(c.id)) seen.set(c.id, c);
      }
    }
    return {
      key,
      ...m,
      primary: [...seen.values()],
      count: seen.size,
      variantCount: inCategory.length,
    };
  });
}
