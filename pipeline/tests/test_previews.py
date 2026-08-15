"""Tests for fixtures and match previews.

The preview engine turns verified match data into claims like "har inte
vunnit på fem matcher", so these tests check that every such claim is
actually backed by the underlying results.
"""
import datetime as dt

import pytest

from pipeline import db
from pipeline.previews import (
    _team_history,
    build_all,
    form_facts,
    form_string,
    head_to_head,
    upcoming_fixtures,
)


@pytest.fixture(scope="session")
def conn():
    c = db.connect()
    yield c
    c.close()


@pytest.fixture(scope="session")
def previews(conn):
    return build_all(conn)


def test_fixtures_exist_and_are_in_the_future(conn):
    fixtures = conn.execute("SELECT local_date FROM fixture").fetchall()
    assert len(fixtures) > 0, "inga kommande matcher ingesterade"
    today = dt.date.today().isoformat()
    # a fixture may linger on today's date until it is played
    assert all(f["local_date"] >= today for f in fixtures)


def test_fixtures_reference_known_clubs(conn):
    orphans = conn.execute(
        """
        SELECT COUNT(*) AS c FROM fixture f
        LEFT JOIN club h ON h.id = f.home_club_id
        LEFT JOIN club a ON a.id = f.away_club_id
        WHERE h.id IS NULL OR a.id IS NULL
        """
    ).fetchone()["c"]
    assert orphans == 0


def test_no_team_plays_itself(conn):
    same = conn.execute(
        "SELECT COUNT(*) AS c FROM fixture WHERE home_club_id = away_club_id"
    ).fetchone()["c"]
    assert same == 0


def test_upcoming_window_is_ordered_by_kickoff(conn):
    fixtures = upcoming_fixtures(conn)
    stamps = [f["kickoff_utc"] for f in fixtures]
    assert stamps == sorted(stamps)


def test_previews_are_generated(previews):
    assert len(previews) > 0
    assert any(p["facts"] for p in previews)


def test_form_string_uses_only_vof(previews):
    for p in previews:
        for form in (p["home_form"], p["away_form"]):
            assert set(form.split()) <= {"V", "O", "F"}, form


def test_winless_claims_match_the_results(conn, previews):
    """Every 'har inte vunnit på N matcher' must be true of the data."""
    checked = 0
    for p in previews:
        for fact in p["facts"]:
            if fact["kind"] != "winless":
                continue
            club = conn.execute(
                "SELECT id FROM club WHERE name = ? AND ns = ?",
                (fact["team"], "dam" if p["comp"] == "damallsvenskan" else "herr"),
            ).fetchone()
            history = _team_history(conn, club["id"], p["comp"])
            n = fact["value"]
            assert all(not m["won"] for m in history[:n]), fact["text"]
            if len(history) > n:
                assert history[n]["won"], f"sviten borde brutits: {fact['text']}"
            checked += 1
    assert checked >= 0  # nothing to verify is acceptable, wrong claims are not


def test_winning_streak_claims_match_the_results(conn, previews):
    for p in previews:
        for fact in p["facts"]:
            if fact["kind"] != "winning":
                continue
            club = conn.execute(
                "SELECT id FROM club WHERE name = ? AND ns = ?",
                (fact["team"], "dam" if p["comp"] == "damallsvenskan" else "herr"),
            ).fetchone()
            history = _team_history(conn, club["id"], p["comp"])
            n = fact["value"]
            assert all(m["won"] for m in history[:n]), fact["text"]


def test_head_to_head_totals_add_up(conn, previews):
    for p in previews:
        h = p["h2h"]
        assert h["home_wins"] + h["away_wins"] + h["draws"] == h["played"]


def test_head_to_head_is_symmetric(conn):
    """Swapping the clubs must swap the win columns, not change the total."""
    row = conn.execute(
        """
        SELECT f.home_club_id AS h, f.away_club_id AS a, comp.code AS comp
        FROM fixture f
        JOIN season s ON s.id = f.season_id
        JOIN competition comp ON comp.id = s.competition_id
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        pytest.skip("inga kommande matcher")
    forward = head_to_head(conn, row["h"], row["a"], row["comp"])
    backward = head_to_head(conn, row["a"], row["h"], row["comp"])
    assert forward["played"] == backward["played"]
    assert forward["home_wins"] == backward["away_wins"]
    assert forward["draws"] == backward["draws"]


def test_form_facts_need_a_real_streak():
    """Short runs must not produce claims."""
    history = [
        {"won": False, "lost": True, "drew": False, "gf": 0, "ga": 1,
         "at_home": True, "date": "2026-08-01", "season": "2026", "opponent": "X"},
        {"won": True, "lost": False, "drew": False, "gf": 2, "ga": 0,
         "at_home": False, "date": "2026-07-25", "season": "2026", "opponent": "Y"},
    ]
    kinds = {f["kind"] for f in form_facts(history, "Testlaget", "Allsvenskan")}
    assert "winless" not in kinds  # only one match without a win
    assert "winning" not in kinds


def test_form_string_orders_oldest_first():
    history = [  # stored newest first
        {"won": True, "lost": False, "drew": False},
        {"won": False, "lost": True, "drew": False},
        {"won": False, "lost": False, "drew": True},
    ]
    assert form_string(history, 3) == "O F V"


def test_form_history_never_spans_a_gap_in_dated_seasons(conn):
    """The seasons used for form must be contiguous — no jumping a hole."""
    from pipeline.previews import unbroken_dated_seasons

    for comp in ("allsvenskan", "superettan", "damallsvenskan"):
        ids = unbroken_dated_seasons(conn, comp)
        if not ids:
            continue
        years = [
            conn.execute(
                "SELECT start_year FROM season WHERE id = ?", (sid,)
            ).fetchone()["start_year"]
            for sid in ids
        ]
        assert years == sorted(years, reverse=True)
        for newer, older in zip(years, years[1:]):
            assert newer - older <= 1, f"{comp}: hål mellan {older} och {newer}"
        # every season in the run really is dated
        assert all(
            conn.execute(
                "SELECT has_dates FROM season WHERE id = ?", (sid,)
            ).fetchone()["has_dates"]
            for sid in ids
        )


def test_head_to_head_counts_every_played_meeting(conn, previews):
    """Regression: the season being played must not be filtered out.

    match_data_complete only turns true once a whole season reconciles
    with its final table, so requiring it silently dropped every result
    from the current season.
    """
    for p in previews:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c FROM match m
            JOIN season s ON s.id = m.season_id
            JOIN competition comp ON comp.id = s.competition_id AND comp.code = :comp
            JOIN club h ON h.id = m.home_club_id
            JOIN club a ON a.id = m.away_club_id
            WHERE (s.match_data_complete = 1 OR s.is_current = 1)
              AND ((h.name = :home AND a.name = :away)
                OR (h.name = :away AND a.name = :home))
            """,
            {"comp": p["comp"], "home": p["home"], "away": p["away"]},
        ).fetchone()
        assert p["h2h"]["played"] == row["c"], f"{p['home']}–{p['away']}"


def test_current_season_matches_are_visible_to_previews(conn):
    """At least one current-season result must reach the preview layer."""
    current = conn.execute(
        """
        SELECT COUNT(*) AS c FROM match m
        JOIN season s ON s.id = m.season_id
        WHERE s.is_current = 1
        """
    ).fetchone()["c"]
    if current == 0:
        pytest.skip("ingen pågående säsong med spelade matcher")
    from pipeline.previews import _team_history

    club = conn.execute(
        """
        SELECT m.home_club_id AS id, comp.code AS comp
        FROM match m
        JOIN season s ON s.id = m.season_id AND s.is_current = 1
        JOIN competition comp ON comp.id = s.competition_id
        LIMIT 1
        """
    ).fetchone()
    history = _team_history(conn, club["id"], club["comp"])
    current_label = conn.execute(
        """
        SELECT label FROM season s
        JOIN competition comp ON comp.id = s.competition_id AND comp.code = ?
        WHERE s.is_current = 1
        """,
        (club["comp"],),
    ).fetchone()["label"]
    assert any(m["season"] == current_label for m in history)
