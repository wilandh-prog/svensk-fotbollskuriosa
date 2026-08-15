"""All-time aggregates across the full league-table history."""
from __future__ import annotations

import sqlite3

from . import curiosity


@curiosity(
    "maraton-table",
    "Maratontabellen",
    "Den sammanlagda allsvenska tabellen över samtliga säsonger.",
    "clubs",
    "tables",
)
def maraton_table(conn: sqlite3.Connection):
    rows = conn.execute(
        """
        SELECT c.name AS club,
               COUNT(*) AS seasons,
               SUM(lt.played) AS played, SUM(lt.won) AS won,
               SUM(lt.drawn) AS drawn, SUM(lt.lost) AS lost,
               SUM(lt.gf) AS gf, SUM(lt.ga) AS ga,
               SUM(lt.won) * 3 + SUM(lt.drawn) AS points_3p
        FROM league_table lt
        JOIN season s ON s.id = lt.season_id AND s.is_current = 0
            AND s.competition_id = (SELECT id FROM competition WHERE code = 'allsvenskan')
        JOIN club c ON c.id = lt.club_id
        GROUP BY lt.club_id
        ORDER BY points_3p DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


@curiosity(
    "league-titles",
    "Seriesegrar genom tiderna",
    "Antal förstaplatser i Allsvenskan per klubb. Observera att seriesegern "
    "inte alltid inneburit SM-guld: 1924–1930 avgjordes mästerskapet i "
    "separat slutspel eller inte alls, och 1982–1992 korades mästaren i "
    "SM-slutspel efter serien.",
    "clubs",
    "tables",
)
def league_titles(conn: sqlite3.Connection):
    rows = conn.execute(
        """
        SELECT c.name AS club, COUNT(*) AS titles,
               GROUP_CONCAT(s.label, ', ') AS seasons
        FROM league_table lt
        JOIN season s ON s.id = lt.season_id AND s.is_current = 0
            AND s.competition_id = (SELECT id FROM competition WHERE code = 'allsvenskan')
        JOIN club c ON c.id = lt.club_id
        WHERE lt.position = 1
        GROUP BY lt.club_id
        ORDER BY titles DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


@curiosity(
    "most-seasons-no-title",
    "Flest säsonger utan serieseger",
    "Klubbarna med flest allsvenska säsonger som aldrig vunnit serien.",
    "clubs",
    "tables",
)
def most_seasons_no_title(conn: sqlite3.Connection):
    rows = conn.execute(
        """
        SELECT c.name AS club, COUNT(*) AS seasons,
               MIN(s.label) AS first_season, MAX(s.label) AS last_season,
               MIN(lt.position) AS best_position
        FROM league_table lt
        JOIN season s ON s.id = lt.season_id AND s.is_current = 0
            AND s.competition_id = (SELECT id FROM competition WHERE code = 'allsvenskan')
        JOIN club c ON c.id = lt.club_id
        GROUP BY lt.club_id
        HAVING SUM(lt.position = 1) = 0
        ORDER BY seasons DESC
        LIMIT 10
        """
    ).fetchall()
    return [dict(r) for r in rows]


@curiosity(
    "yo-yo-clubs",
    "Hissklubbarna",
    "Klubbarna med flest separata sejourer i Allsvenskan — upp och ner genom åren.",
    "clubs",
    "tables",
)
def yo_yo_clubs(conn: sqlite3.Connection):
    rows = conn.execute(
        """
        SELECT lt.club_id, c.name AS club, s.start_year, s.end_year
        FROM league_table lt
        JOIN season s ON s.id = lt.season_id
            AND s.competition_id = (SELECT id FROM competition WHERE code = 'allsvenskan')
        JOIN club c ON c.id = lt.club_id
        ORDER BY lt.club_id, s.start_year, s.label
        """
    ).fetchall()
    spells: dict[int, dict] = {}
    prev: dict[int, int] = {}
    for r in rows:
        cid = r["club_id"]
        info = spells.setdefault(cid, {"club": r["club"], "spells": 0, "seasons": 0})
        info["seasons"] += 1
        # contiguous when this season starts no later than the year after
        # the previous one ended (handles the 1957/58 -> 1959 transition)
        if cid not in prev or r["start_year"] - prev[cid] > 1:
            info["spells"] += 1
        prev[cid] = r["end_year"]
    out = sorted(spells.values(), key=lambda x: -x["spells"])[:10]
    return out


@curiosity(
    "ever-presents",
    "Aldrig nedflyttade",
    "Klubbar som spelat flest säsonger i följd i Allsvenskan.",
    "clubs",
    "tables",
)
def ever_presents(conn: sqlite3.Connection):
    rows = conn.execute(
        """
        SELECT lt.club_id, c.name AS club, s.start_year, s.end_year, s.label
        FROM league_table lt
        JOIN season s ON s.id = lt.season_id
            AND s.competition_id = (SELECT id FROM competition WHERE code = 'allsvenskan')
        JOIN club c ON c.id = lt.club_id
        ORDER BY lt.club_id, s.start_year, s.label
        """
    ).fetchall()
    best: dict[int, dict] = {}
    cur: dict[int, dict] = {}
    prev_year: dict[int, int] = {}
    for r in rows:
        cid = r["club_id"]
        if cid not in prev_year or r["start_year"] - prev_year[cid] > 1:
            cur[cid] = {"club": r["club"], "len": 0, "from": r["label"], "to": r["label"]}
        cur[cid]["len"] += 1
        cur[cid]["to"] = r["label"]
        prev_year[cid] = r["end_year"]
        if cid not in best or cur[cid]["len"] > best[cid]["len"]:
            best[cid] = dict(cur[cid])
    return sorted(best.values(), key=lambda x: -x["len"])[:10]
