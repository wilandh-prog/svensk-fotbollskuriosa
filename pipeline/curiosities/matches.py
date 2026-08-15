"""Curiosities from individual match results.

Only seasons whose match list exactly reproduces the published final
table are used (see reconcile.py), so these never rest on unverified
scores.
"""
from __future__ import annotations

import sqlite3

from . import COMP_FILTER, TRUSTED_MATCHES, curiosity

BASE = f"""
SELECT s.label AS season, s.start_year, m.date,
       h.name AS home, a.name AS away, m.home_goals, m.away_goals
FROM match m
JOIN season s ON s.id = m.season_id AND {TRUSTED_MATCHES}
JOIN club h ON h.id = m.home_club_id
JOIN club a ON a.id = m.away_club_id
WHERE {COMP_FILTER}
"""

# the result that counted, which is not always the score on the pitch:
# a handful of historical matches were awarded by verdict after protests
RESULT = """
    (CASE WHEN m.awarded_result IS NOT NULL THEN m.awarded_result
          WHEN m.home_goals > m.away_goals THEN 'H'
          WHEN m.home_goals < m.away_goals THEN 'A'
          ELSE 'D' END)
"""


def _q(conn: sqlite3.Connection, comp: str, sql: str) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, {"comp": comp}).fetchall()]


@curiosity(
    "biggest-home-wins",
    "Största hemmasegrarna",
    "De mest brutala hemmasegrarna i seriens historia.",
    "records",
    "matches",
)
def biggest_home_wins(conn, comp):
    return _q(
        conn, comp,
        BASE + "AND m.home_goals > m.away_goals "
        "ORDER BY (m.home_goals - m.away_goals) DESC, m.home_goals DESC LIMIT 15",
    )


@curiosity(
    "biggest-away-wins",
    "Största bortasegrarna",
    "Bortalagen som förnedrade värdarna som mest.",
    "records",
    "matches",
)
def biggest_away_wins(conn, comp):
    return _q(
        conn, comp,
        BASE + "AND m.away_goals > m.home_goals "
        "ORDER BY (m.away_goals - m.home_goals) DESC, m.away_goals DESC LIMIT 15",
    )


@curiosity(
    "highest-scoring-matches",
    "Målrikaste matcherna",
    "Matcherna med flest mål totalt.",
    "records",
    "matches",
)
def highest_scoring(conn, comp):
    return _q(
        conn, comp,
        BASE + "ORDER BY (m.home_goals + m.away_goals) DESC, s.start_year LIMIT 15",
    )


@curiosity(
    "double-beatings",
    "Dubbelt förnedrade",
    "Lag som förlorade både hemma och borta mot samma motståndare med minst "
    "fyra mål per match under samma säsong.",
    "anomalies",
    "matches",
)
def double_beatings(conn, comp):
    return _q(
        conn, comp,
        f"""
        SELECT s.label AS season, s.start_year,
               w.name AS winner, l.name AS loser,
               m1.home_goals || '–' || m1.away_goals AS home_result,
               m2.home_goals || '–' || m2.away_goals AS away_result,
               (m1.home_goals - m1.away_goals) + (m2.away_goals - m2.home_goals) AS total_margin
        FROM match m1
        JOIN match m2 ON m2.season_id = m1.season_id
                     AND m2.home_club_id = m1.away_club_id
                     AND m2.away_club_id = m1.home_club_id
        JOIN season s ON s.id = m1.season_id AND {TRUSTED_MATCHES}
        JOIN club w ON w.id = m1.home_club_id
        JOIN club l ON l.id = m1.away_club_id
        WHERE {COMP_FILTER}
          AND m1.home_goals - m1.away_goals >= 4
          AND m2.away_goals - m2.home_goals >= 4
        ORDER BY total_margin DESC LIMIT 15
        """,
    )


@curiosity(
    "identical-double",
    "Exakt samma siffror hemma och borta",
    "Säsonger där två lag möttes två gånger och båda matcherna slutade med "
    "exakt samma ovanliga målsiffror (minst fem mål).",
    "anomalies",
    "matches",
)
def identical_double(conn, comp):
    return _q(
        conn, comp,
        f"""
        SELECT s.label AS season, s.start_year,
               h.name AS club_a, a.name AS club_b,
               m1.home_goals || '–' || m1.away_goals AS result
        FROM match m1
        JOIN match m2 ON m2.season_id = m1.season_id
                     AND m2.home_club_id = m1.away_club_id
                     AND m2.away_club_id = m1.home_club_id
        JOIN season s ON s.id = m1.season_id AND {TRUSTED_MATCHES}
        JOIN club h ON h.id = m1.home_club_id
        JOIN club a ON a.id = m1.away_club_id
        WHERE {COMP_FILTER}
          AND m1.home_goals = m2.home_goals AND m1.away_goals = m2.away_goals
          AND m1.home_goals + m1.away_goals >= 5
          AND m1.home_club_id < m1.away_club_id
        ORDER BY (m1.home_goals + m1.away_goals) DESC LIMIT 15
        """,
    )


@curiosity(
    "home-fortresses",
    "Ointagliga hemmaborgar",
    "Lag som vann samtliga hemmamatcher under en säsong.",
    "records",
    "season-matches",
)
def home_fortresses(conn, comp):
    return _q(
        conn, comp,
        f"""
        SELECT s.label AS season, s.start_year, h.name AS club,
               COUNT(*) AS home_games,
               SUM(m.home_goals) AS gf, SUM(m.away_goals) AS ga
        FROM match m
        JOIN season s ON s.id = m.season_id AND s.match_data_complete = 1 AND s.is_current = 0
        JOIN club h ON h.id = m.home_club_id
        WHERE {COMP_FILTER}
        GROUP BY s.id, m.home_club_id
        HAVING SUM({RESULT} <> 'H') = 0
        ORDER BY s.start_year
        """,
    )


@curiosity(
    "unbeaten-at-home",
    "Obesegrade på hemmaplan",
    "Lag som gick genom en hel säsong utan att förlora en enda hemmamatch.",
    "streaks",
    "season-matches",
)
def unbeaten_at_home(conn, comp):
    return _q(
        conn, comp,
        f"""
        SELECT s.label AS season, s.start_year, h.name AS club,
               COUNT(*) AS home_games,
               SUM({RESULT} = 'H') AS wins, SUM({RESULT} = 'D') AS draws,
               SUM(m.home_goals) AS gf, SUM(m.away_goals) AS ga
        FROM match m
        JOIN season s ON s.id = m.season_id AND s.match_data_complete = 1 AND s.is_current = 0
        JOIN club h ON h.id = m.home_club_id
        WHERE {COMP_FILTER}
        GROUP BY s.id, m.home_club_id
        HAVING SUM({RESULT} = 'A') = 0
        ORDER BY home_games DESC, wins DESC, s.start_year
        LIMIT 20
        """,
    )


@curiosity(
    "away-disasters",
    "Bortaresans fasor",
    "Lag som förlorade samtliga bortamatcher under en säsong.",
    "anomalies",
    "season-matches",
)
def away_disasters(conn, comp):
    return _q(
        conn, comp,
        f"""
        SELECT s.label AS season, s.start_year, a.name AS club,
               COUNT(*) AS away_games,
               SUM(m.away_goals) AS gf, SUM(m.home_goals) AS ga
        FROM match m
        JOIN season s ON s.id = m.season_id AND s.match_data_complete = 1 AND s.is_current = 0
        JOIN club a ON a.id = m.away_club_id
        WHERE {COMP_FILTER}
        GROUP BY s.id, m.away_club_id
        HAVING SUM({RESULT} <> 'H') = 0
        ORDER BY s.start_year
        """,
    )


@curiosity(
    "winless-away",
    "Säsonger utan bortaseger",
    "Lag som inte lyckades vinna en enda match på bortaplan under hela säsongen "
    "— men ändå inte nödvändigtvis förlorade alla.",
    "anomalies",
    "season-matches",
)
def winless_away(conn, comp):
    return _q(
        conn, comp,
        f"""
        SELECT s.label AS season, s.start_year, a.name AS club,
               COUNT(*) AS away_games,
               SUM({RESULT} = 'D') AS draws, SUM({RESULT} = 'H') AS losses,
               SUM(m.away_goals) AS gf, SUM(m.home_goals) AS ga
        FROM match m
        JOIN season s ON s.id = m.season_id AND s.match_data_complete = 1 AND s.is_current = 0
        JOIN club a ON a.id = m.away_club_id
        WHERE {COMP_FILTER}
        GROUP BY s.id, m.away_club_id
        HAVING SUM({RESULT} = 'A') = 0
        ORDER BY away_games DESC, s.start_year
        LIMIT 20
        """,
    )


@curiosity(
    "goalless-kings",
    "Mållöshetens mästare",
    "Lagen som samlade flest mållösa 0–0-matcher under en och samma säsong.",
    "anomalies",
    "season-matches",
)
def goalless_kings(conn, comp):
    return _q(
        conn, comp,
        f"""
        SELECT season, start_year, club, COUNT(*) AS goalless, played
        FROM (
            SELECT s.label AS season, s.start_year, h.name AS club, lt.played AS played
            FROM match m
            JOIN season s ON s.id = m.season_id AND s.match_data_complete = 1 AND s.is_current = 0
            JOIN club h ON h.id = m.home_club_id
            JOIN league_table lt ON lt.season_id = s.id AND lt.club_id = m.home_club_id
            WHERE {COMP_FILTER} AND m.home_goals = 0 AND m.away_goals = 0
            UNION ALL
            SELECT s.label, s.start_year, a.name, lt.played
            FROM match m
            JOIN season s ON s.id = m.season_id AND s.match_data_complete = 1 AND s.is_current = 0
            JOIN club a ON a.id = m.away_club_id
            JOIN league_table lt ON lt.season_id = s.id AND lt.club_id = m.away_club_id
            WHERE {COMP_FILTER} AND m.home_goals = 0 AND m.away_goals = 0
        )
        GROUP BY season, club
        ORDER BY goalless DESC, start_year LIMIT 12
        """,
    )


DERBIES = {
    "herr": {
        "stockholm": ("Stockholmsderbyt", ["AIK", "Djurgårdens IF", "Hammarby IF"]),
        "goteborg": ("Göteborgsderbyt", ["IFK Göteborg", "Örgryte IS", "GAIS", "BK Häcken"]),
        "skane": (
            "Skånederbyt",
            ["Malmö FF", "Helsingborgs IF", "Landskrona BoIS", "Trelleborgs FF"],
        ),
    },
    "dam": {
        "stockholm": ("Stockholmsderbyt", ["AIK", "Djurgårdens IF", "Hammarby IF"]),
        "goteborg": ("Göteborgsderbyt", ["BK Häcken FF", "Jitex BK"]),
        "skane": (
            "Skånederbyt",
            ["FC Rosengård", "Kristianstads DFF", "Vittsjö GIK", "IF Limhamn Bunkeflo"],
        ),
    },
}

COMP_NS = {"allsvenskan": "herr", "superettan": "herr", "damallsvenskan": "dam"}


def _derby_stats(conn: sqlite3.Connection, comp: str, clubs: list[str]) -> list[dict]:
    placeholders = ",".join(f":c{i}" for i in range(len(clubs)))
    params = {"comp": comp} | {f"c{i}": c for i, c in enumerate(clubs)}
    rows = conn.execute(
        f"""
        SELECT h.name AS home, a.name AS away,
               COUNT(*) AS matches,
               SUM({RESULT} = 'H') AS home_wins,
               SUM({RESULT} = 'D') AS draws,
               SUM({RESULT} = 'A') AS away_wins,
               SUM(m.home_goals) AS home_goals, SUM(m.away_goals) AS away_goals
        FROM match m
        JOIN season s ON s.id = m.season_id AND {TRUSTED_MATCHES}
        JOIN club h ON h.id = m.home_club_id
        JOIN club a ON a.id = m.away_club_id
        WHERE {COMP_FILTER}
          AND h.name IN ({placeholders}) AND a.name IN ({placeholders})
        GROUP BY h.name, a.name
        ORDER BY matches DESC
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


@curiosity(
    "derby-alltime",
    "Derbyfacit genom tiderna",
    "Alla inbördes möten i de klassiska Stockholms-, Göteborgs- och Skånederbyna.",
    "derbies",
    "matches",
)
def derby_alltime(conn, comp):
    out = []
    for key, (name, clubs) in DERBIES[COMP_NS[comp]].items():
        pairs = _derby_stats(conn, comp, clubs)
        if pairs:
            out.append({"derby": key, "name": name, "pairs": pairs})
    return out


@curiosity(
    "derby-droughts",
    "De längsta derbytorkorna",
    "Perioder då två rivaler inte möttes i serien över huvud taget — för att "
    "den ena (eller båda) höll till i en annan division.",
    "derbies",
    "matches",
)
def derby_droughts(conn, comp):
    out = []
    for _key, (name, clubs) in DERBIES[COMP_NS[comp]].items():
        for i, a in enumerate(clubs):
            for b in clubs[i + 1:]:
                rows = conn.execute(
                    f"""
                    SELECT DISTINCT s.start_year AS y, s.label AS label
                    FROM match m
                    JOIN season s ON s.id = m.season_id AND {TRUSTED_MATCHES}
                    JOIN club h ON h.id = m.home_club_id
                    JOIN club aw ON aw.id = m.away_club_id
                    WHERE {COMP_FILTER}
                      AND ((h.name = :a AND aw.name = :b) OR (h.name = :b AND aw.name = :a))
                    ORDER BY s.start_year
                    """,
                    {"comp": comp, "a": a, "b": b},
                ).fetchall()
                if len(rows) < 2:
                    continue
                for prev, nxt in zip(rows, rows[1:]):
                    gap = nxt["y"] - prev["y"]
                    if gap > 1:
                        out.append(
                            {
                                "derby": name,
                                "club_a": a,
                                "club_b": b,
                                "last_meeting": prev["label"],
                                "next_meeting": nxt["label"],
                                "years": gap,
                                "seasons_apart": gap - 1,
                            }
                        )
    out.sort(key=lambda x: -x["years"])
    return out[:12]
