"""Ingestion job: COTAHIST -> accumulate OHLC history -> IV/greeks + realized vol
-> IV-vs-RV signal -> store.

The signal is computed at the UNDERLYING level: the underlying's realized vol
(from the accumulating daily history) vs its ATM option IV — not a single OTM
strike (which would just reflect skew). With < 3 sessions of history the RV is
not computable yet, so the signal is honestly None.
"""
from __future__ import annotations

import datetime as dt

from atlas_api.data import store
from atlas_api.data.bcb_sgs import fetch_annual_rate
from atlas_api.data.calendar_b3 import year_fraction
from atlas_api.data.cotahist import Quote, parse_file
from atlas_api.data.option_code import code_consistent
from atlas_api.pricing.bs import bs_greeks
from atlas_api.pricing.iv import implied_vol
from atlas_api.pricing.rv import realized_vol
from atlas_api.pricing.signal import classify

_SUFFIXES = ("4", "3", "11", "5", "6")
_DEFAULT_RATE = 0.1165
_MIN_HISTORY = 3  # closes needed for a realized-vol estimate


def _guess_underlying(option_ticker: str, stocks: dict[str, Quote]) -> str | None:
    root = option_ticker[:4]
    for suffix in _SUFFIXES:
        if root + suffix in stocks:
            return root + suffix
    return None


def _years_to_expiry(asof: dt.date, venc: dt.date) -> float:
    return year_fraction(asof, venc)


def ingest_cotahist(path: str, db_path: str, *, rate: float | None = None, q: float = 0.0) -> int:
    quotes = parse_file(path)
    if quotes and len({qt.data for qt in quotes}) > 1:
        # the daily file is mono-date; an annual file would make asof wrong and
        # mix sessions (audit finding). Ingest daily files.
        raise ValueError("COTAHIST multi-data (arquivo anual?) — ingira arquivos diários")
    asof = quotes[0].data if quotes else dt.date.today()
    asof_s = asof.isoformat()
    # rate=None -> the live BCB-SGS Selic (correct for today's file); historical
    # backfill should pass the era's rate explicitly.
    if rate is None:
        rate = fetch_annual_rate() or _DEFAULT_RATE
    stocks = {qt.ticker: qt for qt in quotes if qt.tipo == "acao"}
    stock_by_isin = {qt.isin: qt.ticker for qt in quotes if qt.tipo == "acao" and qt.isin}

    conn = store.connect(db_path)
    store.upsert_prices(
        conn,
        [(qt.ticker, asof_s, qt.preco_abe, qt.preco_max, qt.preco_min, qt.preco_ult)
         for qt in stocks.values()],
    )

    opt_inst_rows: list[tuple] = []
    opt_rows: list[tuple] = []
    atm: dict[str, tuple[float, float]] = {}  # underlying -> (|strike-spot|, iv) of the ATM option
    for qt in quotes:
        if qt.tipo not in ("call", "put"):
            continue
        if not code_consistent(qt.ticker, qt.tipo, qt.venc.month if qt.venc else None):
            continue
        underlying = stock_by_isin.get(qt.isin) or _guess_underlying(qt.ticker, stocks)
        base = stocks.get(underlying) if underlying else None
        iv = delta = gamma = vega = None
        if base and qt.strike and qt.venc:
            T = _years_to_expiry(asof, qt.venc)
            iv_val = implied_vol(qt.tipo, qt.preco_ult, base.preco_ult, qt.strike, rate, q, T)
            if iv_val == iv_val:  # not NaN
                iv = round(iv_val, 4)
                g = bs_greeks(qt.tipo, base.preco_ult, qt.strike, rate, q, T, iv_val)
                delta, gamma, vega = round(g["delta"], 4), round(g["gamma"], 6), round(g["vega"], 4)
                dist = abs(qt.strike - base.preco_ult)
                if underlying not in atm or dist < atm[underlying][0]:
                    atm[underlying] = (dist, iv_val)
        opt_inst_rows.append((qt.ticker, qt.tipo, qt.preco_ult, None, qt.volume, iv, None, asof_s))
        if underlying:
            opt_rows.append((
                underlying, qt.ticker, qt.tipo, qt.strike,
                qt.venc.isoformat() if qt.venc else None,
                qt.preco_ult, iv, delta, gamma, vega, asof_s,
            ))

    stock_inst_rows: list[tuple] = []
    for qt in stocks.values():
        var = round((qt.preco_ult / qt.preco_abe - 1) * 100, 2) if qt.preco_abe else None
        closes = [c for (_o, _h, _l, c) in store.price_history(conn, qt.ticker)]
        rv = realized_vol(closes) if len(closes) >= _MIN_HISTORY else float("nan")
        atm_iv = atm[qt.ticker][1] if qt.ticker in atm else None
        sig = classify(atm_iv, rv) if (atm_iv is not None and rv == rv) else None
        iv_col = round(atm_iv, 4) if atm_iv is not None else None
        stock_inst_rows.append((qt.ticker, "acao", qt.preco_ult, var, qt.volume, iv_col, sig, asof_s))

    store.reset(conn)
    store.insert_instruments(conn, stock_inst_rows + opt_inst_rows)
    store.insert_options(conn, opt_rows)
    store.set_meta(conn, "asof", asof_s)
    conn.commit()
    total = store.count(conn)
    conn.close()
    return total
