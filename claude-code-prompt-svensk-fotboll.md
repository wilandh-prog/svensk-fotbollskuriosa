# Claude Code Prompt — Svensk Fotbollshistoria (statistical curiosities site)

Build a production-ready website about Swedish football (Allsvenskan, Superettan, Damallsvenskan, Svenska Cupen, landslaget) whose core product is **historical statistical curiosities** — not live scores. Think: "longest unbeaten run in Allsvenskan history", "biggest away wins ever", "teams relegated despite positive goal difference", "on this day in Swedish football", "clubs that led the table in October but finished outside top 3", derby all-time records, goal droughts, improbable comebacks.

## Hard requirements

1. **Data sources — free first, scrape when necessary.** In this order of preference:
   - Free/keyed APIs: check current availability of the Everysport API (Swedish leagues), api.football-data.org (verify whether Allsvenskan is on the free tier), ClubElo API (historical Elo), TheSportsDB.
   - Open datasets: openfootball / footballcsv repos on GitHub, Wikipedia season articles (structured tables for every Allsvenskan season since 1924).
   - Scraping fallback: fbref.com, allsvenskan.se, svenskfotboll.se, ella.everysport.se. Respect robots.txt, set a descriptive User-Agent, rate-limit ≤ 1 req/2s, cache raw HTML to disk so re-parsing never re-fetches.
   - **Do not assume any API works — verify each source with a real request before building on it, and document in README which sources are actually used and why.**

2. **Storage & pipeline.** SQLite database. A single idempotent update script (`update.py` or `update.ts`) that: fetches latest results → upserts matches/tables → recomputes all curiosity statistics → regenerates content. It must be safe to run repeatedly and must not corrupt data on partial failure (use transactions).

3. **Daily updates via cron-job.org → GitHub Actions → static rebuild.** Architecture is fixed:
   - cron-job.org sends a daily `POST` to the GitHub `workflow_dispatch` API for this repo, authenticated with a fine-grained PAT (Actions: read/write only) sent as a header.
   - The workflow runs the update script, commits the updated SQLite DB / data files back to the repo (data is versioned in git), rebuilds the static site, and deploys.
   - Deploy target: Cloudflare Pages or GitHub Pages — pick one and configure it.
   - The workflow must fail loudly (non-zero exit, visible in Actions) if any sanity check fails, and must NOT commit/deploy partial data in that case.
   - README must contain the exact cron-job.org job configuration: URL, method, headers (with placeholder for the PAT), body, schedule, and how to create the PAT.

4. **Site.** Fully static (Astro, Eleventy, or Next static export — justify choice). Search, if any, is client-side over a prebuilt index. Pages:
   - Front page: rotating "curiosity of the day" + "on this day" section.
   - Category pages: streaks, records, anomalies, derbies, seasons, clubs.
   - Club pages: per-club historical oddities and records.
   - Every statistic must show its source and computation basis (seasons covered).
   - Language: Swedish UI text, Swedish number/date formatting.
   - Fast, minimal JS, works well on mobile. No tracking.
   - search engine optimized.

5. **Correctness over volume.** A wrong "record" is worse than a missing one. For each curiosity, state the data coverage (e.g., "Allsvenskan 1924/25–2025"). If a source only covers 2001+, say so on the page. Add automated sanity checks (e.g., season match counts match expected fixtures, goal totals consistent between sources).

6. **Curiosity engine.** Implement statistics as small composable query functions over the SQLite schema, each with a unit test against known historical facts (e.g., verify Malmö FF's title count, IFK Göteborg's 1982 season). Ship at least 15 distinct curiosity types at launch.

## Deliverables
- Working repo with README: setup, env vars, data source inventory, cron-job.org setup steps, how to add a new curiosity type.
- Seeded database with as much historical Allsvenskan data as the free sources allow (target: all seasons since 1924 at league-table level, match-level where available).
- GitHub Actions workflow (`workflow_dispatch` + optional manual trigger) that updates data, commits, builds, deploys.
- Deployment config for Cloudflare Pages or GitHub Pages.

## Process
Work in this order: (1) probe and rank data sources with real requests, (2) schema + ingestion for one league fully, (3) curiosity engine + tests, (4) site, (5) GitHub Actions workflow + cron-job.org docs, (6) expand to remaining leagues. Show me the data-source probe results before committing to the schema.
