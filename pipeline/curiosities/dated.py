"""Curiosities needing match dates, rounds or half-time scores.

Only a handful of seasons carry per-match dates (openfootball /
cache.wfb), so these state their narrow coverage explicitly. A
competition without any dated season is skipped automatically by the
engine, so these appear only where the data actually exists.
"""
from __future__ import annotations

import datetime as dt
import sqlite3

from . import COMP_FILTER, curiosity


@curiosity(
    "on-this-day",
    "Denna vecka i historien",
    "Matcher som spelades kring dagens datum genom åren.",
    "seasons",
    "dated",
)
def on_this_day(conn: sqlite3.Connection, comp: str):
    today = dt.date.today()
    window = [(today + dt.timedelta(days=off)).strftime("%m-%d") for off in range(-3, 4)]
    params = {"comp": comp} | {f"d{i}": d for i, d in enumerate(window)}
    rows = conn.execute(
        f"""
        SELECT s.label AS season, m.date, m.round,
               h.name AS home, a.name AS away, m.home_goals, m.away_goals
        FROM match m
        JOIN season s ON s.id = m.season_id
        JOIN club h ON h.id = m.home_club_id
        JOIN club a ON a.id = m.away_club_id
        WHERE {COMP_FILTER} AND m.date IS NOT NULL
          AND strftime('%m-%d', m.date) IN ({",".join(f":d{i}" for i in range(len(window)))})
        ORDER BY m.date DESC
        LIMIT 20
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def _dated_season_matches(conn: sqlite3.Connection, comp: str):
    return conn.execute(
        f"""
        SELECT s.id AS season_id, s.label AS season, s.end_year, m.date, m.round,
               m.home_club_id, m.away_club_id, m.home_goals, m.away_goals,
               m.awarded_result, h.name AS home, a.name AS away
        FROM match m
        JOIN season s ON s.id = m.season_id AND s.has_dates = 1
        JOIN club h ON h.id = m.home_club_id
        JOIN club a ON a.id = m.away_club_id
        WHERE {COMP_FILTER} AND m.date IS NOT NULL
        ORDER BY m.date
        """,
        {"comp": comp},
    ).fetchall()


def _result(m) -> str:
    if m["awarded_result"]:
        return m["awarded_result"]
    if m["home_goals"] > m["away_goals"]:
        return "H"
    if m["home_goals"] < m["away_goals"]:
        return "A"
    return "D"


@curiosity(
    "longest-unbeaten-runs",
    "Längsta obesegrade sviterna",
    "De längsta sviterna av matcher utan förlust inom en säsong.",
    "streaks",
    "dated",
)
def longest_unbeaten(conn: sqlite3.Connection, comp: str):
    runs: dict[tuple, dict] = {}
    best: list[dict] = []
    for m in _dated_season_matches(conn, comp):
        res = _result(m)
        for club_id, name, lost in (
            (m["home_club_id"], m["home"], res == "A"),
            (m["away_club_id"], m["away"], res == "H"),
        ):
            key = (m["season_id"], club_id)
            r = runs.setdefault(
                key, {"club": name, "season": m["season"], "len": 0, "start": None, "end": None}
            )
            if lost:
                if r["len"] > 0:
                    best.append(dict(r))
                r.update({"len": 0, "start": None, "end": None})
            else:
                r["len"] += 1
                r["start"] = r["start"] or m["date"]
                r["end"] = m["date"]
    best.extend(dict(r) for r in runs.values() if r["len"] > 0)
    best.sort(key=lambda x: -x["len"])
    return best[:10]


@curiosity(
    "losing-streaks",
    "Längsta förlustsviterna",
    "De mörkaste perioderna: flest raka förluster inom en säsong.",
    "streaks",
    "dated",
)
def losing_streaks(conn: sqlite3.Connection, comp: str):
    runs: dict[tuple, dict] = {}
    best: list[dict] = []
    for m in _dated_season_matches(conn, comp):
        res = _result(m)
        for club_id, name, lost in (
            (m["home_club_id"], m["home"], res == "A"),
            (m["away_club_id"], m["away"], res == "H"),
        ):
            key = (m["season_id"], club_id)
            r = runs.setdefault(
                key, {"club": name, "season": m["season"], "len": 0, "start": None, "end": None}
            )
            if lost:
                r["len"] += 1
                r["start"] = r["start"] or m["date"]
                r["end"] = m["date"]
            else:
                if r["len"] > 0:
                    best.append(dict(r))
                r.update({"len": 0, "start": None, "end": None})
    best.extend(dict(r) for r in runs.values() if r["len"] > 0)
    best.sort(key=lambda x: -x["len"])
    return best[:10]


@curiosity(
    "ht-comebacks",
    "Största vändningarna",
    "Matcher som vändes från underläge i halvtid till seger.",
    "records",
    "dated",
)
def ht_comebacks(conn: sqlite3.Connection, comp: str):
    rows = conn.execute(
        f"""
        SELECT s.label AS season, m.date, h.name AS home, a.name AS away,
               m.home_goals, m.away_goals, m.ht_home, m.ht_away,
               CASE WHEN m.home_goals > m.away_goals THEN m.ht_away - m.ht_home
                    ELSE m.ht_home - m.ht_away END AS deficit
        FROM match m
        JOIN season s ON s.id = m.season_id
        JOIN club h ON h.id = m.home_club_id
        JOIN club a ON a.id = m.away_club_id
        WHERE {COMP_FILTER} AND m.ht_home IS NOT NULL
          AND ((m.home_goals > m.away_goals AND m.ht_home < m.ht_away)
            OR (m.away_goals > m.home_goals AND m.ht_away < m.ht_home))
        ORDER BY deficit DESC, ABS(m.home_goals - m.away_goals) DESC
        LIMIT 12
        """,
        {"comp": comp},
    ).fetchall()
    return [dict(r) for r in rows]


@curiosity(
    "halfway-leaders-faded",
    "Serieledare som tappade greppet",
    "Lagen som ledde serien vid halvtid men inte höll i sig till slutet. "
    "Kräver omgångsindelad matchdata, vilket bara finns för ett fåtal säsonger.",
    "anomalies",
    "dated",
)
def halfway_leaders_faded(conn: sqlite3.Connection, comp: str):
    """Rebuild the table at the halfway mark and compare with the final one."""
    seasons: dict[int, dict] = {}
    for m in _dated_season_matches(conn, comp):
        if m["round"] is None:
            continue
        s = seasons.setdefault(
            m["season_id"], {"label": m["season"], "end_year": m["end_year"], "matches": []}
        )
        s["matches"].append(m)

    out: list[dict] = []
    for season_id, s in seasons.items():
        rounds = [m["round"] for m in s["matches"]]
        halfway = max(rounds) // 2
        if halfway < 5:
            continue
        pts_per_win = 3 if s["end_year"] >= 1990 else 2
        table: dict[str, dict] = {}
        for m in s["matches"]:
            if m["round"] > halfway:
                continue
            res = _result(m)
            for name, gf, ga, won, drew in (
                (m["home"], m["home_goals"], m["away_goals"], res == "H", res == "D"),
                (m["away"], m["away_goals"], m["home_goals"], res == "A", res == "D"),
            ):
                t = table.setdefault(name, {"club": name, "pts": 0, "gd": 0, "gf": 0})
                t["pts"] += pts_per_win if won else (1 if drew else 0)
                t["gd"] += gf - ga
                t["gf"] += gf
        if not table:
            continue
        leader = max(table.values(), key=lambda t: (t["pts"], t["gd"], t["gf"]))
        final = conn.execute(
            """
            SELECT lt.position, lt.points FROM league_table lt
            JOIN club c ON c.id = lt.club_id
            WHERE lt.season_id = ? AND c.name = ?
            """,
            (season_id, leader["club"]),
        ).fetchone()
        if not final or final["position"] == 1:
            continue
        out.append(
            {
                "season": s["label"],
                "club": leader["club"],
                "halfway_round": halfway,
                "halfway_points": leader["pts"],
                "final_position": final["position"],
                "final_points": final["points"],
            }
        )
    out.sort(key=lambda x: -x["final_position"])
    return out
