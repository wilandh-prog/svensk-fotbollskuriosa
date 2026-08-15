"""Parsers for rendered Wikipedia season-article HTML.

Across all Allsvenskan seasons 1924/25-2026 the sv.wikipedia articles
share two table shapes (verified empirically over sampled seasons from
every era):

- league table: class "wikitable sortable", header row
  Nr | Lag | S | V | O | F | GM | IM | MS | P
- results matrix: class "wikitable", first header cell "Hemma \\ Borta",
  one row per home team (full club name), one column per away team
  (abbreviation, same order as the rows), cells like "2–1".
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

SCORE_RE = re.compile(r"^(\d+)\s*[–—-]\s*(\d+)")
FOOTNOTE_RE = re.compile(r"\[\s*[\w ]{1,4}\s*\]")
# Trailing status markers Wikipedia appends to team names in tables:
# (M) mästare, (RM) regerande mästare, (N) nykomling, (Kval) etc.
MARKER_RE = re.compile(r"\s*\((?:[A-ZÅÄÖa-zåäö]{1,4}|Kval)\)\s*$")


@dataclass
class TableRow:
    position: int
    team: str
    team_link: str | None
    played: int
    won: int
    drawn: int
    lost: int
    gf: int
    ga: int
    points: int


@dataclass
class MatrixMatch:
    home: str
    home_link: str | None
    away: str
    away_link: str | None
    home_goals: int
    away_goals: int
    # 'H'/'D'/'A' when the counted result differs from the goals
    # (matches awarded after protests or walkovers)
    awarded: str | None = None


def _cell_text(cell) -> str:
    txt = cell.get_text(" ", strip=True)
    txt = FOOTNOTE_RE.sub("", txt)
    return txt.strip()


def _team_cell(cell) -> tuple[str, str | None]:
    """Return (display name, wiki link title) for a team cell."""
    link = None
    a = cell.find("a")
    if a and a.get("title"):
        link = a["title"]
        # red links: title ends with "(sidan finns inte)" / "(page does not exist)"
        link = re.sub(r"\s*\((?:sidan finns inte|page does not exist)\)$", "", link)
    name = _cell_text(cell)
    name = MARKER_RE.sub("", name).strip()
    return name, link


def _int(txt: str) -> int:
    # first number token only — footnote digits after a space must not
    # be glued onto the value ("40 1" is 40, not 401)
    m = re.search(r"-?\d+", txt.replace("−", "-").replace("–", "-"))
    if not m:
        raise ValueError(f"no integer in {txt!r}")
    return int(m.group())


# column-name schemas: Swedish and English Wikipedia league tables
_SCHEMAS = [
    {"team": "Lag", "played": "S", "won": "V", "drawn": "O", "lost": "F",
     "gf": "GM", "ga": "IM", "points": "P", "pos": "Nr"},
    {"team": "Team", "played": "Pld", "won": "W", "drawn": "D", "lost": "L",
     "gf": "GF", "ga": "GA", "points": "Pts", "pos": "Pos"},
]


def parse_league_table(html: str) -> list[TableRow]:
    soup = BeautifulSoup(html, "lxml")
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 3:
            continue
        header = [_cell_text(c) for c in rows[0].find_all(["th", "td"])]
        schema = None
        for s in _SCHEMAS:
            needed = {s["team"], s["played"], s["won"], s["drawn"], s["lost"],
                      s["gf"], s["ga"], s["points"]}
            if len(header) >= 8 and needed.issubset(set(header)):
                schema = s
                break
        if schema is None:
            continue
        cols = ["played", "won", "drawn", "lost", "gf", "ga", "points"]
        idx = {c: header.index(schema[c]) for c in cols}
        idx["Lag"] = header.index(schema["team"])
        pos_idx = header.index(schema["pos"]) if schema["pos"] in header else None
        out: list[TableRow] = []
        for n, tr in enumerate(rows[1:], start=1):
            cells = tr.find_all(["th", "td"])
            if len(cells) < len(header) - 1:
                continue
            team, link = _team_cell(cells[idx["Lag"]])
            if not team:
                continue
            out.append(
                TableRow(
                    position=_int(_cell_text(cells[pos_idx])) if pos_idx is not None else n,
                    team=team,
                    team_link=link,
                    played=_int(_cell_text(cells[idx["played"]])),
                    won=_int(_cell_text(cells[idx["won"]])),
                    drawn=_int(_cell_text(cells[idx["drawn"]])),
                    lost=_int(_cell_text(cells[idx["lost"]])),
                    gf=_int(_cell_text(cells[idx["gf"]])),
                    ga=_int(_cell_text(cells[idx["ga"]])),
                    points=_int(_cell_text(cells[idx["points"]])),
                )
            )
        if len(out) >= 8:  # smallest historical league size is 10
            return out
    raise ValueError("no league table found")


def parse_result_matrix(html: str) -> tuple[
    list[MatrixMatch], list[tuple[tuple[str, str | None], tuple[str, str | None]]]
]:
    """Parse the home×away cross table.

    Returns (matches, missing) where `missing` lists (home, away) team
    pairs whose cell held no parseable score (walkovers, typos) so the
    ingester can try to derive them from the published league table.

    Column order is assumed to equal row order (true for every season
    article; violations are caught by the per-season sanity checks that
    compare matrix-derived goal sums with the published league table).
    """
    soup = BeautifulSoup(html, "lxml")
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 5:
            continue
        first = _cell_text(rows[0].find_all(["th", "td"])[0]) if rows[0].find_all(["th", "td"]) else ""
        sv = "Hemma" in first and "Bort" in first
        en = "Home" in first and "Away" in first
        if not (sv or en):
            continue
        body = rows[1:]
        teams: list[tuple[str, str | None]] = []
        grid: list[list[str]] = []
        for tr in body:
            cells = tr.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            team, link = _team_cell(cells[0])
            if not team:
                continue
            teams.append((team, link))
            grid.append([_cell_text(c) for c in cells[1:]])
        n = len(teams)
        if n < 8:
            continue
        out: list[MatrixMatch] = []
        missing: list[tuple[tuple[str, str | None], tuple[str, str | None]]] = []
        for i, row in enumerate(grid):
            if len(row) < n:
                continue
            for j in range(n):
                if i == j:
                    continue
                m = SCORE_RE.match(row[j])
                if not m:
                    missing.append((teams[i], teams[j]))
                    continue
                out.append(
                    MatrixMatch(
                        home=teams[i][0],
                        home_link=teams[i][1],
                        away=teams[j][0],
                        away_link=teams[j][1],
                        home_goals=int(m.group(1)),
                        away_goals=int(m.group(2)),
                    )
                )
        return out, missing
    return [], []
