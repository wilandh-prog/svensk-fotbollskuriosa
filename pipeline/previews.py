"""Match previews: curiosities about the two teams in an upcoming fixture.

For every fixture in the near future this builds a list of statements
like "Hammarby har inte vunnit på fem matcher" or "AIK har inte slagit
Djurgården på Tele2 sedan 2018", each derived from verified match data.

Form runs are computed over matches that carry a date (the league API
supplies those back to the 1980s); all-time head-to-head figures use the
full verified history of the competition, which reaches back to 1924.
"""
from __future__ import annotations

import datetime as dt
import sqlite3

PREVIEW_WINDOW_DAYS = 21

_RESULT_CASE = """
    CASE WHEN m.awarded_result IS NOT NULL THEN m.awarded_result
         WHEN m.home_goals > m.away_goals THEN 'H'
         WHEN m.home_goals < m.away_goals THEN 'A'
         ELSE 'D' END
"""

# Individual results count as soon as they are played; match_data_complete
# only becomes true when a whole season reconciles with its final table,
# so requiring it here would silently drop the season being played.
_TRUSTED = "(s.match_data_complete = 1 OR s.is_current = 1)"


def upcoming_fixtures(conn: sqlite3.Connection, days: int = PREVIEW_WINDOW_DAYS) -> list[dict]:
    today = dt.date.today()
    horizon = (today + dt.timedelta(days=days)).isoformat()
    rows = conn.execute(
        """
        SELECT f.*, s.label AS season, comp.code AS comp, comp.name AS comp_name,
               h.name AS home, a.name AS away, h.ns AS ns
        FROM fixture f
        JOIN season s ON s.id = f.season_id
        JOIN competition comp ON comp.id = s.competition_id
        JOIN club h ON h.id = f.home_club_id
        JOIN club a ON a.id = f.away_club_id
        WHERE f.local_date >= ? AND f.local_date <= ?
        ORDER BY f.kickoff_utc, comp.code
        """,
        (today.isoformat(), horizon),
    ).fetchall()
    return [dict(r) for r in rows]


def unbroken_dated_seasons(conn: sqlite3.Connection, comp: str) -> list[int]:
    """Season ids forming the most recent gap-free run of dated seasons.

    A streak must never leap over a season we lack dates for, which would
    silently splice 2023 onto 2025 and turn two short runs into one long
    invented one. So the history stops at the first hole going backwards.
    """
    rows = conn.execute(
        """
        SELECT s.id, s.has_dates FROM season s
        JOIN competition comp ON comp.id = s.competition_id AND comp.code = ?
        ORDER BY s.start_year DESC, s.label DESC
        """,
        (comp,),
    ).fetchall()
    ids: list[int] = []
    for r in rows:
        if not r["has_dates"]:
            break
        ids.append(r["id"])
    return ids


def _team_history(conn: sqlite3.Connection, club_id: int, comp: str) -> list[dict]:
    """The club's dated matches in this competition, most recent first."""
    season_ids = unbroken_dated_seasons(conn, comp)
    if not season_ids:
        return []
    placeholders = ",".join(f":s{i}" for i in range(len(season_ids)))
    params = {"club": club_id, "comp": comp} | {
        f"s{i}": sid for i, sid in enumerate(season_ids)
    }
    rows = conn.execute(
        f"""
        SELECT m.date, m.home_club_id, m.away_club_id, m.home_goals, m.away_goals,
               s.label AS season, {_RESULT_CASE} AS result,
               o.name AS opponent,
               CASE WHEN m.home_club_id = :club THEN 1 ELSE 0 END AS at_home
        FROM match m
        JOIN season s ON s.id = m.season_id AND s.has_dates = 1
        JOIN competition comp ON comp.id = s.competition_id AND comp.code = :comp
        JOIN club o ON o.id = CASE WHEN m.home_club_id = :club
                                   THEN m.away_club_id ELSE m.home_club_id END
        WHERE (m.home_club_id = :club OR m.away_club_id = :club)
          AND m.date IS NOT NULL
          AND m.season_id IN ({placeholders})
        ORDER BY m.date DESC, m.id DESC
        """,
        params,
    ).fetchall()
    out = []
    for r in rows:
        at_home = bool(r["at_home"])
        gf, ga = (r["home_goals"], r["away_goals"]) if at_home else (r["away_goals"], r["home_goals"])
        won = r["result"] == ("H" if at_home else "A")
        lost = r["result"] == ("A" if at_home else "H")
        out.append(
            {
                "date": r["date"], "season": r["season"], "opponent": r["opponent"],
                "at_home": at_home, "gf": gf, "ga": ga,
                "won": won, "lost": lost, "drew": r["result"] == "D",
            }
        )
    return out


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one}" if n == 1 else f"{n} {many}"


def _sv_date(iso: str | None) -> str:
    if not iso:
        return ""
    months = ["", "januari", "februari", "mars", "april", "maj", "juni", "juli",
              "augusti", "september", "oktober", "november", "december"]
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {months[d.month]} {d.year}"


def form_facts(history: list[dict], team: str, comp_name: str) -> list[dict]:
    """Streaks and droughts from a team's recent matches."""
    facts: list[dict] = []
    if not history:
        return facts

    def run(pred) -> int:
        n = 0
        for m in history:
            if pred(m):
                n += 1
            else:
                break
        return n

    winless = run(lambda m: not m["won"])
    if winless >= 3:
        recent = history[:winless]
        draws = sum(1 for m in recent if m["drew"])
        losses = sum(1 for m in recent if m["lost"])
        last_win = next((m for m in history if m["won"]), None)
        text = (
            f"{team} har inte vunnit på {_plural(winless, 'match', 'matcher')} "
            f"i {comp_name} ({draws} oavgjorda, {losses} förluster)."
        )
        if last_win:
            text += f" Senaste segern kom mot {last_win['opponent']} den {_sv_date(last_win['date'])}."
        facts.append({"kind": "winless", "team": team, "value": winless, "text": text})

    wins = run(lambda m: m["won"])
    if wins >= 3:
        facts.append(
            {
                "kind": "winning", "team": team, "value": wins,
                "text": f"{team} har vunnit {_plural(wins, 'rak match', 'raka matcher')} i {comp_name}.",
            }
        )

    unbeaten = run(lambda m: not m["lost"])
    if unbeaten >= 5 and wins < unbeaten:
        facts.append(
            {
                "kind": "unbeaten", "team": team, "value": unbeaten,
                "text": f"{team} är obesegrat i {_plural(unbeaten, 'match', 'matcher')} i rad.",
            }
        )

    losses_run = run(lambda m: m["lost"])
    if losses_run >= 3:
        facts.append(
            {
                "kind": "losing", "team": team, "value": losses_run,
                "text": f"{team} har förlorat {_plural(losses_run, 'rak match', 'raka matcher')}.",
            }
        )

    scoreless = run(lambda m: m["gf"] == 0)
    if scoreless >= 2:
        facts.append(
            {
                "kind": "scoreless", "team": team, "value": scoreless,
                "text": f"{team} har inte gjort mål på {_plural(scoreless, 'match', 'matcher')}.",
            }
        )

    no_clean_sheet = run(lambda m: m["ga"] > 0)
    if no_clean_sheet >= 8:
        facts.append(
            {
                "kind": "no-clean-sheet", "team": team, "value": no_clean_sheet,
                "text": f"{team} har släppt in mål i {_plural(no_clean_sheet, 'match', 'matcher')} i följd.",
            }
        )

    conceding = run(lambda m: m["ga"] >= 2)
    if conceding >= 4:
        facts.append(
            {
                "kind": "leaky", "team": team, "value": conceding,
                "text": f"{team} har släppt in minst två mål i {_plural(conceding, 'match', 'matcher')} i rad.",
            }
        )

    venue = [m for m in history if m["at_home"]]
    venue_winless = 0
    for m in venue:
        if m["won"]:
            break
        venue_winless += 1
    if venue_winless >= 3:
        facts.append(
            {
                "kind": "home-winless", "team": team, "value": venue_winless,
                "text": f"{team} har inte vunnit på hemmaplan på {_plural(venue_winless, 'match', 'matcher')}.",
            }
        )

    away = [m for m in history if not m["at_home"]]
    away_winless = 0
    for m in away:
        if m["won"]:
            break
        away_winless += 1
    if away_winless >= 4:
        facts.append(
            {
                "kind": "away-winless", "team": team, "value": away_winless,
                "text": f"{team} har inte vunnit på bortaplan på {_plural(away_winless, 'match', 'matcher')}.",
            }
        )

    return facts


def form_string(history: list[dict], n: int = 5) -> str:
    """Last n results, oldest first: e.g. 'V O F V V'."""
    recent = list(reversed(history[:n]))
    return " ".join("V" if m["won"] else ("F" if m["lost"] else "O") for m in recent)


def head_to_head(conn: sqlite3.Connection, home_id: int, away_id: int, comp: str) -> dict:
    rows = conn.execute(
        f"""
        SELECT m.date, s.label AS season, m.home_club_id, m.away_club_id,
               m.home_goals, m.away_goals, {_RESULT_CASE} AS result
        FROM match m
        JOIN season s ON s.id = m.season_id AND {_TRUSTED}
        JOIN competition comp ON comp.id = s.competition_id AND comp.code = :comp
        WHERE (m.home_club_id = :h AND m.away_club_id = :a)
           OR (m.home_club_id = :a AND m.away_club_id = :h)
        ORDER BY s.start_year, m.date
        """,
        {"h": home_id, "a": away_id, "comp": comp},
    ).fetchall()
    meetings = []
    for r in rows:
        home_is_h = r["home_club_id"] == home_id
        winner = None
        if r["result"] == "H":
            winner = home_id if home_is_h else away_id
        elif r["result"] == "A":
            winner = away_id if home_is_h else home_id
        meetings.append(
            {
                "season": r["season"], "date": r["date"],
                "home_is_first": home_is_h,
                "home_goals": r["home_goals"], "away_goals": r["away_goals"],
                "winner": winner,
            }
        )
    return {
        "meetings": meetings,
        "played": len(meetings),
        "home_wins": sum(1 for m in meetings if m["winner"] == home_id),
        "away_wins": sum(1 for m in meetings if m["winner"] == away_id),
        "draws": sum(1 for m in meetings if m["winner"] is None),
    }


def h2h_facts(h2h: dict, home: str, away: str, home_id: int, away_id: int, comp_name: str) -> list[dict]:
    facts: list[dict] = []
    meetings = h2h["meetings"]
    if not meetings:
        facts.append(
            {
                "kind": "first-meeting", "team": None, "value": 0,
                "text": f"{home} och {away} har aldrig mötts i {comp_name}.",
            }
        )
        return facts

    facts.append(
        {
            "kind": "h2h-record", "team": None, "value": h2h["played"],
            "text": (
                f"Lagen har mötts {_plural(h2h['played'], 'gång', 'gånger')} i {comp_name}: "
                f"{home} har vunnit {h2h['home_wins']}, {away} {h2h['away_wins']}, "
                f"och {h2h['draws']} slutade oavgjort."
            ),
        }
    )

    last = meetings[-1]
    first_team, second_team = (home, away) if last["home_is_first"] else (away, home)
    when = _sv_date(last["date"]) if last["date"] else f"säsongen {last['season']}"
    if last["winner"] is None:
        text = (
            f"Senast lagen möttes ({when}) slutade det "
            f"{last['home_goals']}–{last['away_goals']}."
        )
    else:
        # state the score from the winner's side, not the home team's
        if last["home_goals"] > last["away_goals"]:
            winner, wg, lg = first_team, last["home_goals"], last["away_goals"]
        else:
            winner, wg, lg = second_team, last["away_goals"], last["home_goals"]
        where = "hemma" if winner == first_team else "borta"
        text = f"Senast lagen möttes ({when}) vann {winner} med {wg}–{lg} {where}."
    facts.append({"kind": "last-meeting", "team": None, "value": 0, "text": text})

    for club_id, name, other in ((home_id, home, away), (away_id, away, home)):
        wins = [m for m in meetings if m["winner"] == club_id]
        if not wins:
            facts.append(
                {
                    "kind": "never-beaten", "team": name, "value": 0,
                    "text": f"{name} har aldrig besegrat {other} i {comp_name}.",
                }
            )
            continue
        last_win = wins[-1]
        since = meetings[meetings.index(last_win) + 1:]
        if len(since) >= 4:
            when = _sv_date(last_win["date"]) if last_win["date"] else f"säsongen {last_win['season']}"
            facts.append(
                {
                    "kind": "winless-vs", "team": name, "value": len(since),
                    "text": (
                        f"{name} har inte besegrat {other} på "
                        f"{_plural(len(since), 'möte', 'möten')} — senaste segern kom {when}."
                    ),
                }
            )

    biggest = max(meetings, key=lambda m: abs(m["home_goals"] - m["away_goals"]))
    if abs(biggest["home_goals"] - biggest["away_goals"]) >= 4:
        first_team = home if biggest["home_is_first"] else away
        second_team = away if biggest["home_is_first"] else home
        when = _sv_date(biggest["date"]) if biggest["date"] else f"säsongen {biggest['season']}"
        facts.append(
            {
                "kind": "biggest-meeting", "team": None, "value": 0,
                "text": (
                    f"Största segern i mötet: {first_team}–{second_team} "
                    f"{biggest['home_goals']}–{biggest['away_goals']} ({when})."
                ),
            }
        )
    return facts


def _standing(conn: sqlite3.Connection, season_id: int, club_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT position, played, won, drawn, lost, gf, ga, points
        FROM league_table WHERE season_id = ? AND club_id = ?
        """,
        (season_id, club_id),
    ).fetchone()
    return dict(row) if row else None


def build_preview(conn: sqlite3.Connection, fixture: dict) -> dict:
    comp, comp_name = fixture["comp"], fixture["comp_name"]
    home_id, away_id = fixture["home_club_id"], fixture["away_club_id"]
    home, away = fixture["home"], fixture["away"]

    home_hist = _team_history(conn, home_id, comp)
    away_hist = _team_history(conn, away_id, comp)
    h2h = head_to_head(conn, home_id, away_id, comp)

    facts = (
        form_facts(home_hist, home, comp_name)
        + form_facts(away_hist, away, comp_name)
        + h2h_facts(h2h, home, away, home_id, away_id, comp_name)
    )

    return {
        "external_id": fixture["external_id"],
        "comp": comp,
        "comp_name": comp_name,
        "season": fixture["season"],
        "round": fixture["round"],
        "date": fixture["local_date"],
        "time": fixture["local_time"],
        "arena": fixture["arena"],
        "home": home,
        "away": away,
        "home_standing": _standing(conn, fixture["season_id"], home_id),
        "away_standing": _standing(conn, fixture["season_id"], away_id),
        "home_form": form_string(home_hist),
        "away_form": form_string(away_hist),
        "h2h": {k: v for k, v in h2h.items() if k != "meetings"},
        "facts": facts,
    }


def build_all(conn: sqlite3.Connection, days: int = PREVIEW_WINDOW_DAYS) -> list[dict]:
    return [build_preview(conn, f) for f in upcoming_fixtures(conn, days)]
