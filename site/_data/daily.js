import fs from "node:fs";
import path from "node:path";

// deterministic "curiosity of the day": rotates with the build date, so
// the daily rebuild picks a new one without any client-side JS
export default function () {
  const dir = path.join(process.cwd(), "site", "_data", "generated");
  const curiosities = JSON.parse(
    fs.readFileSync(path.join(dir, "curiosities.json"), "utf-8")
  );
  const meta = JSON.parse(fs.readFileSync(path.join(dir, "meta.json"), "utf-8"));
  const day = Math.floor(new Date(meta.build_date).getTime() / 86400000);
  const eligible = curiosities.filter(
    (c) => c.id !== "on-this-day" && (c.rows?.length || c.derbies?.length)
  );
  const pick = eligible[day % eligible.length];
  const onThisDay = curiosities.find((c) => c.id === "on-this-day");
  return { pick, onThisDay };
}
