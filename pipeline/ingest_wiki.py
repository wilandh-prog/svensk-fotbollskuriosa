"""Ingest all Allsvenskan seasons from Swedish Wikipedia.

Season list comes from the navigation template "Fotbollsallsvenskan
genom tiderna" (so new seasons appear automatically). Every season
article provides the published league table; the home×away results
matrix provides individual match results (without dates).
"""
from __future__ import annotations

import datetime as dt
import re
import sqlite3

from . import db
from .clubs import canonical_name  # noqa: F401  (used in ingest_season)
from .fetch import FetchError, wiki_rendered_html
from .reconcile import best_merge, reconcile
from .wikiparse import parse_league_table, parse_result_matrix

SEASON_LIST_TEMPLATE = "Mall:Fotbollsallsvenskan genom tiderna"
DAY_S = 24 * 3600


def allsvenskan_season_pages() -> list[str]:
    html = wiki_rendered_html(SEASON_LIST_TEMPLATE, max_age_s=7 * DAY_S)
    pages = re.findall(r'title="(Fotbollsallsvenskan [0-9/]+)"', html)
    seen: list[str] = []
    for p in pages:
        if p not in seen:
            seen.append(p)
    if len(seen) < 100:
        raise RuntimeError(f"expected >=100 Allsvenskan seasons, found {len(seen)}")
    return seen


def season_years(page: str) -> tuple[str, int, int]:
    """'Fotbollsallsvenskan 1924/1925' -> ('1924/1925', 1924, 1925)."""
    label = page.split(" ", 1)[1]
    if "/" in label:
        a, b = label.split("/")
        return label, int(a), int(b)
    y = int(label)
    return label, y, y


def en_page_title(label: str) -> str:
    """'1943/1944' -> '1943–44 Allsvenskan'; '2008' -> '2008 Allsvenskan'."""
    if "/" in label:
        a, b = label.split("/")
        return f"{a}–{b[2:]} Allsvenskan"
    return f"{label} Allsvenskan"


def ingest_season(conn: sqlite3.Connection, comp_id: int, page: str, *, current: bool) -> dict:
    label, y0, y1 = season_years(page)
    max_age = 6 * 3600 if current else None
    html = wiki_rendered_html(page, max_age_s=max_age)
    table = parse_league_table(html)
    matrix, missing = parse_result_matrix(html)
    rec = reconcile(table, matrix, missing)
    n = len(table)
    all_matches = matrix + rec.derived
    complete = rec.complete

    if not complete and not current:
        # The sv article's matrix and table disagree. Repair against the
        # independently edited English Wikipedia article, accepting only
        # combinations that exactly reproduce a published table.
        en_matrix: list = []
        en_table: list = []
        try:
            en_html = wiki_rendered_html(en_page_title(label), lang="en")
            en_matrix, _ = parse_result_matrix(en_html)
            try:
                en_table = parse_league_table(en_html)
            except ValueError:
                en_table = []
        except FetchError:
            pass

        merged = best_merge(table, matrix, en_matrix) if en_matrix else None
        if merged:
            all_matches, _ = merged
            complete = True
            note = "Enstaka resultat korsverifierade mot engelska Wikipedia."
            rec.note = f"{rec.note} {note}".strip() if rec.note else note
        elif en_matrix and en_table and len(en_table) == n:
            # both matrices agree -> suspect a typo in the sv *table*.
            # Accept the en table only if the matches reproduce it exactly
            # AND it agrees with the sv table on positions and points.
            merged2 = best_merge(en_table, matrix, en_matrix)
            sv_key = {canonical_name(r.team, r.team_link): (r.position, r.points) for r in table}
            en_key = {canonical_name(r.team, r.team_link): (r.position, r.points) for r in en_table}
            if merged2 and sv_key == en_key:
                # keep sv display names/links, take the reconciled numbers
                en_by_club = {canonical_name(r.team, r.team_link): r for r in en_table}
                for r in table:
                    e = en_by_club[canonical_name(r.team, r.team_link)]
                    r.played, r.won, r.drawn, r.lost = e.played, e.won, e.drawn, e.lost
                    r.gf, r.ga = e.gf, e.ga
                all_matches, _ = merged2
                complete = True
                note = (
                    "Enstaka tabellvärden i svenska Wikipedia rättade mot "
                    "resultatmatrisen och engelska Wikipedia."
                )
                rec.note = f"{rec.note} {note}".strip() if rec.note else note
    # Incomplete historical seasons (e.g. the 33-round 1957/58 marathon,
    # where a cross table cannot hold all meetings, or matrices whose
    # single-goal typos cannot be pinned to one specific match) get no
    # match rows at all rather than a possibly wrong subset. The running
    # season keeps its partial — but individually correct — match list.
    ingest_matches = complete or current
    if not complete and not current:
        miss = (
            "Matchresultat utelämnade: resultatmatrisen går inte att förena "
            "exakt med den publicerade sluttabellen."
        )
        rec.note = f"{rec.note} {miss}".strip() if rec.note else miss

    with conn:  # one transaction per season
        conn.execute(
            """
            INSERT INTO season (competition_id, label, start_year, end_year, wiki_page,
                                num_teams, match_source, match_data_complete, has_dates,
                                is_current, notes)
            VALUES (?, ?, ?, ?, ?, ?, 'wikipedia_matrix', ?, 0, ?, ?)
            ON CONFLICT (competition_id, label) DO UPDATE SET
                num_teams = excluded.num_teams,
                wiki_page = excluded.wiki_page,
                is_current = excluded.is_current,
                notes = excluded.notes
            """,
            (comp_id, label, y0, y1, page, n, int(complete), int(current), rec.note),
        )
        season_id = conn.execute(
            "SELECT id FROM season WHERE competition_id = ? AND label = ?",
            (comp_id, label),
        ).fetchone()["id"]

        conn.execute("DELETE FROM league_table WHERE season_id = ?", (season_id,))
        for r in table:
            club_id = db.get_or_create_club(conn, canonical_name(r.team, r.team_link), r.team_link)
            conn.execute(
                """
                INSERT INTO league_table
                    (season_id, position, club_id, played, won, drawn, lost, gf, ga, points)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (season_id, r.position, club_id, r.played, r.won, r.drawn, r.lost, r.gf, r.ga, r.points),
            )

        # Wikipedia matrix is the match source unless a richer source
        # (openfootball, with dates) has claimed this season.
        row = conn.execute("SELECT match_source FROM season WHERE id = ?", (season_id,)).fetchone()
        if row["match_source"] == "wikipedia_matrix":
            conn.execute(
                "DELETE FROM match WHERE season_id = ? AND source = 'wikipedia_matrix'",
                (season_id,),
            )
            for m in (all_matches if ingest_matches else []):
                home_id = db.get_or_create_club(conn, canonical_name(m.home, m.home_link), m.home_link)
                away_id = db.get_or_create_club(conn, canonical_name(m.away, m.away_link), m.away_link)
                conn.execute(
                    """
                    INSERT INTO match (season_id, home_club_id, away_club_id,
                                       home_goals, away_goals, awarded_result, source)
                    VALUES (?, ?, ?, ?, ?, ?, 'wikipedia_matrix')
                    """,
                    (season_id, home_id, away_id, m.home_goals, m.away_goals, m.awarded),
                )
            conn.execute(
                "UPDATE season SET match_data_complete = ? WHERE id = ?",
                (int(complete), season_id),
            )

    return {
        "page": page,
        "teams": n,
        "table_rows": len(table),
        "matrix_matches": len(all_matches) if ingest_matches else 0,
        "derived": len(rec.derived),
        "expected": n * (n - 1),
        "complete": complete,
        "note": rec.note,
        "problems": rec.problems if not current else [],
    }


def run(conn: sqlite3.Connection) -> list[dict]:
    comp_id = db.get_or_create_competition(conn, "allsvenskan", "Allsvenskan")
    pages = allsvenskan_season_pages()
    today = dt.date.today()
    results = []
    for page in pages:
        label, y0, y1 = season_years(page)
        current = y1 >= today.year
        info = ingest_season(conn, comp_id, page, current=current)
        results.append(info)
        print(
            f"{page}: {info['teams']} lag, {info['matrix_matches']}/{info['expected']} "
            f"matcher{' (komplett)' if info['complete'] else ''}"
        )
    return results


if __name__ == "__main__":
    conn = db.connect()
    run(conn)
    conn.close()
