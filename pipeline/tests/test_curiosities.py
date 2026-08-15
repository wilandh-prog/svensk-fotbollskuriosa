"""Curiosity engine tests against independently known historical facts.

These run against the real seeded database (data/svensk_fotboll.sqlite)
and pin well-documented Allsvenskan history: if an ingest regression
changes any of these answers, something is wrong with the data.
"""
import sqlite3

import pytest

from pipeline import db
from pipeline.curiosities import REGISTRY, load_modules


@pytest.fixture(scope="session")
def conn():
    c = db.connect()
    load_modules()
    yield c
    c.close()


def compute(conn, cid):
    return REGISTRY[cid].compute(conn)["items"]


def test_registry_has_at_least_15_curiosities():
    load_modules()
    assert len(REGISTRY) >= 15


def test_malmo_ff_unbeaten_1949_50_is_the_only_unbeaten_season(conn):
    items = compute(conn, "unbeaten-seasons")
    assert len(items) == 1
    assert items[0]["club"] == "Malmö FF"
    assert items[0]["season"] == "1949/1950"
    assert (items[0]["won"], items[0]["drawn"], items[0]["lost"]) == (20, 2, 0)


def test_billingsfors_winless_1946_47(conn):
    items = compute(conn, "winless-seasons")
    assert [(i["club"], i["season"]) for i in items] == [("Billingsfors IK", "1946/1947")]


def test_malmo_ff_most_league_titles(conn):
    items = compute(conn, "league-titles")
    top = items[0]
    assert top["club"] == "Malmö FF"
    # 25 first places through 2025 (seriesegrar, not SM titles):
    # the count only ever grows, so >= protects against ingest regressions
    assert top["titles"] >= 25


def test_ifk_goteborg_1982_won_regular_season(conn):
    row = conn.execute(
        """
        SELECT c.name FROM league_table lt
        JOIN season s ON s.id = lt.season_id
        JOIN club c ON c.id = lt.club_id
        WHERE s.label = '1982' AND lt.position = 1
        """
    ).fetchone()
    assert row["name"] == "IFK Göteborg"


def test_1982_ifk_goteborg_table_line(conn):
    row = conn.execute(
        """
        SELECT lt.* FROM league_table lt
        JOIN season s ON s.id = lt.season_id
        JOIN club c ON c.id = lt.club_id
        WHERE s.label = '1982' AND c.name = 'IFK Göteborg'
        """
    ).fetchone()
    assert (row["played"], row["won"], row["drawn"], row["lost"]) == (22, 11, 7, 4)
    assert (row["gf"], row["ga"], row["points"]) == (45, 22, 29)


def test_gais_won_first_season_1924_25(conn):
    row = conn.execute(
        """
        SELECT c.name FROM league_table lt
        JOIN season s ON s.id = lt.season_id
        JOIN club c ON c.id = lt.club_id
        WHERE s.label = '1924/1925' AND lt.position = 1
        """
    ).fetchone()
    assert row["name"] == "GAIS"


def test_first_season_had_12_teams_132_matches(conn):
    row = conn.execute(
        "SELECT num_teams, match_data_complete FROM season WHERE label = '1924/1925'"
    ).fetchone()
    assert row["num_teams"] == 12
    assert row["match_data_complete"] == 1
    n = conn.execute(
        """
        SELECT COUNT(*) AS c FROM match m
        JOIN season s ON s.id = m.season_id WHERE s.label = '1924/1925'
        """
    ).fetchone()["c"]
    assert n == 132


def test_biggest_win_is_at_least_nine_goal_margin(conn):
    items = compute(conn, "biggest-home-wins")
    top = items[0]
    assert top["home_goals"] - top["away_goals"] >= 9


def test_derby_stats_are_symmetric_and_nonempty(conn):
    derbies = compute(conn, "derby-alltime")
    assert {d["derby"] for d in derbies} == {"stockholm", "goteborg", "skane"}
    sthlm = next(d for d in derbies if d["derby"] == "stockholm")
    pairs = {(p["home"], p["away"]) for p in sthlm["pairs"]}
    assert ("AIK", "Djurgårdens IF") in pairs
    assert ("Djurgårdens IF", "AIK") in pairs
    aik_dif = next(p for p in sthlm["pairs"] if (p["home"], p["away"]) == ("AIK", "Djurgårdens IF"))
    assert aik_dif["matches"] > 50  # met at home in most shared seasons
    assert aik_dif["home_wins"] + aik_dif["draws"] + aik_dif["away_wins"] == aik_dif["matches"]


def test_maraton_table_includes_all_67_clubs_with_consistent_totals(conn):
    items = compute(conn, "maraton-table")
    assert len(items) == 67
    total_gf = sum(i["gf"] for i in items)
    total_ga = sum(i["ga"] for i in items)
    # annulled Malmö FF 1933/34 matches make GF/GA differ by exactly 11
    assert abs(total_gf - total_ga) == 11
    assert items[0]["club"] in {"Malmö FF", "IFK Göteborg"}


def test_ever_presents_leader_is_long_running_top_club(conn):
    items = compute(conn, "ever-presents")
    assert items[0]["len"] > 50
    assert items[0]["club"] in {"Malmö FF", "IFK Göteborg", "AIK"}


def test_every_curiosity_computes_and_has_coverage(conn):
    for cid, cur in REGISTRY.items():
        result = cur.compute(conn)
        assert result["coverage"].startswith("Allsvenskan"), cid
        assert isinstance(result["items"], list), cid


def test_no_curiosity_uses_incomplete_match_seasons(conn):
    """Matches from seasons flagged incomplete must never surface (except
    the explicitly current season)."""
    bad = conn.execute(
        """
        SELECT COUNT(*) AS c FROM match m
        JOIN season s ON s.id = m.season_id
        WHERE s.match_data_complete = 0 AND s.is_current = 0
        """
    ).fetchone()["c"]
    assert bad == 0
