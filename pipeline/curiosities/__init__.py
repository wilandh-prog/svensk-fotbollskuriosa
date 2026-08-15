"""Curiosity engine.

Each curiosity is a small function over the SQLite DB, registered with
@curiosity(...). It returns a list of result items (dicts). Coverage
(which seasons the statistic is computed over) is resolved from the DB
per coverage *kind*, so every page can print an honest data basis.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Callable

REGISTRY: dict[str, "Curiosity"] = {}

# coverage kinds -> SQL filter over season
_COVERAGE_WHERE = {
    "tables": "1=1",
    "matches": "match_data_complete = 1",
    "dated": "has_dates = 1",
}


def resolve_coverage(conn: sqlite3.Connection, kind: str) -> str:
    where = _COVERAGE_WHERE[kind]
    rows = conn.execute(
        f"SELECT label FROM season WHERE {where} ORDER BY start_year, label"
    ).fetchall()
    labels = [r["label"] for r in rows]
    if not labels:
        return "ingen data"
    total = conn.execute("SELECT COUNT(*) AS n FROM season").fetchone()["n"]
    span = f"Allsvenskan {labels[0]}–{labels[-1]}"
    if len(labels) < total:
        span += f" ({len(labels)} säsonger med tillräcklig data)"
    return span


@dataclass
class Curiosity:
    id: str
    title: str
    description: str
    category: str  # streaks | records | anomalies | derbies | seasons | clubs
    coverage_kind: str  # tables | matches | dated
    fn: Callable[[sqlite3.Connection], list[dict]] = field(repr=False, default=None)

    def compute(self, conn: sqlite3.Connection) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "coverage": resolve_coverage(conn, self.coverage_kind),
            "items": self.fn(conn),
        }


def curiosity(id: str, title: str, description: str, category: str, coverage: str):
    def deco(fn):
        if id in REGISTRY:
            raise ValueError(f"duplicate curiosity id {id!r}")
        REGISTRY[id] = Curiosity(id, title, description, category, coverage, fn)
        return fn

    return deco


def load_modules():
    from . import tables, matches, dated, alltime  # noqa: F401


def compute_all(conn: sqlite3.Connection) -> list[dict]:
    load_modules()
    return [c.compute(conn) for c in REGISTRY.values()]
