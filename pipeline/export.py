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


MONTHS_SV = [
    "", "januari", "februari", "mars", "april", "maj", "juni",
    "juli", "augusti", "september", "oktober", "november", "december",
]


def fmt_date(iso: str | None) -> str:
    if not iso:
        return ""
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {MONTHS_SV[d.month]} {d.year}"


def _score(i: dict) -> str:
    s = f"{i['home_goals']}–{i['away_goals']}"
    if i.get("ht_home") is not None:
        s += f" ({i['ht_home']}–{i['ht_away']})"
    return s


def _gd(i: dict) -> str:
    d = i["gf"] - i["ga"]
    return f"+{d}" if d > 0 else str(d)


# per-curiosity display spec: (column label, cell renderer)
_MATCH_COLS = [
    ("Säsong", lambda i: i["season"]),
    ("Datum", lambda i: fmt_date(i.get("date"))),
    ("Hemmalag", lambda i: i["home"]),
    ("Resultat", _score),
    ("Bortalag", lambda i: i["away"]),
]
_CHAMPION_COLS = [
    ("Säsong", lambda i: i["season"]),
    ("Klubb", lambda i: i["club"]),
    ("V-O-F", lambda i: f"{i['won']}-{i['drawn']}-{i['lost']}"),
    ("Poäng", lambda i: f"{i['points']} av {i['played']} matcher"),
    ("Poängandel", lambda i: f"{i['points_share'] * 100:.1f} %".replace(".", ",")),
]
_DEBUT_COLS = [
    ("Debutsäsong", lambda i: i["season"]),
    ("Klubb", lambda i: i["club"]),
    ("Placering", lambda i: f"{i['position']} av {i['num_teams']}"),
    ("V-O-F", lambda i: f"{i['won']}-{i['drawn']}-{i['lost']}"),
    ("Mål", lambda i: f"{i['gf']}–{i['ga']}"),
    ("P", lambda i: i["points"]),
]
_TABLEROW_COLS = [
    ("Säsong", lambda i: i["season"]),
    ("Klubb", lambda i: i["club"]),
    ("S", lambda i: i["played"]),
    ("V", lambda i: i["won"]),
    ("O", lambda i: i["drawn"]),
    ("F", lambda i: i["lost"]),
    ("Mål", lambda i: f"{i['gf']}–{i['ga']}"),
    ("MS", _gd),
    ("P", lambda i: i["points"]),
]

PRESENTATIONS: dict[str, list] = {
    "unbeaten-seasons": _TABLEROW_COLS,
    "winless-seasons": _TABLEROW_COLS,
    "relegated-best-gd": _TABLEROW_COLS,
    "best-goal-difference": _TABLEROW_COLS,
    "worst-goal-difference": _TABLEROW_COLS,
    "most-goals-per-game": _TABLEROW_COLS
    + [("Mål/match", lambda i: f"{i['gf'] / i['played']:.2f}".replace(".", ","))],
    "fewest-goals-conceded": _TABLEROW_COLS
    + [("Insläppta/match", lambda i: f"{i['ga'] / i['played']:.2f}".replace(".", ","))],
    "closest-title-races": [
        ("Säsong", lambda i: i["season"]),
        ("Seriesegrare", lambda i: i["winner"]),
        ("Tvåa", lambda i: i["runner_up"]),
        ("Poäng", lambda i: f"{i['winner_points']}–{i['runner_points']}"),
        ("Målskillnad", lambda i: f"{i['winner_gd']:+d} mot {i['runner_gd']:+d}"),
    ],
    "biggest-title-margins": [
        ("Säsong", lambda i: i["season"]),
        ("Seriesegrare", lambda i: i["winner"]),
        ("Tvåa", lambda i: i["runner_up"]),
        ("Poäng", lambda i: f"{i['winner_points']}–{i['runner_points']}"),
        ("Marginal", lambda i: f"{i['margin']} p på {i['played']} matcher"),
    ],
    "goal-rich-seasons": [
        ("Säsong", lambda i: i["season"]),
        ("Lag", lambda i: i["num_teams"]),
        ("Matcher", lambda i: i["matches"]),
        ("Mål", lambda i: i["goals"]),
        ("Mål/match", lambda i: str(i["goals_per_match"]).replace(".", ",")),
    ],
    "goal-poor-seasons": [
        ("Säsong", lambda i: i["season"]),
        ("Lag", lambda i: i["num_teams"]),
        ("Matcher", lambda i: i["matches"]),
        ("Mål", lambda i: i["goals"]),
        ("Mål/match", lambda i: str(i["goals_per_match"]).replace(".", ",")),
    ],
    "low-scoring-champions": _CHAMPION_COLS,
    "dominant-champions": _CHAMPION_COLS,
    "best-debut-seasons": _DEBUT_COLS,
    "worst-debut-seasons": _DEBUT_COLS,
    "gd-paradox": [
        ("Säsong", lambda i: i["season"]),
        ("Slutade ovanför", lambda i: f"{i['club_above']} ({i['pos_above']}:a)"),
        ("Trots målskillnad", lambda i: f"{i['gd_above']:+d}"),
        ("Lag under", lambda i: f"{i['club_below']} ({i['pos_below']}:a)"),
        ("Med målskillnad", lambda i: f"{i['gd_below']:+d}"),
        ("Skillnad", lambda i: f"{i['gd_gap']} mål"),
    ],
    "biggest-drop": [
        ("Klubb", lambda i: i["club"]),
        ("Från", lambda i: f"{i['from_position']}:a ({i['from_season']})"),
        ("Till", lambda i: f"{i['to_position']}:a ({i['to_season']})"),
        ("Placeringar", lambda i: f"{abs(i['change'])} ned"),
    ],
    "biggest-climb": [
        ("Klubb", lambda i: i["club"]),
        ("Från", lambda i: f"{i['from_position']}:a ({i['from_season']})"),
        ("Till", lambda i: f"{i['to_position']}:a ({i['to_season']})"),
        ("Placeringar", lambda i: f"{abs(i['change'])} upp"),
    ],
    "tightest-seasons": [
        ("Säsong", lambda i: i["season"]),
        ("Lag", lambda i: i["num_teams"]),
        ("Etta", lambda i: f"{i['top_points']} p"),
        ("Jumbo", lambda i: f"{i['bottom_points']} p"),
        ("Spridning", lambda i: f"{i['spread']:.2f} p/match".replace(".", ",")),
    ],
    "goalless-kings": [
        ("Säsong", lambda i: i["season"]),
        ("Klubb", lambda i: i["club"]),
        ("0–0-matcher", lambda i: i["goalless"]),
        ("Av totalt", lambda i: f"{i['played']} matcher"),
    ],
    "unbeaten-at-home": [
        ("Säsong", lambda i: i["season"]),
        ("Klubb", lambda i: i["club"]),
        ("Hemmamatcher", lambda i: i["home_games"]),
        ("V-O", lambda i: f"{i['wins']}-{i['draws']}"),
        ("Mål hemma", lambda i: f"{i['gf']}–{i['ga']}"),
    ],
    "winless-away": [
        ("Säsong", lambda i: i["season"]),
        ("Klubb", lambda i: i["club"]),
        ("Bortamatcher", lambda i: i["away_games"]),
        ("O-F", lambda i: f"{i['draws']}-{i['losses']}"),
        ("Mål borta", lambda i: f"{i['gf']}–{i['ga']}"),
    ],
    "derby-droughts": [
        ("Derby", lambda i: i["derby"]),
        ("Rivaler", lambda i: f"{i['club_a']} – {i['club_b']}"),
        ("Senaste mötet", lambda i: i["last_meeting"]),
        ("Nästa möte", lambda i: i["next_meeting"]),
        ("Uppehåll", lambda i: f"{i['years']} år"),
    ],
    "halfway-leaders-faded": [
        ("Säsong", lambda i: i["season"]),
        ("Ledde vid halvtid", lambda i: i["club"]),
        ("Poäng då", lambda i: f"{i['halfway_points']} efter {i['halfway_round']} omgångar"),
        ("Slutplacering", lambda i: f"{i['final_position']}:a"),
        ("Slutpoäng", lambda i: i["final_points"]),
    ],
    "biggest-home-wins": _MATCH_COLS,
    "biggest-away-wins": _MATCH_COLS,
    "highest-scoring-matches": _MATCH_COLS,
    "identical-double": [
        ("Säsong", lambda i: i["season"]),
        ("Möte", lambda i: f"{i['club_a']} – {i['club_b']}"),
        ("Resultat båda gångerna", lambda i: i["result"]),
    ],
    "double-beatings": [
        ("Säsong", lambda i: i["season"]),
        ("Vinnare", lambda i: i["winner"]),
        ("Förlorare", lambda i: i["loser"]),
        ("Hemma", lambda i: i["home_result"]),
        ("Borta", lambda i: i["away_result"]),
        ("Total marginal", lambda i: f"+{i['total_margin']}"),
    ],
    "home-fortresses": [
        ("Säsong", lambda i: i["season"]),
        ("Klubb", lambda i: i["club"]),
        ("Hemmamatcher", lambda i: f"{i['home_games']} – alla vunna"),
        ("Mål hemma", lambda i: f"{i['gf']}–{i['ga']}"),
    ],
    "away-disasters": [
        ("Säsong", lambda i: i["season"]),
        ("Klubb", lambda i: i["club"]),
        ("Bortamatcher", lambda i: f"{i['away_games']} – alla förlorade"),
        ("Mål borta", lambda i: f"{i['gf']}–{i['ga']}"),
    ],
    "on-this-day": _MATCH_COLS,
    "ht-comebacks": _MATCH_COLS
    + [("Underläge i halvtid", lambda i: f"{i['deficit']} mål")],
    "longest-unbeaten-runs": [
        ("Klubb", lambda i: i["club"]),
        ("Säsong", lambda i: i["season"]),
        ("Matcher utan förlust", lambda i: i["len"]),
        ("Period", lambda i: f"{fmt_date(i['start'])} – {fmt_date(i['end'])}"),
    ],
    "losing-streaks": [
        ("Klubb", lambda i: i["club"]),
        ("Säsong", lambda i: i["season"]),
        ("Raka förluster", lambda i: i["len"]),
        ("Period", lambda i: f"{fmt_date(i['start'])} – {fmt_date(i['end'])}"),
    ],
    "maraton-table": [
        ("Klubb", lambda i: i["club"]),
        ("Säsonger", lambda i: i["seasons"]),
        ("S", lambda i: i["played"]),
        ("V", lambda i: i["won"]),
        ("O", lambda i: i["drawn"]),
        ("F", lambda i: i["lost"]),
        ("Mål", lambda i: f"{i['gf']}–{i['ga']}"),
        ("P (3 p/vinst)", lambda i: i["points_3p"]),
    ],
    "league-titles": [
        ("Klubb", lambda i: i["club"]),
        ("Seriesegrar", lambda i: i["titles"]),
        ("Säsonger", lambda i: i["seasons"]),
    ],
    "most-seasons-no-title": [
        ("Klubb", lambda i: i["club"]),
        ("Säsonger utan serieseger", lambda i: i["seasons"]),
        ("Period", lambda i: f"{i['first_season']} – {i['last_season']}"),
        ("Bästa placering", lambda i: i["best_position"]),
    ],
    "yo-yo-clubs": [
        ("Klubb", lambda i: i["club"]),
        ("Sejourer", lambda i: i["spells"]),
        ("Säsonger totalt", lambda i: i["seasons"]),
    ],
    "ever-presents": [
        ("Klubb", lambda i: i["club"]),
        ("Raka säsonger", lambda i: i["len"]),
        ("Period", lambda i: f"{i['from']} – {i['to']}"),
    ],
}


def _present(cur: dict) -> dict:
    spec = PRESENTATIONS.get(cur["id"])
    if spec:
        columns = [label for label, _ in spec]
        rows = [[str(fn(i)) for _, fn in spec] for i in cur["items"]]
        # drop columns nobody filled in — e.g. "Datum" for seasons whose
        # results come from a cross table and carry no match dates
        keep = [j for j in range(len(columns)) if any(r[j] for r in rows)]
        cur["columns"] = [columns[j] for j in keep]
        cur["rows"] = [[r[j] for j in keep] for r in rows]
    elif cur["id"] == "derby-alltime":
        derbies = []
        for d in cur["items"]:
            derbies.append(
                {
                    "name": d["name"],
                    "columns": ["Hemmalag", "Bortalag", "Matcher", "1", "X", "2", "Mål"],
                    "rows": [
                        [
                            p["home"], p["away"], str(p["matches"]),
                            str(p["home_wins"]), str(p["draws"]), str(p["away_wins"]),
                            f"{p['home_goals']}–{p['away_goals']}",
                        ]
                        for p in d["pairs"]
                    ],
                }
            )
        cur["derbies"] = derbies
    return cur


def export_curiosities(conn: sqlite3.Connection) -> list[dict]:
    return [_present(c) for c in compute_all(conn)]


def season_slug(comp_code: str, label: str) -> str:
    slug = label.replace("/", "-")
    return slug if comp_code == "allsvenskan" else f"{comp_code}-{slug}"


def export_clubs(conn: sqlite3.Connection) -> list[dict]:
    clubs = []
    for c in conn.execute("SELECT * FROM club ORDER BY name").fetchall():
        seasons = [
            dict(r)
            for r in conn.execute(
                """
                SELECT s.label AS season, s.start_year, lt.position, s.num_teams,
                       lt.played, lt.won, lt.drawn, lt.lost, lt.gf, lt.ga, lt.points,
                       s.is_current, comp.code AS comp, comp.name AS comp_name
                FROM league_table lt
                JOIN season s ON s.id = lt.season_id
                JOIN competition comp ON comp.id = s.competition_id
                WHERE lt.club_id = ?
                ORDER BY s.start_year, s.label
                """,
                (c["id"],),
            ).fetchall()
        ]
        if not seasons:
            continue
        for s in seasons:
            s["slug"] = season_slug(s["comp"], s["season"])
        finished = [s for s in seasons if not s["is_current"]]
        top_flight = [
            s for s in finished if s["comp"] in ("allsvenskan", "damallsvenskan")
        ]
        titles = [s["season"] for s in top_flight if s["position"] == 1]
        best = min(top_flight, key=lambda s: s["position"], default=None)
        biggest_win = conn.execute(
            """
            SELECT s.label AS season, comp.name AS comp_name,
                   h.name AS home, a.name AS away,
                   m.home_goals, m.away_goals, m.date
            FROM match m
            JOIN season s ON s.id = m.season_id AND s.match_data_complete = 1
            JOIN competition comp ON comp.id = s.competition_id
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
            SELECT s.label AS season, comp.name AS comp_name,
                   h.name AS home, a.name AS away,
                   m.home_goals, m.away_goals, m.date
            FROM match m
            JOIN season s ON s.id = m.season_id AND s.match_data_complete = 1
            JOIN competition comp ON comp.id = s.competition_id
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
            "seasons": len(top_flight),
            "played": sum(s["played"] for s in finished),
            "won": sum(s["won"] for s in finished),
            "drawn": sum(s["drawn"] for s in finished),
            "lost": sum(s["lost"] for s in finished),
            "gf": sum(s["gf"] for s in finished),
            "ga": sum(s["ga"] for s in finished),
        }
        comp_order = ["allsvenskan", "damallsvenskan", "superettan"]
        competitions = []
        for code in comp_order:
            cs = [s for s in seasons if s["comp"] == code]
            if cs:
                competitions.append(
                    {"code": code, "name": cs[0]["comp_name"], "seasons": cs}
                )
        clubs.append(
            {
                "name": c["name"],
                "ns": c["ns"],
                "slug": slugify(c["name"]) + ("-dam" if c["ns"] == "dam" else ""),
                "wiki_page": c["wiki_page"],
                "competitions": competitions,
                "top_flight_name": "Damallsvenskan" if c["ns"] == "dam" else "Allsvenskan",
                "titles": titles,
                "best_position": best["position"] if best else None,
                "best_seasons": [s["season"] for s in top_flight if best and s["position"] == best["position"]],
                "biggest_win": dict(biggest_win) if biggest_win else None,
                "worst_loss": dict(worst_loss) if worst_loss else None,
                "totals": totals,
            }
        )
    return clubs


def export_seasons(conn: sqlite3.Connection) -> list[dict]:
    out = []
    for s in conn.execute(
        """
        SELECT s.*, comp.code AS comp, comp.name AS comp_name
        FROM season s JOIN competition comp ON comp.id = s.competition_id
        ORDER BY comp.code, s.start_year, s.label
        """
    ).fetchall():
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
                "comp": s["comp"],
                "comp_name": s["comp_name"],
                "slug": season_slug(s["comp"], s["label"]),
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
        "competitions": [
            {
                "code": code,
                "name": next(s["comp_name"] for s in seasons if s["comp"] == code),
                "seasons": sum(1 for s in seasons if s["comp"] == code),
                "complete": sum(
                    1 for s in seasons if s["comp"] == code and s["match_data_complete"]
                ),
            }
            for code in ["allsvenskan", "superettan", "damallsvenskan"]
            if any(s["comp"] == code for s in seasons)
        ],
        "sources": [
            {
                "name": "Svenska Wikipedia – säsongsartiklar",
                "url": "https://sv.wikipedia.org/wiki/Fotbollsallsvenskan",
                "role": "Tabeller och resultatmatriser: Allsvenskan 1924/25–idag, "
                        "Superettan 2000–idag, Damallsvenskan 1988–idag (CC BY-SA 4.0)",
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
