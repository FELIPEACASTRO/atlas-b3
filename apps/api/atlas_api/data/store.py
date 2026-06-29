"""SQLite-backed EOD store — the dependency-free implementation of the data cache.

ADR-003 targeted DuckDB/Parquet; sqlite3 (stdlib) is the first implementation:
zero dependency risk on Python 3.14, queryable, and swappable behind these
functions later without touching the API routes.
"""
from __future__ import annotations

import sqlite3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS instruments (
  ticker TEXT, tipo TEXT, ultimo REAL, var_pct REAL, liquidez REAL,
  iv REAL, iv_vs_rv TEXT, asof TEXT
);
CREATE TABLE IF NOT EXISTS options (
  underlying TEXT, ticker TEXT, kind TEXT, strike REAL, venc TEXT,
  last REAL, iv REAL, delta REAL, gamma REAL, vega REAL, asof TEXT
);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def reset(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM instruments")
    conn.execute("DELETE FROM options")


def insert_instruments(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    conn.executemany(
        "INSERT INTO instruments (ticker,tipo,ultimo,var_pct,liquidez,iv,iv_vs_rv,asof) "
        "VALUES (?,?,?,?,?,?,?,?)",
        rows,
    )


def insert_options(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    conn.executemany(
        "INSERT INTO options (underlying,ticker,kind,strike,venc,last,iv,delta,gamma,vega,asof) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO meta (k,v) VALUES (?,?)", (key, value))


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT v FROM meta WHERE k = ?", (key,)).fetchone()
    return row[0] if row else None


def query_screener(conn, *, tipo=None, min_liq=0.0, limit=200) -> list[dict]:
    sql = "SELECT * FROM instruments WHERE COALESCE(liquidez, 0) >= ?"
    args: list = [min_liq]
    if tipo:
        sql += " AND tipo = ?"
        args.append(tipo)
    sql += " ORDER BY liquidez DESC LIMIT ?"
    args.append(limit)
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def query_chain(conn, underlying: str, *, limit=500) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM options WHERE underlying = ? ORDER BY venc, strike LIMIT ?",
        (underlying, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM instruments").fetchone()[0]
