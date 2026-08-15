"""Curiosities needing match dates or half-time scores.

Only a handful of recent seasons have per-match dates (openfootball /
cache.wfb), so these state their narrow coverage explicitly.
"""
from __future__ import annotations

import datetime as dt
import sqlite3

from . import curiosity


@curiosity(
    "on-this-day",
    "Denna vecka i historien",
    "Allsvenska matcher som spelades kring dagens datum genom åren.",
    "seasons",
    "dated",
)
def on_this_day(conn: sqlite3.Connection):
    today = dt.date.today()
    window = [
        (today + dt.timedelta(days=off)).strftime("%m-%d") for off in range(-3, 4)
    ]
    rows = conn.execute(
        f"""
        SELECT s.label AS season, m.date, m.round,
               h.name AS home, a.name AS away, m.home_goals, m.away_goals
        FROM match m
        JOIN season s ON s.id = m.season_id
        JOIN club h ON h.id = m.home_club_id
        JOIN club a ON a.id = m.away_club_id
        WHERE m.date IS NOT NULL
          AND strftime('%m-%d', m.date) IN ({",".join("?" * len(window))})
        ORDER BY m.date DESC
        LIMIT 20
        """,
        window,
    ).fetchall()
    return [dict(r) for r in rows]


def _dated_season_matches(conn: sqlite3.Connection):
    return conn.execute(
        """
        SELECT s.id AS season_id, s.label AS season, m.date,
               m.home_club_id, m.away_club_id, m.home_goals, m.away_goals,
               h.name AS home, a.name AS away
        FROM match m
        JOIN season s ON s.id = m.season_id AND s.has_dates = 1
        JOIN club h ON h.id = m.home_club_id
        JOIN club a ON a.id = m.away_club_id
        WHERE m.date IS NOT NULL
        ORDER BY m.date
        """
    ).fetchall()


@curiosity(
    "longest-unbeaten-runs",
    "Längsta obesegrade sviterna",
    "De längsta sviterna av matcher utan förlust inom en säsong.",
    "streaks",
    "dated",
)
def longest_unbeaten(conn: sqlite3.Connection):
    runs: dict[tuple, dict] = {}
    best: list[dict] = []
    for m in _dated_season_matches(conn):
        for club_id, name, won, lost in (
            (m["home_club_id"], m["home"], m["home_goals"] > m["away_goals"], m["home_goals"] < m["away_goals"]),
            (m["away_club_id"], m["away"], m["away_goals"] > m["home_goals"], m["away_goals"] < m["home_goals"]),
        ):
            key = (m["season_id"], club_id)
            r = runs.setdefault(key, {"club": name, "season": m["season"], "len": 0, "start": None, "end": None})
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
def losing_streaks(conn: sqlite3.Connection):
    runs: dict[tuple, dict] = {}
    best: list[dict] = []
    for m in _dated_season_matches(conn):
        for club_id, name, lost in (
            (m["home_club_id"], m["home"], m["home_goals"] < m["away_goals"]),
            (m["away_club_id"], m["away"], m["away_goals"] < m["home_goals"]),
        ):
            key = (m["season_id"], club_id)
            r = runs.setdefault(key, {"club": name, "season": m["season"], "len": 0, "start": None, "end": None})
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
def ht_comebacks(conn: sqlite3.Connection):
    rows = conn.execute(
        """
        SELECT s.label AS season, m.date, h.name AS home, a.name AS away,
               m.home_goals, m.away_goals, m.ht_home, m.ht_away,
               CASE WHEN m.home_goals > m.away_goals THEN m.ht_away - m.ht_home
                    ELSE m.ht_home - m.ht_away END AS deficit
        FROM match m
        JOIN season s ON s.id = m.season_id
        JOIN club h ON h.id = m.home_club_id
        JOIN club a ON a.id = m.away_club_id
        WHERE m.ht_home IS NOT NULL
          AND ((m.home_goals > m.away_goals AND m.ht_home < m.ht_away)
            OR (m.away_goals > m.home_goals AND m.ht_away < m.ht_home))
        ORDER BY deficit DESC,
                 ABS(m.home_goals - m.away_goals) DESC
        LIMIT 12
        """
    ).fetchall()
    return [dict(r) for r in rows]
