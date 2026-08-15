"""SQLite schema and helpers. All writes happen inside transactions."""
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "svensk_fotboll.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS competition (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS season (
    id INTEGER PRIMARY KEY,
    competition_id INTEGER NOT NULL REFERENCES competition(id),
    label TEXT NOT NULL,
    start_year INTEGER NOT NULL,
    end_year INTEGER NOT NULL,
    wiki_page TEXT,
    num_teams INTEGER,
    match_source TEXT,
    match_data_complete INTEGER NOT NULL DEFAULT 0,
    has_dates INTEGER NOT NULL DEFAULT 0,
    is_current INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    UNIQUE (competition_id, label)
);

CREATE TABLE IF NOT EXISTS club (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    -- 'herr' / 'dam': women's clubs live in their own namespace so a
    -- shared name (Hammarby IF, AIK) never merges two organisations
    ns TEXT NOT NULL DEFAULT 'herr',
    wiki_page TEXT,
    UNIQUE (name, ns)
);

CREATE TABLE IF NOT EXISTS club_alias (
    alias TEXT PRIMARY KEY,
    club_id INTEGER NOT NULL REFERENCES club(id)
);

CREATE TABLE IF NOT EXISTS league_table (
    season_id INTEGER NOT NULL REFERENCES season(id),
    position INTEGER NOT NULL,
    club_id INTEGER NOT NULL REFERENCES club(id),
    played INTEGER NOT NULL,
    won INTEGER NOT NULL,
    drawn INTEGER NOT NULL,
    lost INTEGER NOT NULL,
    gf INTEGER NOT NULL,
    ga INTEGER NOT NULL,
    points INTEGER NOT NULL,
    PRIMARY KEY (season_id, position)
);

CREATE TABLE IF NOT EXISTS match (
    id INTEGER PRIMARY KEY,
    season_id INTEGER NOT NULL REFERENCES season(id),
    round INTEGER,
    date TEXT,
    home_club_id INTEGER NOT NULL REFERENCES club(id),
    away_club_id INTEGER NOT NULL REFERENCES club(id),
    home_goals INTEGER NOT NULL,
    away_goals INTEGER NOT NULL,
    ht_home INTEGER,
    ht_away INTEGER,
    awarded_result TEXT CHECK (awarded_result IN ('H', 'D', 'A')),
    source TEXT NOT NULL
);

-- matches not yet played, from the league's own fixture API
CREATE TABLE IF NOT EXISTS fixture (
    id INTEGER PRIMARY KEY,
    season_id INTEGER NOT NULL REFERENCES season(id),
    external_id TEXT NOT NULL UNIQUE,
    round INTEGER,
    kickoff_utc TEXT NOT NULL,
    local_date TEXT NOT NULL,
    local_time TEXT,
    home_club_id INTEGER NOT NULL REFERENCES club(id),
    away_club_id INTEGER NOT NULL REFERENCES club(id),
    arena TEXT,
    status TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS fixture_by_date ON fixture (local_date);

CREATE UNIQUE INDEX IF NOT EXISTS match_unique
    ON match (season_id, home_club_id, away_club_id, IFNULL(date, ''));

CREATE INDEX IF NOT EXISTS match_by_date ON match (date);
CREATE INDEX IF NOT EXISTS match_by_clubs ON match (home_club_id, away_club_id);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def get_or_create_competition(conn: sqlite3.Connection, code: str, name: str) -> int:
    row = conn.execute("SELECT id FROM competition WHERE code = ?", (code,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO competition (code, name) VALUES (?, ?)", (code, name))
    return cur.lastrowid


def get_or_create_club(
    conn: sqlite3.Connection, canonical: str, wiki_page: str | None = None, ns: str = "herr"
) -> int:
    row = conn.execute(
        "SELECT id FROM club WHERE name = ? AND ns = ?", (canonical, ns)
    ).fetchone()
    if row:
        if wiki_page:
            conn.execute(
                "UPDATE club SET wiki_page = COALESCE(wiki_page, ?) WHERE id = ?",
                (wiki_page, row["id"]),
            )
        return row["id"]
    cur = conn.execute(
        "INSERT INTO club (name, ns, wiki_page) VALUES (?, ?, ?)", (canonical, ns, wiki_page)
    )
    return cur.lastrowid
