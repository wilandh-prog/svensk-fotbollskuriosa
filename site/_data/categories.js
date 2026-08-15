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
    description: "Obesegrade sviter och förlustrader.",
  },
  derbies: {
    slug: "derbyn",
    name: "Derbyn",
    description: "Inbördes möten i de klassiska rivaliteterna.",
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

export default function () {
  const dir = path.join(process.cwd(), "site", "_data", "generated");
  const curiosities = JSON.parse(
    fs.readFileSync(path.join(dir, "curiosities.json"), "utf-8")
  );
  return Object.entries(META).map(([key, m]) => ({
    key,
    ...m,
    curiosities: curiosities.filter((c) => c.category === key),
  }));
}
