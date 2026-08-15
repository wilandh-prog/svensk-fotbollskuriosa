"""Ingest openfootball match files (dates, kickoff times, HT scores).

Files live in github.com/openfootball/europe under sweden/, named like
2025_se1.txt (Allsvenskan) / 2025_se2.txt (Superettan). These replace
the date-less Wikipedia-matrix matches for the seasons they cover.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3

from . import db
from .clubs import canonical_name
from .fetch import cached_get

LISTING_URL = "https://api.github.com/repos/openfootball/europe/contents/sweden"
RAW_URL = "https://raw.githubusercontent.com/openfootball/europe/master/sweden/{name}"
DAY_S = 24 * 3600

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

MATCHDAY_RE = re.compile(r"^[▪»]?\s*Matchday (\d+)")
DATE_RE = re.compile(r"^\s{0,4}\w{3} (\w{3}) (\d{1,2})(?: (\d{4}))?\s*$")
MATCH_RE = re.compile(
    r"^\s+(?:(\d{1,2}[.:]\d{2})\s+)?(.+?)\s+v\s+(.+?)\s+(\d+)-(\d+)(?:\s+\((\d+)-(\d+)\))?\s*$"
)


def parse_openfootball(text: str, default_year: int) -> list[dict]:
    matches: list[dict] = []
    round_no = None
    cur_date: dt.date | None = None
    for line in text.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        m = MATCHDAY_RE.match(line.strip())
        if m:
            round_no = int(m.group(1))
            continue
        m = DATE_RE.match(line)
        if m and m.group(1) in MONTHS:
            year = int(m.group(3)) if m.group(3) else (cur_date.year if cur_date else default_year)
            cur_date = dt.date(year, MONTHS[m.group(1)], int(m.group(2)))
            continue
        m = MATCH_RE.match(line)
        if m:
            time, home, away, hg, ag, hth, hta = m.groups()
            matches.append(
                {
                    "round": round_no,
                    "date": cur_date.isoformat() if cur_date else None,
                    "home": home.strip(),
                    "away": away.strip(),
                    "hg": int(hg),
                    "ag": int(ag),
                    "hth": int(hth) if hth is not None else None,
                    "hta": int(hta) if hta is not None else None,
                }
            )
    return matches


def available_files() -> list[str]:
    body = cached_get(LISTING_URL, max_age_s=DAY_S)
    return sorted(x["name"] for x in json.loads(body) if x["name"].endswith("_se1.txt"))


def ingest_file(conn: sqlite3.Connection, name: str) -> dict:
    year = int(name.split("_")[0])
    today = dt.date.today()
    text = cached_get(RAW_URL.format(name=name), max_age_s=DAY_S if year >= today.year - 1 else None)
    matches = parse_openfootball(text, year)
    if not matches:
        raise RuntimeError(f"{name}: no matches parsed")

    comp_id = db.get_or_create_competition(conn, "allsvenskan", "Allsvenskan")
    row = conn.execute(
        "SELECT id, num_teams FROM season WHERE competition_id = ? AND label = ?",
        (comp_id, str(year)),
    ).fetchone()
    if not row:
        raise RuntimeError(f"{name}: season {year} not in DB (run wiki ingest first)")
    season_id = row["id"]

    # Only replace the (complete, date-less) Wikipedia matches when the
    # openfootball file covers the entire season — some year files were
    # abandoned partway and would silently lose data otherwise.
    if len(matches) != row["num_teams"] * (row["num_teams"] - 1):
        print(f"{name}: bara {len(matches)} matcher, hoppar över (behåller Wikipedia-matrisen)")
        return {"file": name, "season": year, "matches": 0, "skipped": True}

    with conn:
        conn.execute("DELETE FROM match WHERE season_id = ?", (season_id,))
        for m in matches:
            home_id = db.get_or_create_club(conn, canonical_name(m["home"]))
            away_id = db.get_or_create_club(conn, canonical_name(m["away"]))
            conn.execute(
                """
                INSERT INTO match (season_id, round, date, home_club_id, away_club_id,
                                   home_goals, away_goals, ht_home, ht_away, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'openfootball')
                """,
                (season_id, m["round"], m["date"], home_id, away_id,
                 m["hg"], m["ag"], m["hth"], m["hta"]),
            )
        n = conn.execute(
            "SELECT num_teams FROM season WHERE id = ?", (season_id,)
        ).fetchone()["num_teams"]
        complete = len(matches) == n * (n - 1)
        conn.execute(
            """
            UPDATE season SET match_source = 'openfootball', has_dates = 1,
                              match_data_complete = ?
            WHERE id = ?
            """,
            (int(complete), season_id),
        )
    return {"file": name, "season": year, "matches": len(matches)}


def run(conn: sqlite3.Connection) -> list[dict]:
    out = []
    for name in available_files():
        info = ingest_file(conn, name)
        out.append(info)
        print(f"{name}: {info['matches']} matcher med datum")
    return out


if __name__ == "__main__":
    conn = db.connect()
    run(conn)
    conn.close()
