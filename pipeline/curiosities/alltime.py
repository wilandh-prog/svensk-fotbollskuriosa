"""All-time aggregates across a competition's full table history."""
from __future__ import annotations

import sqlite3

from . import COMP_FILTER, curiosity


@curiosity(
    "maraton-table",
    "Maratontabellen",
    "Den sammanlagda tabellen över samtliga säsonger. Poängen räknas med "
    "dagens tre poäng per seger genom hela historien, så att epoker går att "
    "jämföra rakt av.",
    "clubs",
    "tables",
)
def maraton_table(conn: sqlite3.Connection, comp: str):
    rows = conn.execute(
        f"""
        SELECT c.name AS club,
               COUNT(*) AS seasons,
               SUM(lt.played) AS played, SUM(lt.won) AS won,
               SUM(lt.drawn) AS drawn, SUM(lt.lost) AS lost,
               SUM(lt.gf) AS gf, SUM(lt.ga) AS ga,
               SUM(lt.won) * 3 + SUM(lt.drawn) AS points_3p
        FROM league_table lt
        JOIN season s ON s.id = lt.season_id AND s.is_current = 0
        JOIN club c ON c.id = lt.club_id
        WHERE {COMP_FILTER}
        GROUP BY lt.club_id
        ORDER BY points_3p DESC
        """,
        {"comp": comp},
    ).fetchall()
    return [dict(r) for r in rows]


@curiosity(
    "league-titles",
    "Seriesegrar genom tiderna",
    {
        "allsvenskan": "Antal förstaplatser i Allsvenskan per klubb. Observera att "
        "seriesegern inte alltid inneburit SM-guld: 1924–1930 avgjordes mästerskapet "
        "i separat cupspel, och 1982–1992 korades mästaren i SM-slutspel efter serien.",
        "superettan": "Antal seriesegrar i Superettan per klubb — segern har alltid "
        "inneburit direkt uppflyttning till Allsvenskan.",
        "*": "Antal förstaplatser i serien per klubb.",
    },
    "clubs",
    "tables",
)
def league_titles(conn: sqlite3.Connection, comp: str):
    rows = conn.execute(
        f"""
        SELECT c.name AS club, COUNT(*) AS titles,
               GROUP_CONCAT(s.label, ', ') AS seasons
        FROM league_table lt
        JOIN season s ON s.id = lt.season_id AND s.is_current = 0
        JOIN club c ON c.id = lt.club_id
        WHERE lt.position = 1 AND {COMP_FILTER}
        GROUP BY lt.club_id
        ORDER BY titles DESC
        """,
        {"comp": comp},
    ).fetchall()
    return [dict(r) for r in rows]


@curiosity(
    "most-seasons-no-title",
    "Flest säsonger utan serieseger",
    "Klubbarna med flest säsonger i serien som aldrig vunnit den.",
    "clubs",
    "tables",
)
def most_seasons_no_title(conn: sqlite3.Connection, comp: str):
    rows = conn.execute(
        f"""
        SELECT c.name AS club, COUNT(*) AS seasons,
               MIN(s.label) AS first_season, MAX(s.label) AS last_season,
               MIN(lt.position) AS best_position
        FROM league_table lt
        JOIN season s ON s.id = lt.season_id AND s.is_current = 0
        JOIN club c ON c.id = lt.club_id
        WHERE {COMP_FILTER}
        GROUP BY lt.club_id
        HAVING SUM(lt.position = 1) = 0
        ORDER BY seasons DESC
        LIMIT 10
        """,
        {"comp": comp},
    ).fetchall()
    return [dict(r) for r in rows]


def _spells(conn: sqlite3.Connection, comp: str):
    return conn.execute(
        f"""
        SELECT lt.club_id, c.name AS club, s.start_year, s.end_year, s.label
        FROM league_table lt
        JOIN season s ON s.id = lt.season_id
        JOIN club c ON c.id = lt.club_id
        WHERE {COMP_FILTER}
        ORDER BY lt.club_id, s.start_year, s.label
        """,
        {"comp": comp},
    ).fetchall()


@curiosity(
    "yo-yo-clubs",
    "Hissklubbarna",
    "Klubbarna med flest separata sejourer i serien — upp och ner genom åren.",
    "clubs",
    "tables",
)
def yo_yo_clubs(conn: sqlite3.Connection, comp: str):
    spells: dict[int, dict] = {}
    prev: dict[int, int] = {}
    for r in _spells(conn, comp):
        cid = r["club_id"]
        info = spells.setdefault(cid, {"club": r["club"], "spells": 0, "seasons": 0})
        info["seasons"] += 1
        # contiguous when this season starts no later than the year after
        # the previous one ended (handles the 1957/58 -> 1959 transition)
        if cid not in prev or r["start_year"] - prev[cid] > 1:
            info["spells"] += 1
        prev[cid] = r["end_year"]
    return sorted(spells.values(), key=lambda x: -x["spells"])[:10]


@curiosity(
    "ever-presents",
    "Längst obrutna sejourer",
    "Klubbarna som spelat flest säsonger i följd i serien.",
    "clubs",
    "tables",
)
def ever_presents(conn: sqlite3.Connection, comp: str):
    best: dict[int, dict] = {}
    cur: dict[int, dict] = {}
    prev_year: dict[int, int] = {}
    for r in _spells(conn, comp):
        cid = r["club_id"]
        if cid not in prev_year or r["start_year"] - prev_year[cid] > 1:
            cur[cid] = {"club": r["club"], "len": 0, "from": r["label"], "to": r["label"]}
        cur[cid]["len"] += 1
        cur[cid]["to"] = r["label"]
        prev_year[cid] = r["end_year"]
        if cid not in best or cur[cid]["len"] > best[cid]["len"]:
            best[cid] = dict(cur[cid])
    return sorted(best.values(), key=lambda x: -x["len"])[:10]
