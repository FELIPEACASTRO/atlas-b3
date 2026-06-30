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
from atlas_api.pricing.american import american_greeks, american_iv
from atlas_api.pricing.features import put_call_ratio, skew_25d, vrp
from atlas_api.pricing.iv import iv_is_reliable
from atlas_api.pricing.rv import realized_vol
from atlas_api.pricing.signal import classify, iv_rank

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


def _pct_change(prev: float | None, last: float) -> float | None:
    """Percent change from a prior close, or None when there is no usable prior."""
    return round((last / prev - 1) * 100, 2) if prev else None


def ingest_cotahist(
    path: str,
    db_path: str,
    *,
    rate: float | None = None,
    q: float = 0.0,
    q_by_ticker: dict[str, float] | None = None,
) -> int:
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
    # real dividend yield per underlying (brapi); COTAHIST has none, so default q=0.
    q_map = q_by_ticker or {}

    conn = store.connect(db_path)
    store.upsert_prices(
        conn,
        [(qt.ticker, asof_s, qt.preco_abe, qt.preco_max, qt.preco_min, qt.preco_ult)
         for qt in stocks.values()],
    )

    opt_inst_rows: list[tuple] = []
    opt_rows: list[tuple] = []
    atm: dict[str, tuple[float, float]] = {}  # underlying -> (|strike-spot|, iv) of the ATM option
    vol_by_kind: dict[str, list[float]] = {}  # underlying -> [call_vol, put_vol]
    put_deltas: dict[str, list[tuple[float, float]]] = {}  # underlying -> [(delta, iv), ...]
    for qt in quotes:
        if qt.tipo not in ("call", "put"):
            continue
        if not code_consistent(qt.ticker, qt.tipo, qt.venc.month if qt.venc else None):
            continue
        underlying = stock_by_isin.get(qt.isin) or _guess_underlying(qt.ticker, stocks)
        base = stocks.get(underlying) if underlying else None
        if underlying and qt.volume:  # flow counts regardless of whether IV is reliable
            vol_by_kind.setdefault(underlying, [0.0, 0.0])[0 if qt.tipo == "call" else 1] += qt.volume
        iv = delta = gamma = vega = theta = None
        if base and qt.strike and qt.venc:
            T = _years_to_expiry(asof, qt.venc)
            q_u = q_map.get(underlying, q)  # real dividend yield when known, else 0
            # B3 equity options are AMERICAN: invert the Bjerksund-Stensland price
            # (validated vs CRR) so the early-exercise premium is not misread as IV.
            iv_val = american_iv(qt.tipo, qt.preco_ult, base.preco_ult, qt.strike, rate, q_u, T)
            # economic-validity gate, not just NaN: an at-intrinsic/stale EOD print
            # can yield an absurd vol (real data: 464%) that reprices with non-trivial
            # vega and would otherwise slip through. Suppress IV *and* its greeks, and
            # keep it out of the ATM pick so the underlying signal stays clean.
            if iv_is_reliable(qt.tipo, qt.preco_ult, base.preco_ult, qt.strike, iv_val):
                iv = round(iv_val, 4)
                g = american_greeks(qt.tipo, base.preco_ult, qt.strike, rate, q_u, T, iv_val)
                delta, gamma, vega = round(g["delta"], 4), round(g["gamma"], 6), round(g["vega"], 4)
                theta = round(g["theta"], 4)  # american_greeks theta is already per-day
                dist = abs(qt.strike - base.preco_ult)
                if underlying not in atm or dist < atm[underlying][0]:
                    atm[underlying] = (dist, iv_val)
                if qt.tipo == "put":
                    put_deltas.setdefault(underlying, []).append((delta, iv_val))
        opt_inst_rows.append((qt.ticker, qt.tipo, qt.preco_ult, None, qt.volume, iv, None, None, asof_s))
        if underlying:
            opt_rows.append((
                underlying, qt.ticker, qt.tipo, qt.strike,
                qt.venc.isoformat() if qt.venc else None,
                qt.preco_ult, iv, delta, gamma, vega, theta, asof_s,
            ))

    # persist today's ATM IV per underlying so IV Rank has a trailing window.
    store.upsert_iv_daily(
        conn, [(u, asof_s, round(iv_val, 4)) for u, (_d, iv_val) in atm.items()]
    )

    stock_inst_rows: list[tuple] = []
    feat_rows: list[tuple] = []
    for qt in stocks.values():
        closes = [c for (_o, _h, _l, c) in store.price_history(conn, qt.ticker)]
        # closes[-1] is today's close (just upserted); the prior session gives a
        # true day-over-day var. Fall back to intraday open only on the first session.
        prev_close = closes[-2] if len(closes) >= 2 else None
        var = _pct_change(prev_close, qt.preco_ult)
        if var is None and qt.preco_abe:
            var = _pct_change(qt.preco_abe, qt.preco_ult)
        rv_val = realized_vol(closes) if len(closes) >= _MIN_HISTORY else float("nan")
        atm_iv = atm[qt.ticker][1] if qt.ticker in atm else None
        sig = classify(atm_iv, rv_val) if (atm_iv is not None and rv_val == rv_val) else None
        iv_col = round(atm_iv, 4) if atm_iv is not None else None
        rank = iv_rank(store.iv_history(conn, qt.ticker), iv_col) if iv_col is not None else None
        stock_inst_rows.append((qt.ticker, "acao", qt.preco_ult, var, qt.volume, iv_col, sig, rank, asof_s))
        # labeled option features: variance premium, flow, OTM-put skew
        cvol, pvol = vol_by_kind.get(qt.ticker, [0.0, 0.0])
        rv_arg = rv_val if rv_val == rv_val else None
        feat = (
            vrp(atm_iv, rv_arg),
            put_call_ratio(cvol, pvol),
            skew_25d(put_deltas.get(qt.ticker, []), atm_iv),
        )
        if any(f is not None for f in feat):
            feat_rows.append((qt.ticker, feat[0], feat[1], feat[2], asof_s))

    store.reset(conn)
    store.insert_instruments(conn, stock_inst_rows + opt_inst_rows)
    store.insert_options(conn, opt_rows)
    store.insert_features(conn, feat_rows)
    store.set_meta(conn, "asof", asof_s)
    conn.commit()
    total = store.count(conn)
    conn.close()
    return total
