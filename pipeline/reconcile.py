"""Reconcile a parsed result matrix against the published league table.

Decides whether the match list is complete, recovers single missing
scores (walkovers, typos in the source) by diffing matrix sums against
the table, and detects annulled clubs (thrown out mid-season, their
matches voided — e.g. Malmö FF 1933/34).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .clubs import canonical_name
from .wikiparse import MatrixMatch, TableRow


@dataclass
class Reconciliation:
    complete: bool
    derived: list[MatrixMatch] = field(default_factory=list)
    note: str | None = None
    problems: list[str] = field(default_factory=list)


def _stats(matches: list[MatrixMatch], ns: str = "herr") -> dict[str, dict]:
    st: dict[str, dict] = {}
    for m in matches:
        h = canonical_name(m.home, m.home_link, ns)
        a = canonical_name(m.away, m.away_link, ns)
        for name in (h, a):
            st.setdefault(name, {"p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0})
        st[h]["p"] += 1; st[a]["p"] += 1
        st[h]["gf"] += m.home_goals; st[h]["ga"] += m.away_goals
        st[a]["gf"] += m.away_goals; st[a]["ga"] += m.home_goals
        if m.awarded:
            res = m.awarded
        elif m.home_goals > m.away_goals:
            res = "H"
        elif m.home_goals < m.away_goals:
            res = "A"
        else:
            res = "D"
        if res == "H":
            st[h]["w"] += 1; st[a]["l"] += 1
        elif res == "A":
            st[h]["l"] += 1; st[a]["w"] += 1
        else:
            st[h]["d"] += 1; st[a]["d"] += 1
    return st


def reconcile(
    table: list[TableRow],
    matches: list[MatrixMatch],
    missing: list[tuple[tuple[str, str | None], tuple[str, str | None]]],
    allow_derive: bool = True,
    ns: str = "herr",
) -> Reconciliation:
    tbl = {canonical_name(r.team, r.team_link, ns): r for r in table}
    matches = list(matches)
    derived: list[MatrixMatch] = []

    # Try to derive each missing cell: the table totals minus the matrix
    # sums for the two clubs pin down the score exactly. Only safe when
    # almost nothing is missing — with many empty cells (a season in
    # progress) the residuals would cascade into fabricated scores.
    if not allow_derive or len(missing) > 2:
        missing = []
    for (home, home_link), (away, away_link) in missing:
        st = _stats(matches, ns)
        h, a = canonical_name(home, home_link, ns), canonical_name(away, away_link, ns)
        if h not in tbl or a not in tbl:
            continue
        sh = st.get(h, {"gf": 0, "ga": 0})
        sa = st.get(a, {"gf": 0, "ga": 0})
        hg = tbl[h].gf - sh["gf"]
        ag = tbl[h].ga - sh["ga"]
        if hg < 0 or ag < 0:
            continue
        if tbl[a].gf - sa["gf"] != ag or tbl[a].ga - sa["ga"] != hg:
            continue
        m = MatrixMatch(home, home_link, away, away_link, hg, ag)
        matches.append(m)
        derived.append(m)

    st = _stats(matches, ns)

    # Detect awarded matches: every club's GF/GA and games played agree
    # with the table but W/D/L is off — a result was awarded by verdict
    # (protest, walkover) while the pitch score stood in the matrix.
    wdl_clubs = []
    goals_ok = True
    for name, row in tbl.items():
        got = st.get(name)
        if got is None:
            continue
        if (got["p"], got["gf"], got["ga"]) != (row.played, row.gf, row.ga):
            goals_ok = False
        elif (got["w"], got["d"], got["l"]) != (row.won, row.drawn, row.lost):
            wdl_clubs.append(name)
    if goals_ok and 2 <= len(wdl_clubs) <= 4:
        from itertools import product as _product

        cand = [
            m for m in matches
            if canonical_name(m.home, m.home_link, ns) in wdl_clubs
            and canonical_name(m.away, m.away_link, ns) in wdl_clubs
        ]
        if 0 < len(cand) <= 4:
            options = [None, "H", "D", "A"]
            for combo in _product(options, repeat=len(cand)):
                for m, o in zip(cand, combo):
                    m.awarded = o
                trial = _stats(matches, ns)
                if all(
                    (trial[c]["w"], trial[c]["d"], trial[c]["l"])
                    == (tbl[c].won, tbl[c].drawn, tbl[c].lost)
                    for c in wdl_clubs
                    if c in trial
                ):
                    break
            else:
                for m in cand:
                    m.awarded = None
            st = _stats(matches, ns)

    notes: list[str] = []
    for m in matches:
        if m.awarded:
            res = {"H": "hemmalaget", "A": "bortalaget", "D": "oavgjort"}[m.awarded]
            notes.append(
                f"Matchen {m.home}–{m.away} ({m.home_goals}–{m.away_goals}) "
                f"tilldömdes {res} genom beslut (protest/w.o.)."
            )
    problems = []
    for name, row in tbl.items():
        got = st.get(name)
        if got is None:
            # club absent from the matrix entirely: annulled if the table
            # shows it stripped of points (thrown out mid-season)
            if row.points == 0 and row.played < max(r.played for r in table):
                notes.append(
                    f"{name} uteslöts under säsongen; lagets {row.played} "
                    "matcher annullerades och ingår inte i matchdata."
                )
                continue
            problems.append(f"{name}: saknas helt i resultattabellen")
            continue
        want = (row.played, row.won, row.drawn, row.lost, row.gf, row.ga)
        have = (got["p"], got["w"], got["d"], got["l"], got["gf"], got["ga"])
        if want != have:
            problems.append(f"{name}: matris ger {have}, tabellen {want}")

    return Reconciliation(
        complete=not problems,
        derived=derived,
        note=" ".join(notes) if notes else None,
        problems=problems,
    )


def _pair_key(m: MatrixMatch, ns: str = "herr") -> tuple[str, str]:
    return (canonical_name(m.home, m.home_link, ns), canonical_name(m.away, m.away_link, ns))


def best_merge(
    table: list[TableRow],
    sv_matches: list[MatrixMatch],
    alt_matches: list[MatrixMatch],
    max_conflicts: int = 8,
    ns: str = "herr",
) -> tuple[list[MatrixMatch], Reconciliation] | None:
    """Repair single-cell typos in the sv matrix using an independently
    edited alternate matrix (en.wikipedia). For each cell where the two
    disagree, try both values and accept the combination under which the
    match list exactly reproduces the published league table.
    """
    from itertools import product

    sv = {_pair_key(m, ns): m for m in sv_matches}
    alt = {_pair_key(m, ns): m for m in alt_matches}
    conflicts = [
        k for k in sv
        if k in alt and (sv[k].home_goals, sv[k].away_goals) != (alt[k].home_goals, alt[k].away_goals)
    ]
    if len(conflicts) > max_conflicts:
        return None
    base = dict(sv)
    for k, m in alt.items():
        if k not in base:
            base[k] = m  # cells missing in sv (walkovers etc.)
    for choice in product((0, 1), repeat=len(conflicts)):
        trial = dict(base)
        for bit, k in zip(choice, conflicts):
            trial[k] = alt[k] if bit else sv[k]
        rec = reconcile(table, list(trial.values()), [], ns=ns)
        if rec.complete:
            return list(trial.values()), rec
    return None
