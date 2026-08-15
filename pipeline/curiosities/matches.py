"""Curiosities from individual match results (seasons with complete
match data — the Wikipedia result matrices give every score since 1924)."""
from __future__ import annotations

import sqlite3

from . import curiosity

BASE = """
SELECT s.label AS season, s.start_year, m.date,
       h.name AS home, a.name AS away, m.home_goals, m.away_goals
FROM match m
JOIN season s ON s.id = m.season_id AND s.match_data_complete = 1 AND s.competition_id = (SELECT id FROM competition WHERE code = 'allsvenskan')
JOIN club h ON h.id = m.home_club_id
JOIN club a ON a.id = m.away_club_id
"""


@curiosity(
    "biggest-home-wins",
    "Största hemmasegrarna",
    "De mest brutala hemmasegrarna i seriens historia.",
    "records",
    "matches",
)
def biggest_home_wins(conn):
    rows = conn.execute(
        BASE + "WHERE m.home_goals > m.away_goals "
        "ORDER BY (m.home_goals - m.away_goals) DESC, m.home_goals DESC LIMIT 15"
    ).fetchall()
    return [dict(r) for r in rows]


@curiosity(
    "biggest-away-wins",
    "Största bortasegrarna",
    "Bortalagen som förnedrade värdarna som mest.",
    "records",
    "matches",
)
def biggest_away_wins(conn):
    rows = conn.execute(
        BASE + "WHERE m.away_goals > m.home_goals "
        "ORDER BY (m.away_goals - m.home_goals) DESC, m.away_goals DESC LIMIT 15"
    ).fetchall()
    return [dict(r) for r in rows]


@curiosity(
    "highest-scoring-matches",
    "Målrikaste matcherna",
    "Matcherna med flest mål totalt.",
    "records",
    "matches",
)
def highest_scoring(conn):
    rows = conn.execute(
        BASE + "ORDER BY (m.home_goals + m.away_goals) DESC, s.start_year LIMIT 15"
    ).fetchall()
    return [dict(r) for r in rows]


@curiosity(
    "double-beatings",
    "Dubbelt förnedrade",
    "Lag som förlorade både hemma och borta mot samma motståndare med minst fyra mål per match under samma säsong.",
    "anomalies",
    "matches",
)
def double_beatings(conn):
    rows = conn.execute(
        """
        SELECT s.label AS season, s.start_year,
               w.name AS winner, l.name AS loser,
               m1.home_goals || '–' || m1.away_goals AS home_result,
               m2.home_goals || '–' || m2.away_goals AS away_result,
               (m1.home_goals - m1.away_goals) + (m2.away_goals - m2.home_goals) AS total_margin
        FROM match m1
        JOIN match m2 ON m2.season_id = m1.season_id
                     AND m2.home_club_id = m1.away_club_id
                     AND m2.away_club_id = m1.home_club_id
        JOIN season s ON s.id = m1.season_id AND s.match_data_complete = 1 AND s.competition_id = (SELECT id FROM competition WHERE code = 'allsvenskan')
        JOIN club w ON w.id = m1.home_club_id
        JOIN club l ON l.id = m1.away_club_id
        WHERE m1.home_goals - m1.away_goals >= 4
          AND m2.away_goals - m2.home_goals >= 4
        ORDER BY total_margin DESC LIMIT 15
        """
    ).fetchall()
    return [dict(r) for r in rows]


DERBIES = {
    "stockholm": ("Stockholmsderbyt", ["AIK", "Djurgårdens IF", "Hammarby IF"]),
    "goteborg": ("Göteborgsderbyt", ["IFK Göteborg", "Örgryte IS", "GAIS", "BK Häcken"]),
    "skane": ("Skånederbyt", ["Malmö FF", "Helsingborgs IF", "Landskrona BoIS", "Trelleborgs FF"]),
}


def _derby_stats(conn: sqlite3.Connection, clubs: list[str]) -> list[dict]:
    placeholders = ",".join("?" * len(clubs))
    rows = conn.execute(
        f"""
        SELECT h.name AS home, a.name AS away,
               COUNT(*) AS matches,
               SUM(m.home_goals > m.away_goals) AS home_wins,
               SUM(m.home_goals = m.away_goals) AS draws,
               SUM(m.home_goals < m.away_goals) AS away_wins,
               SUM(m.home_goals) AS home_goals, SUM(m.away_goals) AS away_goals
        FROM match m
        JOIN season s ON s.id = m.season_id AND s.match_data_complete = 1 AND s.competition_id = (SELECT id FROM competition WHERE code = 'allsvenskan')
        JOIN club h ON h.id = m.home_club_id
        JOIN club a ON a.id = m.away_club_id
        WHERE h.name IN ({placeholders}) AND a.name IN ({placeholders})
        GROUP BY h.name, a.name
        ORDER BY matches DESC
        """,
        clubs + clubs,
    ).fetchall()
    return [dict(r) for r in rows]


@curiosity(
    "derby-alltime",
    "Derbyfacit genom tiderna",
    "Alla allsvenska inbördes möten i Stockholms-, Göteborgs- och Skånederbyna.",
    "derbies",
    "matches",
)
def derby_alltime(conn):
    out = []
    for key, (name, clubs) in DERBIES.items():
        out.append({"derby": key, "name": name, "pairs": _derby_stats(conn, clubs)})
    return out


@curiosity(
    "home-fortresses",
    "Ointagliga hemmaborgar",
    "Lag som vann samtliga hemmamatcher under en säsong.",
    "records",
    "matches",
)
def home_fortresses(conn):
    rows = conn.execute(
        """
        SELECT s.label AS season, s.start_year, h.name AS club,
               COUNT(*) AS home_games,
               SUM(m.home_goals) AS gf, SUM(m.away_goals) AS ga
        FROM match m
        JOIN season s ON s.id = m.season_id AND s.match_data_complete = 1 AND s.competition_id = (SELECT id FROM competition WHERE code = 'allsvenskan') AND s.is_current = 0
        JOIN club h ON h.id = m.home_club_id
        GROUP BY s.id, m.home_club_id
        HAVING SUM(m.home_goals <= m.away_goals) = 0
        ORDER BY s.start_year
        """
    ).fetchall()
    return [dict(r) for r in rows]


@curiosity(
    "away-disasters",
    "Bortaresans fasor",
    "Lag som förlorade samtliga bortamatcher under en säsong.",
    "anomalies",
    "matches",
)
def away_disasters(conn):
    rows = conn.execute(
        """
        SELECT s.label AS season, s.start_year, a.name AS club,
               COUNT(*) AS away_games,
               SUM(m.away_goals) AS gf, SUM(m.home_goals) AS ga
        FROM match m
        JOIN season s ON s.id = m.season_id AND s.match_data_complete = 1 AND s.competition_id = (SELECT id FROM competition WHERE code = 'allsvenskan') AND s.is_current = 0
        JOIN club a ON a.id = m.away_club_id
        GROUP BY s.id, m.away_club_id
        HAVING SUM(m.away_goals >= m.home_goals) = 0
        ORDER BY s.start_year
        """
    ).fetchall()
    return [dict(r) for r in rows]


@curiosity(
    "identical-double",
    "Exakt samma siffror hemma och borta",
    "Säsonger där två lag möttes två gånger och båda matcherna slutade med exakt samma ovanliga målsiffror (minst fem mål).",
    "anomalies",
    "matches",
)
def identical_double(conn):
    rows = conn.execute(
        """
        SELECT s.label AS season, s.start_year,
               h.name AS club_a, a.name AS club_b,
               m1.home_goals || '–' || m1.away_goals AS result
        FROM match m1
        JOIN match m2 ON m2.season_id = m1.season_id
                     AND m2.home_club_id = m1.away_club_id
                     AND m2.away_club_id = m1.home_club_id
        JOIN season s ON s.id = m1.season_id AND s.match_data_complete = 1 AND s.competition_id = (SELECT id FROM competition WHERE code = 'allsvenskan')
        JOIN club h ON h.id = m1.home_club_id
        JOIN club a ON a.id = m1.away_club_id
        WHERE m1.home_goals = m2.home_goals AND m1.away_goals = m2.away_goals
          AND m1.home_goals + m1.away_goals >= 5
          AND m1.home_club_id < m1.away_club_id
        ORDER BY (m1.home_goals + m1.away_goals) DESC LIMIT 15
        """
    ).fetchall()
    return [dict(r) for r in rows]
