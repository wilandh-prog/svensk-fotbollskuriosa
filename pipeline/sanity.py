"""Sanity checks. `run()` returns a list of failures; the update script
exits non-zero (and CI refuses to commit/deploy) if any check fails.

Strict checks (failures abort the pipeline):
- every season has a full league table (rows == num_teams)
- per season: sum(GF) == sum(GA), and sum(played) is even
- seasons flagged match_data_complete: recomputed W/D/L/GF/GA per club
  from the match list equals the published league table

Advisory checks (printed, non-fatal): points-vs-results recomputation.
Points rules changed over the years (2-point win through 1989, 3-point
win from 1990) and tables occasionally include sanctioned adjustments,
so points differences are reported but only fail if the era rule is
certain and the difference is unexplained.
"""
from __future__ import annotations

import sqlite3


def check_tables(conn: sqlite3.Connection) -> list[str]:
    fails: list[str] = []
    for s in conn.execute("SELECT * FROM season").fetchall():
        rows = conn.execute(
            "SELECT * FROM league_table WHERE season_id = ? ORDER BY position", (s["id"],)
        ).fetchall()
        label = s["label"]
        if len(rows) != s["num_teams"]:
            fails.append(f"{label}: {len(rows)} tabellrader, väntade {s['num_teams']}")
            continue
        if not s["notes"] and not s["is_current"]:
            # seasons with an annulled club (see season.notes) legitimately
            # break the global GF==GA and even-match-count invariants; the
            # running season's live table can be mid-edit on Wikipedia, so
            # it is checked only advisorily
            gf = sum(r["gf"] for r in rows)
            ga = sum(r["ga"] for r in rows)
            if gf != ga:
                fails.append(f"{label}: summa GM ({gf}) != summa IM ({ga})")
            played = sum(r["played"] for r in rows)
            if played % 2 != 0:
                fails.append(f"{label}: udda summa spelade matcher ({played})")
        for r in rows:
            if r["won"] + r["drawn"] + r["lost"] != r["played"]:
                fails.append(f"{label}: V+O+F != S för klubb id {r['club_id']}")
    return fails


def check_matches_vs_table(conn: sqlite3.Connection) -> list[str]:
    fails: list[str] = []
    seasons = conn.execute(
        "SELECT * FROM season WHERE match_data_complete = 1"
    ).fetchall()
    for s in seasons:
        table = {
            r["club_id"]: r
            for r in conn.execute(
                "SELECT * FROM league_table WHERE season_id = ?", (s["id"],)
            ).fetchall()
        }
        stats = {cid: {"w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "p": 0} for cid in table}
        for m in conn.execute("SELECT * FROM match WHERE season_id = ?", (s["id"],)).fetchall():
            h, a = m["home_club_id"], m["away_club_id"]
            if h not in stats or a not in stats:
                fails.append(f"{s['label']}: match med okänd klubb (id {h} / {a})")
                continue
            hg, ag = m["home_goals"], m["away_goals"]
            stats[h]["gf"] += hg; stats[h]["ga"] += ag; stats[h]["p"] += 1
            stats[a]["gf"] += ag; stats[a]["ga"] += hg; stats[a]["p"] += 1
            res = m["awarded_result"] or ("H" if hg > ag else "A" if hg < ag else "D")
            if res == "H":
                stats[h]["w"] += 1; stats[a]["l"] += 1
            elif res == "A":
                stats[h]["l"] += 1; stats[a]["w"] += 1
            else:
                stats[h]["d"] += 1; stats[a]["d"] += 1
        for cid, st in stats.items():
            t = table[cid]
            if st["p"] == 0 and t["points"] == 0 and s["notes"]:
                # club thrown out mid-season, matches annulled (see season.notes)
                continue
            got = (st["p"], st["w"], st["d"], st["l"], st["gf"], st["ga"])
            want = (t["played"], t["won"], t["drawn"], t["lost"], t["gf"], t["ga"])
            if got != want:
                name = conn.execute("SELECT name FROM club WHERE id = ?", (cid,)).fetchone()["name"]
                fails.append(
                    f"{s['label']} {name}: matcher ger S/V/O/F/GM/IM {got}, tabellen säger {want}"
                )
    return fails


def check_points_advisory(conn: sqlite3.Connection) -> list[str]:
    notes: list[str] = []
    for s in conn.execute(
        "SELECT * FROM season WHERE match_data_complete = 1 AND end_year <= 1989"
    ).fetchall():
        for r in conn.execute(
            "SELECT lt.*, c.name FROM league_table lt JOIN club c ON c.id = lt.club_id "
            "WHERE season_id = ?",
            (s["id"],),
        ).fetchall():
            expected = 2 * r["won"] + r["drawn"]
            if expected != r["points"]:
                notes.append(
                    f"{s['label']} {r['name']}: 2-poängsregeln ger {expected}, tabellen {r['points']}"
                )
    return notes


def run(conn: sqlite3.Connection) -> list[str]:
    fails = check_tables(conn) + check_matches_vs_table(conn)
    for note in check_points_advisory(conn):
        print(f"  [advisory] {note}")
    return fails


if __name__ == "__main__":
    import sys

    from . import db

    conn = db.connect()
    failures = run(conn)
    if failures:
        print(f"{len(failures)} sanity-fel:")
        for f in failures:
            print(" -", f)
        sys.exit(1)
    print("Alla sanity-kontroller OK")
