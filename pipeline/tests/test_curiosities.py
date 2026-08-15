"""Curiosity engine tests against independently known historical facts.

These run against the real seeded database (data/svensk_fotboll.sqlite)
and pin well-documented Swedish football history: if an ingest or query
regression changes any of these answers, something is wrong.
"""
import pytest

from pipeline import db
from pipeline.curiosities import COMPETITIONS, REGISTRY, compute_all, load_modules


@pytest.fixture(scope="session")
def conn():
    c = db.connect()
    load_modules()
    yield c
    c.close()


@pytest.fixture(scope="session")
def all_results(conn):
    return compute_all(conn)


def compute(conn, cid, comp="allsvenskan"):
    result = REGISTRY[cid].compute(conn, comp)
    assert result is not None, f"{cid} produced nothing for {comp}"
    return result["items"]


# --- engine ----------------------------------------------------------


def test_registry_has_at_least_15_curiosities():
    load_modules()
    assert len(REGISTRY) >= 15


def test_every_curiosity_computes_and_has_coverage(conn):
    for cid, cur in REGISTRY.items():
        for comp in COMPETITIONS:
            result = cur.compute(conn, comp)
            if result is None:
                continue  # competition lacks the data this one needs
            assert result["coverage"], cid
            assert result["items"], cid
            assert result["comp"] == comp


def test_variants_cross_link_symmetrically(all_results):
    by_key = {(r["id"], r["comp"]): r for r in all_results}
    for (cid, comp), r in by_key.items():
        for v in r["variants"]:
            assert (cid, v["comp"]) in by_key
            assert v["comp"] != comp
            back = by_key[(cid, v["comp"])]["variants"]
            assert any(b["comp"] == comp for b in back)


def test_allsvenskan_owns_the_root_urls(all_results):
    for r in all_results:
        if r["comp"] == "allsvenskan":
            assert r["slug"] == r["id"]
        else:
            assert r["slug"] == f"{r['comp']}/{r['id']}"


def test_dated_curiosities_only_where_dates_exist(conn):
    # only Allsvenskan has per-match dates ingested
    assert REGISTRY["on-this-day"].compute(conn, "superettan") is None
    assert REGISTRY["longest-unbeaten-runs"].compute(conn, "damallsvenskan") is None
    assert REGISTRY["longest-unbeaten-runs"].compute(conn, "allsvenskan") is not None


# --- Allsvenskan facts -----------------------------------------------


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
    top = compute(conn, "league-titles")[0]
    assert top["club"] == "Malmö FF"
    # 25 first places through 2025; the count only grows
    assert top["titles"] >= 25


def test_ifk_goteborg_1982_won_regular_season(conn):
    row = conn.execute(
        """
        SELECT c.name FROM league_table lt
        JOIN season s ON s.id = lt.season_id
        JOIN club c ON c.id = lt.club_id
        WHERE s.label = '1982' AND lt.position = 1
          AND s.competition_id = (SELECT id FROM competition WHERE code = 'allsvenskan')
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
          AND s.competition_id = (SELECT id FROM competition WHERE code = 'allsvenskan')
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
    top = compute(conn, "biggest-home-wins")[0]
    assert top["home_goals"] - top["away_goals"] >= 9


def test_oster_won_allsvenskan_in_its_debut_season_1968(conn):
    top = compute(conn, "best-debut-seasons")[0]
    assert top["club"] == "Östers IF"
    assert top["season"] == "1968"
    assert top["position"] == 1


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


def test_position_swings_are_within_league_size(conn):
    for cid in ("biggest-drop", "biggest-climb"):
        for i in compute(conn, cid):
            assert abs(i["change"]) < i["num_teams"]
            assert 1 <= i["from_position"] and 1 <= i["to_position"]


def test_gd_paradox_pairs_are_really_out_of_order(conn):
    for i in compute(conn, "gd-paradox"):
        assert i["pos_above"] < i["pos_below"]
        assert i["gd_above"] < i["gd_below"]
        assert i["pts_above"] >= i["pts_below"]


# --- other competitions ----------------------------------------------


def test_rosengard_dominates_damallsvenskan(conn):
    top = compute(conn, "league-titles", "damallsvenskan")[0]
    assert top["club"] == "FC Rosengård"
    assert top["titles"] >= 13


def test_umea_ik_won_damallsvenskan_2000_2002(conn):
    umea = next(
        i for i in compute(conn, "league-titles", "damallsvenskan")
        if i["club"] == "Umeå IK FF"
    )
    for year in ("2000", "2001", "2002"):
        assert year in umea["seasons"]


def test_superettan_starts_in_2000(conn):
    row = conn.execute(
        """
        SELECT MIN(label) AS first, COUNT(*) AS n FROM season
        WHERE competition_id = (SELECT id FROM competition WHERE code = 'superettan')
        """
    ).fetchone()
    assert row["first"] == "2000"
    assert row["n"] >= 27


def test_womens_and_mens_clubs_never_share_a_row(conn):
    """Hammarby, AIK and Djurgården exist in both namespaces and must stay
    two separate clubs with separate histories."""
    for name in ("Hammarby IF", "AIK", "Djurgårdens IF"):
        rows = conn.execute("SELECT ns FROM club WHERE name = ?", (name,)).fetchall()
        assert {r["ns"] for r in rows} == {"herr", "dam"}, name
    herr = conn.execute(
        """
        SELECT COUNT(*) AS c FROM league_table lt
        JOIN club c ON c.id = lt.club_id
        JOIN season s ON s.id = lt.season_id
        WHERE c.name = 'Hammarby IF' AND c.ns = 'herr'
          AND s.competition_id = (SELECT id FROM competition WHERE code = 'damallsvenskan')
        """
    ).fetchone()["c"]
    assert herr == 0


# --- data integrity ---------------------------------------------------


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


def test_awarded_matches_are_counted_by_verdict_not_score(conn):
    """The two known awarded matches must not be scored by goals alone."""
    rows = conn.execute(
        """
        SELECT m.awarded_result, m.home_goals, m.away_goals
        FROM match m WHERE m.awarded_result IS NOT NULL
        """
    ).fetchall()
    assert len(rows) >= 1
    for r in rows:
        natural = (
            "H" if r["home_goals"] > r["away_goals"]
            else "A" if r["home_goals"] < r["away_goals"] else "D"
        )
        assert r["awarded_result"] != natural
