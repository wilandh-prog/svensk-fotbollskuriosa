"""Curiosities computed from published league tables.

Table data exists for every season of every competition, so these have
the widest possible coverage.
"""
from __future__ import annotations

import sqlite3

from . import COMP_FILTER, curiosity

BASE = f"""
SELECT s.label AS season, s.start_year, s.num_teams, c.name AS club,
       lt.position, lt.played, lt.won, lt.drawn, lt.lost, lt.gf, lt.ga, lt.points
FROM league_table lt
JOIN season s ON s.id = lt.season_id
JOIN club c ON c.id = lt.club_id
WHERE s.is_current = 0 AND {COMP_FILTER}
"""

# points per win: 3 from 1990 onwards, 2 before that
PTS_PER_WIN = "(CASE WHEN s.end_year >= 1990 THEN 3 ELSE 2 END)"


def _rows(
    conn: sqlite3.Connection, comp: str, extra: str = "", order: str = "", limit: int = 10
) -> list[dict]:
    q = BASE + extra + (f" ORDER BY {order}" if order else "") + f" LIMIT {limit}"
    return [dict(r) for r in conn.execute(q, {"comp": comp}).fetchall()]


@curiosity(
    "unbeaten-seasons",
    "Obesegrade genom en hel säsong",
    "Lag som tog sig genom en hel säsong utan en enda förlust.",
    "records",
    "tables",
)
def unbeaten_seasons(conn, comp):
    return _rows(conn, comp, "AND lt.lost = 0", "s.start_year", limit=50)


@curiosity(
    "winless-seasons",
    "Säsonger utan en enda seger",
    "Lag som spelade en hel säsong utan att vinna en match.",
    "anomalies",
    "tables",
)
def winless_seasons(conn, comp):
    return _rows(conn, comp, "AND lt.won = 0", "s.start_year", limit=50)


@curiosity(
    "relegated-best-gd",
    "Nedflyttade med bäst målskillnad",
    "Jumbolagen som åkte ur trots att de var långt ifrån sämst på att göra mål.",
    "anomalies",
    "tables",
)
def relegated_best_gd(conn, comp):
    return _rows(
        conn, comp, "AND lt.position > s.num_teams - 2", "(lt.gf - lt.ga) DESC", limit=10
    )


@curiosity(
    "best-goal-difference",
    "Största målskillnad under en säsong",
    "De mest överlägsna målskillnaderna i seriehistorien.",
    "records",
    "tables",
)
def best_goal_difference(conn, comp):
    return _rows(conn, comp, "", "(lt.gf - lt.ga) DESC", limit=10)


@curiosity(
    "worst-goal-difference",
    "Sämsta målskillnad under en säsong",
    "Säsongerna då allting gick fel.",
    "anomalies",
    "tables",
)
def worst_goal_difference(conn, comp):
    return _rows(conn, comp, "", "(lt.gf - lt.ga) ASC", limit=10)


@curiosity(
    "most-goals-per-game",
    "Flest gjorda mål per match",
    "Lagen med det högsta målsnittet per match under en säsong.",
    "records",
    "tables",
)
def most_goals_per_game(conn, comp):
    return _rows(conn, comp, "AND lt.played >= 18", "CAST(lt.gf AS REAL)/lt.played DESC", limit=10)


@curiosity(
    "fewest-goals-conceded",
    "Tätaste försvaren",
    "Färst insläppta mål per match under en hel säsong.",
    "records",
    "tables",
)
def fewest_conceded(conn, comp):
    return _rows(conn, comp, "AND lt.played >= 18", "CAST(lt.ga AS REAL)/lt.played ASC", limit=10)


@curiosity(
    "closest-title-races",
    "Tätaste titelstriderna",
    "Säsonger där serien avgjordes med minsta möjliga marginal mellan etta och tvåa.",
    "seasons",
    "tables",
)
def closest_title_races(conn, comp):
    rows = conn.execute(
        f"""
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
        WHERE s.is_current = 0 AND {COMP_FILTER}
        ORDER BY (lt1.points - lt2.points),
                 ((lt1.gf - lt1.ga) - (lt2.gf - lt2.ga))
        LIMIT 10
        """,
        {"comp": comp},
    ).fetchall()
    return [dict(r) for r in rows]


@curiosity(
    "biggest-title-margins",
    "De mest överlägsna seriesegrarna",
    "Störst poängavstånd mellan seriesegraren och tvåan.",
    "records",
    "tables",
)
def biggest_title_margins(conn, comp):
    rows = conn.execute(
        f"""
        SELECT s.label AS season, s.start_year, w.name AS winner, r.name AS runner_up,
               lt1.points AS winner_points, lt2.points AS runner_points,
               (lt1.points - lt2.points) AS margin, lt1.played AS played
        FROM season s
        JOIN league_table lt1 ON lt1.season_id = s.id AND lt1.position = 1
        JOIN league_table lt2 ON lt2.season_id = s.id AND lt2.position = 2
        JOIN club w ON w.id = lt1.club_id
        JOIN club r ON r.id = lt2.club_id
        WHERE s.is_current = 0 AND {COMP_FILTER}
        ORDER BY margin DESC, (lt1.points - lt2.points) / CAST(lt1.played AS REAL) DESC
        LIMIT 10
        """,
        {"comp": comp},
    ).fetchall()
    return [dict(r) for r in rows]


@curiosity(
    "goal-rich-seasons",
    "Målrikaste säsongerna",
    "Säsongerna med flest mål per match i genomsnitt.",
    "seasons",
    "tables",
)
def goal_rich_seasons(conn, comp):
    rows = conn.execute(
        f"""
        SELECT s.label AS season, s.start_year, s.num_teams,
               SUM(lt.gf) AS goals, SUM(lt.played) / 2 AS matches,
               ROUND(SUM(lt.gf) * 1.0 / (SUM(lt.played) / 2), 2) AS goals_per_match
        FROM league_table lt JOIN season s ON s.id = lt.season_id
        WHERE s.is_current = 0 AND {COMP_FILTER}
        GROUP BY s.id ORDER BY goals_per_match DESC LIMIT 10
        """,
        {"comp": comp},
    ).fetchall()
    return [dict(r) for r in rows]


@curiosity(
    "goal-poor-seasons",
    "Målfattigaste säsongerna",
    "Säsongerna då målen satt som längst inne.",
    "seasons",
    "tables",
)
def goal_poor_seasons(conn, comp):
    rows = conn.execute(
        f"""
        SELECT s.label AS season, s.start_year, s.num_teams,
               SUM(lt.gf) AS goals, SUM(lt.played) / 2 AS matches,
               ROUND(SUM(lt.gf) * 1.0 / (SUM(lt.played) / 2), 2) AS goals_per_match
        FROM league_table lt JOIN season s ON s.id = lt.season_id
        WHERE s.is_current = 0 AND {COMP_FILTER}
        GROUP BY s.id ORDER BY goals_per_match ASC LIMIT 10
        """,
        {"comp": comp},
    ).fetchall()
    return [dict(r) for r in rows]


@curiosity(
    "low-scoring-champions",
    "Svagaste mästarna",
    "Seriesegrare med lägst poängandel av maximalt möjliga.",
    "anomalies",
    "tables",
)
def low_scoring_champions(conn, comp):
    rows = conn.execute(
        f"""
        SELECT s.label AS season, s.start_year, c.name AS club, lt.points, lt.played,
               lt.won, lt.drawn, lt.lost,
               ROUND(lt.points * 1.0 / (lt.played * {PTS_PER_WIN}), 3) AS points_share
        FROM league_table lt
        JOIN season s ON s.id = lt.season_id
        JOIN club c ON c.id = lt.club_id
        WHERE lt.position = 1 AND s.is_current = 0 AND {COMP_FILTER}
        ORDER BY points_share ASC LIMIT 10
        """,
        {"comp": comp},
    ).fetchall()
    return [dict(r) for r in rows]


@curiosity(
    "dominant-champions",
    "De mest dominanta mästarna",
    "Seriesegrarna som tog störst andel av alla möjliga poäng. Jämförelsen är "
    "rättvis över tid: två poäng per seger till och med 1989, tre från 1990.",
    "records",
    "tables",
)
def dominant_champions(conn, comp):
    rows = conn.execute(
        f"""
        SELECT s.label AS season, s.start_year, c.name AS club, lt.points, lt.played,
               lt.won, lt.drawn, lt.lost,
               ROUND(lt.points * 1.0 / (lt.played * {PTS_PER_WIN}), 3) AS points_share
        FROM league_table lt
        JOIN season s ON s.id = lt.season_id
        JOIN club c ON c.id = lt.club_id
        WHERE lt.position = 1 AND s.is_current = 0 AND {COMP_FILTER}
        ORDER BY points_share DESC LIMIT 10
        """,
        {"comp": comp},
    ).fetchall()
    return [dict(r) for r in rows]


@curiosity(
    "best-debut-seasons",
    "Bästa debutsäsongerna",
    "Nykomlingar som klev rakt in och placerade sig högst i sin allra första "
    "säsong. Seriens premiärsäsong räknas inte — då debuterade ju alla.",
    "clubs",
    "tables",
)
def best_debut_seasons(conn, comp):
    return _debut_seasons(conn, comp, "ASC")


@curiosity(
    "worst-debut-seasons",
    "Sämsta debutsäsongerna",
    "Nykomlingarna som mötte den hårdaste verkligheten i sin första säsong.",
    "anomalies",
    "tables",
)
def worst_debut_seasons(conn, comp):
    return _debut_seasons(conn, comp, "DESC")


def _debut_seasons(conn: sqlite3.Connection, comp: str, direction: str) -> list[dict]:
    rows = conn.execute(
        f"""
        WITH first_season AS (
            SELECT lt.club_id, MIN(s.start_year) AS y
            FROM league_table lt
            JOIN season s ON s.id = lt.season_id
            WHERE {COMP_FILTER}
            GROUP BY lt.club_id
        ),
        opening AS (
            SELECT MIN(start_year) AS y FROM season s WHERE {COMP_FILTER}
        )
        SELECT s.label AS season, s.start_year, s.num_teams, c.name AS club,
               lt.position, lt.played, lt.won, lt.drawn, lt.lost,
               lt.gf, lt.ga, lt.points
        FROM league_table lt
        JOIN season s ON s.id = lt.season_id
        JOIN club c ON c.id = lt.club_id
        JOIN first_season f ON f.club_id = lt.club_id AND f.y = s.start_year
        WHERE s.is_current = 0 AND {COMP_FILTER}
          AND s.start_year > (SELECT y FROM opening)
        ORDER BY lt.position {direction},
                 (lt.gf - lt.ga) {"DESC" if direction == "ASC" else "ASC"}
        LIMIT 10
        """,
        {"comp": comp},
    ).fetchall()
    return [dict(r) for r in rows]


@curiosity(
    "gd-paradox",
    "Målskillnadens paradox",
    "Lag som slutade ovanför ett annat lag trots betydligt sämre målskillnad — "
    "beviset på att poäng, inte mål, avgör serien.",
    "anomalies",
    "tables",
)
def gd_paradox(conn, comp):
    rows = conn.execute(
        f"""
        SELECT s.label AS season, s.start_year,
               ca.name AS club_above, lta.position AS pos_above,
               lta.points AS pts_above, (lta.gf - lta.ga) AS gd_above,
               cb.name AS club_below, ltb.position AS pos_below,
               ltb.points AS pts_below, (ltb.gf - ltb.ga) AS gd_below,
               ((ltb.gf - ltb.ga) - (lta.gf - lta.ga)) AS gd_gap
        FROM league_table lta
        JOIN league_table ltb ON ltb.season_id = lta.season_id
                             AND ltb.position > lta.position
        JOIN season s ON s.id = lta.season_id
        JOIN club ca ON ca.id = lta.club_id
        JOIN club cb ON cb.id = ltb.club_id
        WHERE s.is_current = 0 AND {COMP_FILTER}
        ORDER BY gd_gap DESC LIMIT 10
        """,
        {"comp": comp},
    ).fetchall()
    return [dict(r) for r in rows]


def _position_swings(conn: sqlite3.Connection, comp: str, direction: str) -> list[dict]:
    """Largest position changes between a club's consecutive seasons.

    Only counts seasons that actually follow each other (a club that was
    relegated and returned years later is not a "drop").
    """
    rows = conn.execute(
        f"""
        SELECT lt.club_id, c.name AS club, s.label AS season, s.start_year,
               s.end_year, lt.position, s.num_teams
        FROM league_table lt
        JOIN season s ON s.id = lt.season_id
        JOIN club c ON c.id = lt.club_id
        WHERE s.is_current = 0 AND {COMP_FILTER}
        ORDER BY lt.club_id, s.start_year
        """,
        {"comp": comp},
    ).fetchall()
    swings: list[dict] = []
    prev: dict[int, dict] = {}
    for r in rows:
        p = prev.get(r["club_id"])
        if p and r["start_year"] - p["end_year"] <= 1:
            swings.append(
                {
                    "club": r["club"],
                    "from_season": p["season"],
                    "from_position": p["position"],
                    "to_season": r["season"],
                    "to_position": r["position"],
                    "change": r["position"] - p["position"],
                    "num_teams": r["num_teams"],
                }
            )
        prev[r["club_id"]] = dict(r)
    swings.sort(key=lambda x: x["change"], reverse=(direction == "drop"))
    return swings[:10]


@curiosity(
    "biggest-drop",
    "Största raset mellan två säsonger",
    "Från toppen till botten på tolv månader: de brantaste tabellrasen mellan "
    "två raka säsonger i serien.",
    "anomalies",
    "tables",
)
def biggest_drop(conn, comp):
    return _position_swings(conn, comp, "drop")


@curiosity(
    "biggest-climb",
    "Största klivet mellan två säsonger",
    "De mest dramatiska uppryckningarna från en säsong till nästa.",
    "records",
    "tables",
)
def biggest_climb(conn, comp):
    return _position_swings(conn, comp, "climb")


@curiosity(
    "tightest-seasons",
    "Jämnaste säsongerna",
    "Säsongerna där avståndet mellan etta och jumbo var som minst, räknat i "
    "poäng per spelad match.",
    "seasons",
    "tables",
)
def tightest_seasons(conn, comp):
    rows = conn.execute(
        f"""
        SELECT s.label AS season, s.start_year, s.num_teams,
               MAX(lt.points) AS top_points, MIN(lt.points) AS bottom_points,
               MAX(lt.played) AS played,
               ROUND((MAX(lt.points) - MIN(lt.points)) * 1.0 / MAX(lt.played), 3) AS spread
        FROM league_table lt
        JOIN season s ON s.id = lt.season_id
        WHERE s.is_current = 0 AND {COMP_FILTER}
        GROUP BY s.id
        HAVING MAX(lt.played) >= 18
        ORDER BY spread ASC LIMIT 10
        """,
        {"comp": comp},
    ).fetchall()
    return [dict(r) for r in rows]
