# Svensk Fotbollskuriosa

Statisk webbplats med **statistiska kuriositeter ur Allsvenskans historia sedan
1924/1925** — rekord, sviter, egendomligheter, derbyfacit och "denna vecka i
historien". Inga liveresultat; korrekthet före volym: varje statistik redovisar
sitt beräkningsunderlag, och data som inte kan verifieras publiceras inte.

## Arkitektur

```
cron-job.org ──POST──▶ GitHub Actions (workflow_dispatch)
                          │ python -m pipeline.update
                          │   fetch → upsert (SQLite) → sanity-gate → export JSON
                          │ pytest (kända historiska fakta)
                          │ git commit data/ cache/
                          │ npm run build (Eleventy)
                          ▼
                    GitHub Pages (statisk sajt, noll klient-JS)
```

- **Pipeline**: Python (`pipeline/`), SQLite-databas i `data/svensk_fotboll.sqlite`
  (versionerad i git). En enda idempotent ingång: `python -m pipeline.update`.
  Körningen avbryts med felkod ≠ 0 — utan att committa eller deploya — om någon
  sanity-kontroll fallerar.
- **Sajt**: [Eleventy](https://www.11ty.dev/) (`site/`). Vald för att den bygger
  datadrivna sidor direkt ur JSON utan ramverks-JS, bygger 200+ sidor på under
  två sekunder och producerar ren statisk HTML (bra SEO, snabb mobil). Svensk
  UI-text och svensk tal-/datumformatering. Ingen spårning.
- **Deploy**: GitHub Pages via `actions/deploy-pages` (inget externt konto
  behövs; deployen bor i samma workflow som datauppdateringen).

## Datakällor (inventering)

Alla källor probades med riktiga anrop innan arkitekturen låstes (2026-08-15):

| Källa | Status | Används till |
|---|---|---|
| Seriernas match-API (`gql.sportomedia.se/graphql`) | ✅ publikt GraphQL, ingen nyckel; samma källa som allsvenskan.se/superettan.se/damallsvenskan.se själva läser | **Kommande matcher** (avspark, omgång, arena) och **datumsatta resultat** från 1980-talet och framåt |
| sv.wikipedia (MediaWiki API) | ✅ säsongsartiklar 1924/25–idag med sluttabell + resultatmatris | Ryggraden: tabeller alla säsonger, matchresultat via matriser |
| en.wikipedia (MediaWiki API) | ✅ | Korsverifiering när sv-artikelns matris/tabell inte stämmer internt |
| openfootball/europe (GitHub) | ✅ Allsvenskan 2023–2025 (2025 ofullständig) | Matchdatum, avsparkstider, halvtidsresultat 2023–2024 |
| footballcsv/cache.wfb (GitHub) | ✅ se.1.csv för 2019, 2020 (2020 ofullständig), 2023, 2024 | Matchdatum 2019 |
| TheSportsDB | ⚠️ svarar, men gratisnyckeln kapar alla listor till 5 rader | Används inte |
| football-data.org | ❌ Allsvenskan är TIER_THREE (betald) | Används inte |
| Everysport API | ⚠️ svarar 401; nyckel kräver ansökan via mejl | Används inte (adapter välkommen om nyckel erhålls) |
| ClubElo API | ❌ timeout (nere vid probe) | Används inte |
| fbref.com | ❌ Cloudflare-utmaning även på robots.txt | Används inte |
| worldfootball.net | ❌ 403 mot beskrivande User-Agent | Används inte (vi låtsas inte vara webbläsare) |
| svenskfotboll.se | ❌ robots.txt förbjuder just tabell-/resultatsidorna | Används inte |
| allsvenskan.se | ✅ robots tillåter (crawl-delay 10) | Reserv/korskontroll — ej aktiv |

**Kvalitetsmodell**: varje säsongs matchlista godkänns bara om den *exakt*
återskapar den publicerade sluttabellen (S/V/O/F/GM/IM per klubb). Avvikelser
reparateras via en-Wikipedia-korsverifiering; specialfall (tilldömda matcher,
Malmö FF:s uteslutning 1933/34, maratonsäsongen 1957/58) hanteras explicit.
Säsonger som inte kan verifieras publiceras med enbart tabelldata och en
förklaring på säsongssidan.

Match-API:ets historik prövas mot samma spärr: en säsong därifrån accepteras
bara om matchlistan exakt återskapar den publicerade sluttabellen. Eftersom
API:et etiketterar en klubbs hela historia med dess *nuvarande* namn (2003 års
FC Café Opera-matcher ligger under Nordic United FC) paras okända lagnamn ihop
med tabellens lag via exakt säsongsfacit — en felaktig gissning överlever inte
avstämningen. Tolv säsonger avvisas på riktiga resultatavvikelser och behåller
sin Wikipedia-data.

**Täckning** (efter verifiering):

| Liga | Säsonger | Komplett matchdata | Med matchdatum |
|---|---|---|---|
| Allsvenskan | 102 (1924/25–2026) | 95 | 39 |
| Superettan | 27 (2000–2026) | 24 | 24 |
| Damallsvenskan | 39 (1988–2026) | 17 | 22 |

Herr- och damklubbar hålls i separata namnrymder i databasen så att t.ex.
Hammarby IF (herr) och Hammarby IF (dam) aldrig blandas ihop trots samma namn.
Kuriositetsmotorn räknar fram **41 statistiktyper × alla serier där data
räcker till = 108 färdiga listor**. Allsvenskan äger rot-URL:erna
(`/kuriosa/<id>/`), övriga serier ligger under `/kuriosa/<serie>/<id>/`, och
varianterna korslänkar till varandra.

**Svenska cupen** ingår inte i lanseringen: cupen saknar sluttabeller att
verifiera matchresultat emot, och Wikipedias cupartiklar har skiftande
bracket-format över åren. Utan en oberoende verifieringsmodell skulle
cupstatistik bryta mot sajtens korrekthetsprincip — den läggs till när en
pålitlig avstämningsmetod finns.

## Kuriosa inför match

Varje kommande match inom tre veckor får en egen sida (`/matcher/<slug>/`) med
statistik om de två lagen, framräknad i `pipeline/previews.py`:

- **Formsviter**: utan seger, raka segrar, obesegrade, raka förluster, utan
  gjorda mål, utan nollor, utan hemma- respektive bortaseger.
- **Inbördes historik**: antal möten, facit, senaste mötet, när laget senast
  besegrade motståndaren, största segern i mötet.
- **Tabelläge** och form (V/O/F) för båda lagen.

Sviterna räknas bara på matcher med känt datum och inbördes statistik bara på
verifierade säsonger. Finns inget att belägga visas inget påstående — testerna
i `pipeline/tests/test_previews.py` verifierar varje svitpåstående mot de
underliggande resultaten.

## Kom igång lokalt

```bash
pip install -r requirements.txt
npm install

python -m pipeline.update    # hämtar/uppdaterar data, kör sanity, exporterar JSON
python -m pytest pipeline/tests -q
npm run serve                # http://localhost:8080
```

Första körningen hämtar ~110 Wikipedia-sidor (rate-limit 1 anrop/2 s, ≈4 min).
Rå-HTML cachas i `cache/` (versionerad i git), så senare körningar hämtar bara
sidor som kan ha ändrats (pågående säsong).

Miljövariabler (behövs bara för korrekt kanonisk URL i produktion):

| Variabel | Exempel | Sätts av |
|---|---|---|
| `SITE_URL` | `https://wilandh-prog.github.io/svensk-fotbollskuriosa` | workflowen |
| `PATH_PREFIX` | `/REPO/` | workflowen |

## Daglig uppdatering: cron-job.org → GitHub Actions

### 1. Skapa en fine-grained PAT

1. GitHub → Settings → Developer settings → **Fine-grained personal access tokens** → *Generate new token*.
2. **Repository access**: Only select repositories → detta repo.
3. **Permissions → Repository permissions → Actions: Read and write.** Inget annat.
4. Sätt en utgångstid och spara token-strängen (visas bara en gång).

### 2. Aktivera GitHub Pages

Repo → Settings → Pages → **Source: GitHub Actions**.

### 3. Konfigurera jobbet på cron-job.org

| Fält | Värde |
|---|---|
| URL | `https://api.github.com/repos/wilandh-prog/svensk-fotbollskuriosa/actions/workflows/update.yml/dispatches` |
| Metod | `POST` |
| Schema | Dagligen, t.ex. 06:00 (Europe/Stockholm) |
| Body (raw, JSON) | `{"ref":"main"}` |

Headers:

```
Authorization: Bearer <DIN_PAT>
Accept: application/vnd.github+json
X-GitHub-Api-Version: 2022-11-28
Content-Type: application/json
User-Agent: cron-job.org
```

GitHub svarar `204 No Content` när triggern lyckas — sätt gärna cron-job.org
att larma på annan statuskod. Misslyckas datauppdateringen (sanity-fel) blir
Actions-körningen röd och **ingen data committas och ingen deploy sker**.

## Lägga till en ny kuriositet

1. Skriv en funktion i lämplig modul under `pipeline/curiosities/`
   (`tables.py` = tabellbaserad, `matches.py` = matchbaserad,
   `dated.py` = kräver datum, `alltime.py` = flersäsongsaggregat).
   Funktionen tar `(conn, comp)` och ska scopa sin fråga med
   `COMP_FILTER` och den namngivna parametern `:comp` — då räknas samma
   statistik automatiskt fram för alla serier där data räcker till:

   ```python
   @curiosity(
       "mitt-id",              # url-slug
       "Min rubrik",
       "En mening som förklarar vad som visas.",
       "records",              # kategori: records|anomalies|streaks|derbies|seasons|clubs
       "tables",               # täckning: tables|matches|dated (styr underlagstexten)
   )
   def min_kuriositet(conn, comp):
       rows = conn.execute(
           f"SELECT ... FROM league_table lt "
           f"JOIN season s ON s.id = lt.season_id WHERE {COMP_FILTER}",
           {"comp": comp},
       ).fetchall()
       return [dict(r) for r in rows]
   ```

   Behöver texten skilja sig mellan serier kan `description` vara en dict:
   `{"allsvenskan": "...", "*": "fallback"}`. Ger frågan inga träffar för
   en viss serie publiceras ingen tom sida — varianten hoppas över.

2. Lägg till en presentationsspec i `PRESENTATIONS` i `pipeline/export.py`
   (kolumnrubriker + cellrenderare).
3. Lägg till ett test i `pipeline/tests/test_curiosities.py` som låser ett
   känt historiskt faktum.
4. `python -m pipeline.update && npm run build` — sidan
   `/kuriosa/mitt-id/` genereras automatiskt och dyker upp i sin kategori.

## Repostruktur

```
pipeline/            datapipeline (Python)
  fetch.py           cachad, rate-limitad hämtning (beskrivande User-Agent)
  wikiparse.py       parser för Wikipedias tabeller/resultatmatriser
  reconcile.py       matchdata ⇄ sluttabell-avstämning, w.o./tilldömda matcher
  ingest_wiki.py     alla Allsvenskan-säsonger via sv/en-Wikipedia
  ingest_openfootball.py, ingest_wfb.py   matchdatum för sentida säsonger
  sanity.py          kontroller som fäller CI vid inkonsistens
  curiosities/       kuriositetsmotorn (29 st, komponerbara SQL-frågor)
  export.py          JSON-export + presentationslager till sajten
  update.py          hela flödet: python -m pipeline.update
data/                SQLite-databasen (versionerad)
cache/               rå-HTML/JSON-cache (versionerad, gör CI-körningar snabba)
site/                Eleventy-sajt (Nunjucks-mallar, noll klient-JS)
.github/workflows/   update.yml — uppdatera → gate → committa → bygg → deploya
```
