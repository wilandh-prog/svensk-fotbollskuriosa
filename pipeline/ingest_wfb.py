"""Ingest footballcsv/cache.wfb CSVs (adds match dates for 2019-2020).

Only used for seasons openfootball does not cover; the repo has
se.1.csv for 2019, 2020, 2023 and 2024 only.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import re
import sqlite3

from . import db
from .clubs import canonical_name
from .fetch import cached_get, FetchError

RAW_URL = "https://raw.githubusercontent.com/footballcsv/cache.wfb/master/{year}/se.1.csv"
YEARS = [2019, 2020]

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def _parse_date(s: str) -> str | None:
    m = re.match(r"\w{3} (\w{3}) (\d{1,2}) (\d{4})", s.strip())
    if not m or m.group(1) not in MONTHS:
        return None
    return dt.date(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2))).isoformat()


def _score(s: str) -> tuple[int | None, int | None]:
    m = re.match(r"(\d+)-(\d+)", s.strip())
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def ingest_year(conn: sqlite3.Connection, year: int) -> dict:
    try:
        text = cached_get(RAW_URL.format(year=year))
    except FetchError:
        return {"season": year, "matches": 0, "skipped": True}
    rows = list(csv.DictReader(io.StringIO(text)))

    comp_id = db.get_or_create_competition(conn, "allsvenskan", "Allsvenskan")
    season = conn.execute(
        "SELECT id, num_teams, match_source FROM season WHERE competition_id = ? AND label = ?",
        (comp_id, str(year)),
    ).fetchone()
    if not season:
        raise RuntimeError(f"season {year} not in DB (run wiki ingest first)")
    if season["match_source"] == "openfootball":
        return {"season": year, "matches": 0, "skipped": True}

    matches = []
    for r in rows:
        hg, ag = _score(r["FT"])
        if hg is None:
            continue
        hth, hta = _score(r.get("HT") or "")
        matches.append(
            {
                "round": int(r["Round"]) if r.get("Round", "").strip().isdigit() else None,
                "date": _parse_date(r["Date"]),
                "home": r["Team 1"].strip(),
                "away": r["Team 2"].strip(),
                "hg": hg, "ag": ag, "hth": hth, "hta": hta,
            }
        )
    if not matches:
        raise RuntimeError(f"cache.wfb {year}: no matches parsed")
    if len(matches) != season["num_teams"] * (season["num_teams"] - 1):
        print(f"cache.wfb {year}: bara {len(matches)} matcher, hoppar över")
        return {"season": year, "matches": 0, "skipped": True}

    with conn:
        conn.execute("DELETE FROM match WHERE season_id = ?", (season["id"],))
        for m in matches:
            home_id = db.get_or_create_club(conn, canonical_name(m["home"]))
            away_id = db.get_or_create_club(conn, canonical_name(m["away"]))
            conn.execute(
                """
                INSERT INTO match (season_id, round, date, home_club_id, away_club_id,
                                   home_goals, away_goals, ht_home, ht_away, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'cache.wfb')
                """,
                (season["id"], m["round"], m["date"], home_id, away_id,
                 m["hg"], m["ag"], m["hth"], m["hta"]),
            )
        complete = len(matches) == season["num_teams"] * (season["num_teams"] - 1)
        conn.execute(
            """
            UPDATE season SET match_source = 'cache.wfb', has_dates = 1,
                              match_data_complete = ?
            WHERE id = ?
            """,
            (int(complete), season["id"]),
        )
    return {"season": year, "matches": len(matches), "skipped": False}


def run(conn: sqlite3.Connection) -> list[dict]:
    out = []
    for year in YEARS:
        info = ingest_year(conn, year)
        out.append(info)
        print(f"cache.wfb {year}: {info['matches']} matcher")
    return out


if __name__ == "__main__":
    conn = db.connect()
    run(conn)
    conn.close()
