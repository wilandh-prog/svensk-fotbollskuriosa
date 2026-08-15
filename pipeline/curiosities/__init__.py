"""Curiosity engine.

Each curiosity is a small function over the SQLite DB, registered with
@curiosity(...). It takes (conn, comp) where `comp` is a competition
code, and returns a list of result items (dicts) — so the same
statistic can be computed for Allsvenskan, Superettan and
Damallsvenskan without duplicating any SQL.

Coverage (which seasons the statistic is computed over) is resolved
from the DB per coverage *kind* and competition, so every page can
print an honest data basis. A curiosity/competition pair with no
qualifying seasons is skipped entirely rather than shown empty.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Callable

REGISTRY: dict[str, "Curiosity"] = {}

# competitions in display order; the first one owns the root URLs
COMPETITIONS = ["allsvenskan", "superettan", "damallsvenskan"]

# SQL fragment every query uses to scope itself to one competition
COMP_FILTER = "s.competition_id = (SELECT id FROM competition WHERE code = :comp)"

# coverage kinds -> extra SQL filter over season
_COVERAGE_WHERE = {
    "tables": "1=1",
    "matches": "match_data_complete = 1",
    "dated": "has_dates = 1",
}


def competition_name(conn: sqlite3.Connection, comp: str) -> str:
    row = conn.execute("SELECT name FROM competition WHERE code = ?", (comp,)).fetchone()
    return row["name"] if row else comp


def coverage_seasons(conn: sqlite3.Connection, kind: str, comp: str) -> list[str]:
    where = _COVERAGE_WHERE[kind]
    rows = conn.execute(
        f"""
        SELECT label FROM season
        WHERE {where}
          AND competition_id = (SELECT id FROM competition WHERE code = ?)
        ORDER BY start_year, label
        """,
        (comp,),
    ).fetchall()
    return [r["label"] for r in rows]


def resolve_coverage(conn: sqlite3.Connection, kind: str, comp: str) -> str:
    labels = coverage_seasons(conn, kind, comp)
    if not labels:
        return ""
    total = conn.execute(
        """
        SELECT COUNT(*) AS n FROM season
        WHERE competition_id = (SELECT id FROM competition WHERE code = ?)
        """,
        (comp,),
    ).fetchone()["n"]
    span = f"{competition_name(conn, comp)} {labels[0]}–{labels[-1]}"
    if len(labels) < total:
        span += f" ({len(labels)} säsonger med tillräcklig data)"
    return span


@dataclass
class Curiosity:
    id: str
    title: str
    # either one string, or {comp_code: text, "*": fallback} when a
    # statistic needs a competition-specific caveat
    description: str | dict
    category: str  # streaks | records | anomalies | derbies | seasons | clubs
    coverage_kind: str  # tables | matches | dated
    competitions: tuple[str, ...]  # which competitions this makes sense for
    fn: Callable[[sqlite3.Connection, str], list[dict]] = field(repr=False, default=None)

    def compute(self, conn: sqlite3.Connection, comp: str) -> dict | None:
        coverage = resolve_coverage(conn, self.coverage_kind, comp)
        if not coverage:
            return None  # this competition has no qualifying data
        items = self.fn(conn, comp)
        if not items:
            return None  # nothing to show; don't publish an empty page
        description = self.description
        if isinstance(description, dict):
            description = description.get(comp, description["*"])
        return {
            "id": self.id,
            "comp": comp,
            "slug": self.id if comp == COMPETITIONS[0] else f"{comp}/{self.id}",
            "competition": competition_name(conn, comp),
            "title": self.title,
            "description": description,
            "category": self.category,
            "coverage": coverage,
            "items": items,
        }


def curiosity(
    id: str,
    title: str,
    description: str,
    category: str,
    coverage: str,
    competitions: tuple[str, ...] | list[str] = tuple(COMPETITIONS),
):
    def deco(fn):
        if id in REGISTRY:
            raise ValueError(f"duplicate curiosity id {id!r}")
        REGISTRY[id] = Curiosity(
            id, title, description, category, coverage, tuple(competitions), fn
        )
        return fn

    return deco


def load_modules():
    from . import tables, matches, dated, alltime  # noqa: F401


def compute_all(conn: sqlite3.Connection) -> list[dict]:
    """Compute every curiosity for every competition it applies to.

    Variants of the same statistic cross-link to each other so a reader
    on the Allsvenskan page can jump to the Superettan version.
    """
    load_modules()
    by_id: dict[str, list[dict]] = {}
    out: list[dict] = []
    for cur in REGISTRY.values():
        for comp in COMPETITIONS:
            if comp not in cur.competitions:
                continue
            result = cur.compute(conn, comp)
            if result is None:
                continue
            by_id.setdefault(cur.id, []).append(result)
            out.append(result)
    for results in by_id.values():
        for r in results:
            r["variants"] = [
                {"comp": o["comp"], "competition": o["competition"], "slug": o["slug"]}
                for o in results
                if o["comp"] != r["comp"]
            ]
    return out
