"""Export computed data as JSON for the static site build.

Everything the Eleventy build needs lands in site/_data/generated/.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

from . import db
from .curiosities import compute_all

OUT_DIR = db.ROOT / "site" / "_data" / "generated"


def slugify(name: str) -> str:
    s = name.replace("å", "a").replace("ä", "a").replace("ö", "o")
    s = s.replace("Å", "a").replace("Ä", "a").replace("Ö", "o")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s


def export_curiosities(conn: sqlite3.Connection) -> list[dict]:
    return compute_all(conn)


def export_clubs(conn: sqlite3.Connection) -> list[dict]:
    clubs = []
    for c in conn.execute("SELECT * FROM club ORDER BY name").fetchall():
        seasons = [
            dict(r)
            for r in conn.execute(
                """
                SELECT s.label AS season, s.start_year, lt.position, s.num_teams,
                       lt.played, lt.won, lt.drawn, lt.lost, lt.gf, lt.ga, lt.points,
                       s.is_current
                FROM league_table lt
                JOIN season s ON s.id = lt.season_id
                WHERE lt.club_id = ?
                ORDER BY s.start_year, s.label
                """,
                (c["id"],),
            ).fetchall()
        ]
        if not seasons:
            continue
        finished = [s for s in seasons if not s["is_current"]]
        titles = [s["season"] for s in finished if s["position"] == 1]
        best = min(finished, key=lambda s: s["position"], default=None)
        biggest_win = conn.execute(
            """
            SELECT s.label AS season, h.name AS home, a.name AS away,
                   m.home_goals, m.away_goals, m.date
            FROM match m
            JOIN season s ON s.id = m.season_id AND s.match_data_complete = 1
            JOIN club h ON h.id = m.home_club_id
            JOIN club a ON a.id = m.away_club_id
            WHERE (m.home_club_id = ? AND m.home_goals > m.away_goals)
               OR (m.away_club_id = ? AND m.away_goals > m.home_goals)
            ORDER BY ABS(m.home_goals - m.away_goals) DESC,
                     MAX(m.home_goals, m.away_goals) DESC
            LIMIT 1
            """,
            (c["id"], c["id"]),
        ).fetchone()
        worst_loss = conn.execute(
            """
            SELECT s.label AS season, h.name AS home, a.name AS away,
                   m.home_goals, m.away_goals, m.date
            FROM match m
            JOIN season s ON s.id = m.season_id AND s.match_data_complete = 1
            JOIN club h ON h.id = m.home_club_id
            JOIN club a ON a.id = m.away_club_id
            WHERE (m.home_club_id = ? AND m.home_goals < m.away_goals)
               OR (m.away_club_id = ? AND m.away_goals < m.home_goals)
            ORDER BY ABS(m.home_goals - m.away_goals) DESC,
                     MAX(m.home_goals, m.away_goals) DESC
            LIMIT 1
            """,
            (c["id"], c["id"]),
        ).fetchone()
        totals = {
            "seasons": len(finished),
            "played": sum(s["played"] for s in finished),
            "won": sum(s["won"] for s in finished),
            "drawn": sum(s["drawn"] for s in finished),
            "lost": sum(s["lost"] for s in finished),
            "gf": sum(s["gf"] for s in finished),
            "ga": sum(s["ga"] for s in finished),
        }
        clubs.append(
            {
                "name": c["name"],
                "slug": slugify(c["name"]),
                "wiki_page": c["wiki_page"],
                "seasons": seasons,
                "titles": titles,
                "best_position": best["position"] if best else None,
                "best_seasons": [s["season"] for s in finished if best and s["position"] == best["position"]],
                "biggest_win": dict(biggest_win) if biggest_win else None,
                "worst_loss": dict(worst_loss) if worst_loss else None,
                "totals": totals,
            }
        )
    return clubs


def export_seasons(conn: sqlite3.Connection) -> list[dict]:
    out = []
    for s in conn.execute("SELECT * FROM season ORDER BY start_year, label").fetchall():
        table = [
            dict(r)
            for r in conn.execute(
                """
                SELECT lt.position, c.name AS club, lt.played, lt.won, lt.drawn,
                       lt.lost, lt.gf, lt.ga, lt.points
                FROM league_table lt JOIN club c ON c.id = lt.club_id
                WHERE lt.season_id = ? ORDER BY lt.position
                """,
                (s["id"],),
            ).fetchall()
        ]
        out.append(
            {
                "label": s["label"],
                "start_year": s["start_year"],
                "end_year": s["end_year"],
                "num_teams": s["num_teams"],
                "match_source": s["match_source"],
                "match_data_complete": bool(s["match_data_complete"]),
                "has_dates": bool(s["has_dates"]),
                "is_current": bool(s["is_current"]),
                "notes": s["notes"],
                "wiki_page": s["wiki_page"],
                "table": table,
            }
        )
    return out


def run(conn: sqlite3.Connection) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    curiosities = export_curiosities(conn)
    clubs = export_clubs(conn)
    seasons = export_seasons(conn)
    meta = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "build_date": dt.date.today().isoformat(),
        "season_count": len(seasons),
        "complete_match_seasons": sum(1 for s in seasons if s["match_data_complete"]),
        "match_count": conn.execute("SELECT COUNT(*) c FROM match").fetchone()["c"],
        "club_count": len(clubs),
        "sources": [
            {
                "name": "Svenska Wikipedia – säsongsartiklar",
                "url": "https://sv.wikipedia.org/wiki/Fotbollsallsvenskan",
                "role": "Tabeller och resultatmatriser 1924/25–idag (CC BY-SA 4.0)",
            },
            {
                "name": "Engelska Wikipedia – säsongsartiklar",
                "url": "https://en.wikipedia.org/wiki/Allsvenskan",
                "role": "Korsverifiering av enstaka resultat (CC BY-SA 4.0)",
            },
            {
                "name": "openfootball/europe",
                "url": "https://github.com/openfootball/europe",
                "role": "Matchdatum och halvtidsresultat 2023–2024",
            },
            {
                "name": "footballcsv/cache.wfb",
                "url": "https://github.com/footballcsv/cache.wfb",
                "role": "Matchdatum 2019",
            },
        ],
    }
    (OUT_DIR / "curiosities.json").write_text(
        json.dumps(curiosities, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (OUT_DIR / "clubs.json").write_text(
        json.dumps(clubs, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (OUT_DIR / "seasons.json").write_text(
        json.dumps(seasons, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (OUT_DIR / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(
        f"Exporterade {len(curiosities)} kuriositeter, {len(clubs)} klubbar, "
        f"{len(seasons)} säsonger -> {OUT_DIR}"
    )


if __name__ == "__main__":
    conn = db.connect()
    run(conn)
    conn.close()
