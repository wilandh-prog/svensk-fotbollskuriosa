"""Ingest from the leagues' own match API (gql.sportomedia.se).

This is the public GraphQL endpoint that allsvenskan.se, superettan.se
and damallsvenskan.se themselves read from. It gives two things no other
free source does:

- **upcoming fixtures** with kickoff time, round and arena, and
- **played matches with dates** for recent decades, which is what turns
  "biggest win ever" into "hasn't won in five matches".

Finished seasons are only accepted when the API's match list exactly
reproduces the season's published final table (same reconciliation rule
as the Wikipedia matrices), so dates never come at the cost of accuracy.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from zoneinfo import ZoneInfo

from . import db
from .clubs import canonical_name
from .fetch import FetchError, cached_post_json
from .reconcile import reconcile
from .wikiparse import MatrixMatch

GQL_URL = "https://gql.sportomedia.se/graphql"
STOCKHOLM = ZoneInfo("Europe/Stockholm")
DAY_S = 24 * 3600

# competition code -> (API league name, earliest season worth asking for)
API_LEAGUES = {
    "allsvenskan": ("allsvenskan", 1985),
    "superettan": ("superettan", 2000),
    "damallsvenskan": ("damallsvenskan", 1988),
}

QUERY = """
query matchesForLeague($configLeagueName: String!, $configSeasonStartYear: Int!) {
  matchesForLeague(
    configLeagueName: $configLeagueName
    configSeasonStartYear: $configSeasonStartYear
  ) {
    matches {
      id
      startDate
      round
      status
      arenaName
      homeTeamName
      visitingTeamName
      homeTeamScore
      visitingTeamScore
    }
  }
}
"""


def fetch_season(league: str, year: int, *, fresh: bool) -> list[dict]:
    data = cached_post_json(
        GQL_URL,
        {
            "query": QUERY,
            "variables": {"configLeagueName": league, "configSeasonStartYear": year},
        },
        # only the running season can change; older ones are immutable
        max_age_s=3 * 3600 if fresh else None,
    )
    payload = (data.get("data") or {}).get("matchesForLeague") or {}
    return payload.get("matches") or []


def _local(iso: str) -> tuple[str, str, str]:
    """UTC ISO -> (utc iso, local date, local HH:MM) in Swedish time."""
    stamp = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    local = stamp.astimezone(STOCKHOLM)
    return stamp.isoformat(), local.date().isoformat(), local.strftime("%H:%M")


def _as_matrix(matches: list[dict]) -> list[MatrixMatch]:
    out = []
    for m in matches:
        out.append(
            MatrixMatch(
                home=m["homeTeamName"],
                home_link=None,
                away=m["visitingTeamName"],
                away_link=None,
                home_goals=int(m["homeTeamScore"]),
                away_goals=int(m["visitingTeamScore"]),
            )
        )
    return out


def _table_rows(conn: sqlite3.Connection, season_id: int):
    """Published final table in the shape reconcile() expects."""
    from .wikiparse import TableRow

    rows = conn.execute(
        """
        SELECT lt.*, c.name AS club FROM league_table lt
        JOIN club c ON c.id = lt.club_id
        WHERE lt.season_id = ? ORDER BY lt.position
        """,
        (season_id,),
    ).fetchall()
    return [
        TableRow(
            position=r["position"], team=r["club"], team_link=None,
            played=r["played"], won=r["won"], drawn=r["drawn"], lost=r["lost"],
            gf=r["gf"], ga=r["ga"], points=r["points"],
        )
        for r in rows
    ]


def _align_names(
    finished: list[dict], table, ns: str
) -> tuple[dict[str, str], list[str]]:
    """Map API club names onto the names used in the published table.

    The API labels a club's whole history with its *current* name (the
    2003 matches of FC Café Opera are filed under Nordic United FC), so
    a plain alias table cannot resolve every season. Instead, unmatched
    names are paired by their season record: an API club is accepted as
    a table club only when played/won/drawn/lost/goals agree exactly and
    the pairing is unambiguous. A wrong guess cannot survive that test,
    and whatever is left unmatched makes the season fail verification.
    """
    stats: dict[str, dict] = {}
    for m in finished:
        h = canonical_name(m["homeTeamName"], None, ns)
        a = canonical_name(m["visitingTeamName"], None, ns)
        hg, ag = int(m["homeTeamScore"]), int(m["visitingTeamScore"])
        for name, gf, ga in ((h, hg, ag), (a, ag, hg)):
            s = stats.setdefault(name, {"p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0})
            s["p"] += 1
            s["gf"] += gf
            s["ga"] += ga
            s["w" if gf > ga else ("l" if gf < ga else "d")] += 1

    table_by_name = {canonical_name(r.team, None, ns): r for r in table}
    name_map = {n: n for n in stats if n in table_by_name}
    unmatched_api = [n for n in stats if n not in table_by_name]
    unmatched_tbl = [n for n in table_by_name if n not in stats]

    for api_name in list(unmatched_api):
        s = stats[api_name]
        record = (s["p"], s["w"], s["d"], s["l"], s["gf"], s["ga"])
        candidates = [
            t for t in unmatched_tbl
            if (
                table_by_name[t].played, table_by_name[t].won, table_by_name[t].drawn,
                table_by_name[t].lost, table_by_name[t].gf, table_by_name[t].ga,
            ) == record
        ]
        if len(candidates) == 1:
            name_map[api_name] = candidates[0]
            unmatched_tbl.remove(candidates[0])
            unmatched_api.remove(api_name)

    return name_map, unmatched_api


def ingest_season(
    conn: sqlite3.Connection, comp: str, comp_id: int, season: sqlite3.Row
) -> dict:
    league, _ = API_LEAGUES[comp]
    year = season["start_year"]
    current = bool(season["is_current"])
    try:
        matches = fetch_season(league, year, fresh=current)
    except FetchError as e:
        return {"season": season["label"], "status": f"fel: {e}"}
    if not matches:
        return {"season": season["label"], "status": "saknas i API:et"}

    ns = "dam" if comp == "damallsvenskan" else "herr"
    finished = [
        m for m in matches
        if m["status"] == "FINISHED"
        and m["homeTeamScore"] is not None
        and m["visitingTeamScore"] is not None
    ]
    upcoming = [m for m in matches if m["status"] != "FINISHED" and m["startDate"]]

    unknown: set[str] = set()
    name_map: dict[str, str] = {}

    def club_id(name: str) -> int | None:
        canonical = name_map.get(
            canonical_name(name, None, ns), canonical_name(name, None, ns)
        )
        row = conn.execute(
            "SELECT id FROM club WHERE name = ? AND ns = ?", (canonical, ns)
        ).fetchone()
        if row is None:
            unknown.add(f"{name} -> {canonical}")
            return None
        return row["id"]

    verified = False
    if not current and finished:
        # Only trust the API's history when it reproduces the published
        # table exactly; otherwise the Wikipedia matrix stays in charge.
        table = _table_rows(conn, season["id"])
        name_map, unmatched = _align_names(finished, table, ns)
        if unmatched:
            return {
                "season": season["label"],
                "status": "avvisad (okända lag: " + ", ".join(sorted(unmatched)) + ")",
            }
        matrix = _as_matrix(finished)
        for m in matrix:
            m.home = name_map.get(canonical_name(m.home, None, ns), m.home)
            m.away = name_map.get(canonical_name(m.away, None, ns), m.away)
        rec = reconcile(table, matrix, [], allow_derive=False, ns=ns)
        verified = rec.complete
        if not verified:
            return {
                "season": season["label"],
                "status": f"avvisad ({len(rec.problems)} avvikelser mot sluttabellen)",
            }

    with conn:
        if verified or current:
            rows = []
            for m in finished:
                h, a = club_id(m["homeTeamName"]), club_id(m["visitingTeamName"])
                if h is None or a is None:
                    continue
                _, local_date, _ = _local(m["startDate"]) if m["startDate"] else ("", None, "")
                rows.append(
                    (season["id"], m.get("round"), local_date, h, a,
                     int(m["homeTeamScore"]), int(m["visitingTeamScore"]))
                )
            if unknown:
                return {"season": season["label"], "status": "okända klubbar: " + "; ".join(sorted(unknown))}
            conn.execute("DELETE FROM match WHERE season_id = ?", (season["id"],))
            conn.executemany(
                """
                INSERT INTO match (season_id, round, date, home_club_id, away_club_id,
                                   home_goals, away_goals, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'sportomedia')
                """,
                rows,
            )
            conn.execute(
                """
                UPDATE season SET match_source = 'sportomedia', has_dates = 1,
                                  match_data_complete = ?
                WHERE id = ?
                """,
                (int(verified), season["id"]),
            )

        conn.execute("DELETE FROM fixture WHERE season_id = ?", (season["id"],))
        for m in upcoming:
            h, a = club_id(m["homeTeamName"]), club_id(m["visitingTeamName"])
            if h is None or a is None:
                continue
            utc, local_date, local_time = _local(m["startDate"])
            conn.execute(
                """
                INSERT INTO fixture (season_id, external_id, round, kickoff_utc,
                                     local_date, local_time, home_club_id, away_club_id,
                                     arena, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (external_id) DO NOTHING
                """,
                (season["id"], str(m["id"]), m.get("round"), utc, local_date, local_time,
                 h, a, (m.get("arenaName") or "").strip() or None, m["status"]),
            )

    return {
        "season": season["label"],
        "status": "ok",
        "finished": len(finished) if (verified or current) else 0,
        "upcoming": len(upcoming),
        "verified": verified,
        "current": current,
    }


def run(conn: sqlite3.Connection) -> list[dict]:
    out = []
    for comp, (_league, earliest) in API_LEAGUES.items():
        comp_id = conn.execute(
            "SELECT id FROM competition WHERE code = ?", (comp,)
        ).fetchone()
        if comp_id is None:
            continue
        comp_id = comp_id["id"]
        seasons = conn.execute(
            """
            SELECT * FROM season
            WHERE competition_id = ? AND start_year >= ? AND label NOT LIKE '%/%'
            ORDER BY start_year DESC
            """,
            (comp_id, earliest),
        ).fetchall()
        ok = dated = fixtures = 0
        for season in seasons:
            info = ingest_season(conn, comp, comp_id, season)
            out.append({"comp": comp} | info)
            if info["status"] == "ok":
                ok += 1
                dated += info["finished"]
                fixtures += info["upcoming"]
            elif info["status"] != "saknas i API:et":
                print(f"  {comp} {info['season']}: {info['status']}")
        print(f"{comp}: {ok} säsonger med datum ({dated} matcher), {fixtures} kommande matcher")
    return out


if __name__ == "__main__":
    conn = db.connect()
    run(conn)
    conn.close()
