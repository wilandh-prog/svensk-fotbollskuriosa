"""Curiosities computed from published league tables (full 1924- coverage)."""
from __future__ import annotations

import sqlite3

from . import curiosity

BASE = """
SELECT s.label AS season, s.start_year, s.num_teams, c.name AS club,
       lt.position, lt.played, lt.won, lt.drawn, lt.lost, lt.gf, lt.ga, lt.points
FROM league_table lt
JOIN season s ON s.id = lt.season_id
JOIN club c ON c.id = lt.club_id
WHERE s.is_current = 0
"""


def _rows(conn: sqlite3.Connection, extra: str = "", order: str = "", limit: int = 10) -> list[dict]:
    q = BASE + extra + (f" ORDER BY {order}" if order else "") + f" LIMIT {limit}"
    return [dict(r) for r in conn.execute(q).fetchall()]


@curiosity(
    "unbeaten-seasons",
    "Obesegrade genom en hel säsong",
    "Lag som tog sig genom en hel allsvensk säsong utan en enda förlust.",
    "records",
    "tables",
)
def unbeaten_seasons(conn):
    return _rows(conn, "AND lt.lost = 0", "s.start_year", limit=50)


@curiosity(
    "winless-seasons",
    "Säsonger utan en enda seger",
    "Lag som spelade en hel säsong utan att vinna en match.",
    "anomalies",
    "tables",
)
def winless_seasons(conn):
    return _rows(conn, "AND lt.won = 0", "s.start_year", limit=50)


@curiosity(
    "relegated-best-gd",
    "Nedflyttade med bäst målskillnad",
    "Ingen har någonsin åkt ur Allsvenskan med plusmålskillnad — här är "
    "jumbolagen som kom närmast.",
    "anomalies",
    "tables",
)
def relegated_best_gd(conn):
    # relegation zone approximated as the bottom two of each season
    return _rows(
        conn,
        "AND lt.position > s.num_teams - 2",
        "(lt.gf - lt.ga) DESC",
        limit=10,
    )


@curiosity(
    "best-goal-difference",
    "Största målskillnad under en säsong",
    "De mest överlägsna målskillnaderna i seriehistorien.",
    "records",
    "tables",
)
def best_goal_difference(conn):
    return _rows(conn, "", "(lt.gf - lt.ga) DESC", limit=10)


@curiosity(
    "worst-goal-difference",
    "Sämsta målskillnad under en säsong",
    "Säsongerna då allting gick fel.",
    "anomalies",
    "tables",
)
def worst_goal_difference(conn):
    return _rows(conn, "", "(lt.gf - lt.ga) ASC", limit=10)


@curiosity(
    "most-goals-per-game",
    "Flest gjorda mål per match",
    "Lagen med det högsta målsnittet per match under en säsong.",
    "records",
    "tables",
)
def most_goals_per_game(conn):
    return _rows(conn, "AND lt.played >= 18", "CAST(lt.gf AS REAL)/lt.played DESC", limit=10)


@curiosity(
    "fewest-goals-conceded",
    "Tätaste försvaren",
    "Färst insläppta mål per match under en hel säsong.",
    "records",
    "tables",
)
def fewest_conceded(conn):
    return _rows(conn, "AND lt.played >= 18", "CAST(lt.ga AS REAL)/lt.played ASC", limit=10)


@curiosity(
    "closest-title-races",
    "Tätaste titelstriderna",
    "Säsonger där guldet avgjordes med minsta möjliga marginal mellan etta och tvåa.",
    "seasons",
    "tables",
)
def closest_title_races(conn):
    rows = conn.execute(
        """
        SELECT s.label AS season, s.start_year,
               w.name AS winner, r.name AS runner_up,
               lt1.points AS winner_points, lt2.points AS runner_points,
               (lt1.gf - lt1.ga) AS winner_gd, (lt2.gf - lt2.ga) AS runner_gd,
               lt1.gf AS winner_gf, lt2.gf AS runner_gf
        FROM season s
        JOIN league_table lt1 ON lt1.season_id = s.id AND lt1.position = 1
        JOIN league_table lt2 ON lt2.season_id = s.id AND lt2.position = 2
        JOIN club w ON w.id = lt1.club_id
        JOIN club r ON r.id = lt2.club_id
        WHERE s.is_current = 0
        ORDER BY (lt1.points - lt2.points),
                 ((lt1.gf - lt1.ga) - (lt2.gf - lt2.ga))
        LIMIT 10
        """
    ).fetchall()
    return [dict(r) for r in rows]


@curiosity(
    "biggest-title-margins",
    "De mest överlägsna seriesegrarna",
    "Störst poängavstånd mellan seriesegraren och tvåan.",
    "records",
    "tables",
)
def biggest_title_margins(conn):
    rows = conn.execute(
        """
        SELECT s.label AS season, s.start_year, w.name AS winner, r.name AS runner_up,
               lt1.points AS winner_points, lt2.points AS runner_points,
               (lt1.points - lt2.points) AS margin, lt1.played AS played
        FROM season s
        JOIN league_table lt1 ON lt1.season_id = s.id AND lt1.position = 1
        JOIN league_table lt2 ON lt2.season_id = s.id AND lt2.position = 2
        JOIN club w ON w.id = lt1.club_id
        JOIN club r ON r.id = lt2.club_id
        WHERE s.is_current = 0
        ORDER BY margin DESC, (lt1.points - lt2.points) / CAST(lt1.played AS REAL) DESC
        LIMIT 10
        """
    ).fetchall()
    return [dict(r) for r in rows]


@curiosity(
    "goal-rich-seasons",
    "Målrikaste säsongerna",
    "Säsongerna med flest mål per match i genomsnitt.",
    "seasons",
    "tables",
)
def goal_rich_seasons(conn):
    rows = conn.execute(
        """
        SELECT s.label AS season, s.start_year, s.num_teams,
               SUM(lt.gf) AS goals, SUM(lt.played) / 2 AS matches,
               ROUND(SUM(lt.gf) * 1.0 / (SUM(lt.played) / 2), 2) AS goals_per_match
        FROM league_table lt JOIN season s ON s.id = lt.season_id
        WHERE s.is_current = 0
        GROUP BY s.id ORDER BY goals_per_match DESC LIMIT 10
        """
    ).fetchall()
    return [dict(r) for r in rows]


@curiosity(
    "goal-poor-seasons",
    "Målfattigaste säsongerna",
    "Säsongerna då målen satt som längst inne.",
    "seasons",
    "tables",
)
def goal_poor_seasons(conn):
    rows = conn.execute(
        """
        SELECT s.label AS season, s.start_year, s.num_teams,
               SUM(lt.gf) AS goals, SUM(lt.played) / 2 AS matches,
               ROUND(SUM(lt.gf) * 1.0 / (SUM(lt.played) / 2), 2) AS goals_per_match
        FROM league_table lt JOIN season s ON s.id = lt.season_id
        WHERE s.is_current = 0
        GROUP BY s.id ORDER BY goals_per_match ASC LIMIT 10
        """
    ).fetchall()
    return [dict(r) for r in rows]


@curiosity(
    "low-scoring-champions",
    "Svagaste mästarna",
    "Seriesegrare med lägst poängandel av maximalt möjliga.",
    "anomalies",
    "tables",
)
def low_scoring_champions(conn):
    rows = conn.execute(
        """
        SELECT s.label AS season, s.start_year, c.name AS club, lt.points, lt.played,
               lt.won, lt.drawn, lt.lost,
               ROUND(lt.points * 1.0 / (lt.played * (CASE WHEN s.end_year >= 1990 THEN 3 ELSE 2 END)), 3)
                   AS points_share
        FROM league_table lt
        JOIN season s ON s.id = lt.season_id
        JOIN club c ON c.id = lt.club_id
        WHERE lt.position = 1 AND s.is_current = 0
        ORDER BY points_share ASC LIMIT 10
        """
    ).fetchall()
    return [dict(r) for r in rows]
