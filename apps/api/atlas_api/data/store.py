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
CREATE TABLE IF NOT EXISTS prices_daily (
  ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL,
  PRIMARY KEY (ticker, date)
);
CREATE TABLE IF NOT EXISTS positions (ticker TEXT PRIMARY KEY, qty REAL);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def reset(conn: sqlite3.Connection) -> None:
    # instruments/options are a per-day snapshot; prices_daily is the ACCUMULATING
    # history (never wiped) — that's what makes realized vol / the IV-vs-RV signal
    # possible. (audit root cause: the old full-wipe destroyed every prior day.)
    conn.execute("DELETE FROM instruments")
    conn.execute("DELETE FROM options")


def upsert_prices(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    """Accumulate daily OHLC, idempotent per (ticker, date)."""
    conn.executemany(
        "INSERT OR REPLACE INTO prices_daily (ticker,date,open,high,low,close) "
        "VALUES (?,?,?,?,?,?)",
        rows,
    )


def price_history(conn: sqlite3.Connection, ticker: str, *, limit: int = 90) -> list[tuple]:
    """Oldest-first OHLC history for a ticker (last ``limit`` sessions)."""
    rows = conn.execute(
        "SELECT open, high, low, close FROM prices_daily WHERE ticker = ? "
        "ORDER BY date DESC LIMIT ?",
        (ticker, limit),
    ).fetchall()
    return [(r["open"], r["high"], r["low"], r["close"]) for r in reversed(rows)]


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


def get_instrument(conn: sqlite3.Connection, ticker: str) -> dict | None:
    r = conn.execute("SELECT * FROM instruments WHERE ticker = ? LIMIT 1", (ticker,)).fetchone()
    return dict(r) if r else None


def get_option(conn: sqlite3.Connection, ticker: str) -> dict | None:
    r = conn.execute("SELECT * FROM options WHERE ticker = ? LIMIT 1", (ticker,)).fetchone()
    return dict(r) if r else None


# --- positions (user data; never wiped by reset) ---

def set_position(conn: sqlite3.Connection, ticker: str, qty: float) -> None:
    if qty == 0:
        conn.execute("DELETE FROM positions WHERE ticker = ?", (ticker,))
    else:
        conn.execute("INSERT OR REPLACE INTO positions (ticker, qty) VALUES (?, ?)", (ticker, qty))


def list_positions(conn: sqlite3.Connection) -> list[tuple]:
    rows = conn.execute("SELECT ticker, qty FROM positions ORDER BY ticker").fetchall()
    return [(r["ticker"], r["qty"]) for r in rows]


def remove_position(conn: sqlite3.Connection, ticker: str) -> None:
    conn.execute("DELETE FROM positions WHERE ticker = ?", (ticker,))
