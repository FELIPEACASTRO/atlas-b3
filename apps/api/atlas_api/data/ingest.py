"""Ingestion job: COTAHIST -> compute IV/greeks -> write to the store.

Maps each option to its underlying, computes IV with the NaN-safe solver and
greeks at that IV, and persists enriched rows. Options whose price violates the
no-arbitrage bounds (stale) get iv=None (honest), never a false number.
"""
from __future__ import annotations

import datetime as dt

from atlas_api.data import store
from atlas_api.data.cotahist import Quote, parse_file
from atlas_api.pricing.bs import bs_greeks
from atlas_api.pricing.iv import implied_vol

_SUFFIXES = ("4", "3", "11", "5", "6")


def _guess_underlying(option_ticker: str, stocks: dict[str, Quote]) -> str | None:
    root = option_ticker[:4]
    for suffix in _SUFFIXES:
        candidate = root + suffix
        if candidate in stocks:
            return candidate
    return None


def _years_to_expiry(asof: dt.date, venc: dt.date) -> float:
    return max((venc - asof).days, 1) / 365.0


def ingest_cotahist(path: str, db_path: str, *, rate: float = 0.1165, q: float = 0.0) -> int:
    quotes = parse_file(path)
    asof = quotes[0].data if quotes else dt.date.today()
    asof_s = asof.isoformat()
    stocks = {qt.ticker: qt for qt in quotes if qt.tipo == "acao"}

    inst_rows: list[tuple] = []
    opt_rows: list[tuple] = []
    for qt in quotes:
        if qt.tipo == "acao":
            var = round((qt.preco_ult / qt.preco_abe - 1) * 100, 2) if qt.preco_abe else 0.0
            inst_rows.append((qt.ticker, "acao", qt.preco_ult, var, qt.volume, None, None, asof_s))
            continue

        underlying = _guess_underlying(qt.ticker, stocks)
        base = stocks.get(underlying) if underlying else None
        iv = delta = gamma = vega = None
        if base and qt.strike and qt.venc:
            T = _years_to_expiry(asof, qt.venc)
            iv_val = implied_vol(qt.tipo, qt.preco_ult, base.preco_ult, qt.strike, rate, q, T)
            if iv_val == iv_val:  # not NaN
                iv = round(iv_val, 4)
                g = bs_greeks(qt.tipo, base.preco_ult, qt.strike, rate, q, T, iv_val)
                delta = round(g["delta"], 4)
                gamma = round(g["gamma"], 6)
                vega = round(g["vega"], 4)
        inst_rows.append((qt.ticker, qt.tipo, qt.preco_ult, 0.0, qt.volume, iv, None, asof_s))
        if underlying:
            opt_rows.append((
                underlying, qt.ticker, qt.tipo, qt.strike,
                qt.venc.isoformat() if qt.venc else None,
                qt.preco_ult, iv, delta, gamma, vega, asof_s,
            ))

    conn = store.connect(db_path)
    store.reset(conn)
    store.insert_instruments(conn, inst_rows)
    store.insert_options(conn, opt_rows)
    store.set_meta(conn, "asof", asof_s)
    conn.commit()
    total = store.count(conn)
    conn.close()
    return total
