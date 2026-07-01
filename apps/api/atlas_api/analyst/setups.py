"""Build a real defined-risk Setup from the store — shared by the /briefing API
and the chat `briefing` tool, so the Analyst screen and the chat can never report
different numbers for the same ticker (single source of truth).

Honesty: it never fabricates a number. If the closing marks can't form a genuine
credit spread (inverted/missing prices), it returns a reason instead of inventing
one. A leg with no stored delta is passed through as ``None``, not a guess.
"""
from __future__ import annotations

from datetime import date

from atlas_api.analyst.briefing import Briefing, Setup, build_briefing
from atlas_api.data import store
from atlas_api.pricing.rv import realized_vol

_RV_WINDOW = 21  # sessions of closes used for realized vol (one source for both surfaces)


def call_spread_briefing(conn, underlying: str, *, capital: float = 50000.0):
    """Return ``(Briefing, None)`` on success or ``(None, motivo)`` if it can't be
    built honestly. ``underlying`` is upper-cased here."""
    underlying = (underlying or "").upper().strip()
    stocks = [r for r in store.query_screener(conn, limit=10000) if r["ticker"] == underlying]
    if not stocks:
        return None, f"{underlying} não encontrado na base."
    spot = stocks[0].get("ultimo")
    closes = [c for (_d, c) in store.close_series(conn, underlying)][-_RV_WINDOW:]
    chain = store.query_chain(conn, underlying)
    asof = store.get_meta(conn, "asof") or ""
    rv = realized_vol(closes) if len(closes) >= 3 else float("nan")
    # a call usable as a spread leg needs IV, strike, expiry AND a traded price
    calls = [o for o in chain if o["kind"] == "call" and o.get("iv") is not None
             and o.get("strike") and o.get("venc") and o.get("last") is not None]
    if spot is None or rv != rv or len(calls) < 2:
        return None, (f"dados insuficientes para um briefing de {underlying} "
                      "(precisa de vol realizada + cadeia de calls com IV e preço).")

    near_venc = min(o["venc"] for o in calls)
    near = sorted((o for o in calls if o["venc"] == near_venc), key=lambda o: o["strike"])
    i = min(range(len(near)), key=lambda k: abs(near[k]["strike"] - spot))
    if i + 1 >= len(near):
        i = len(near) - 2
    short_leg, long_leg = near[i], near[i + 1]
    width = long_leg["strike"] - short_leg["strike"]
    credit = short_leg["last"] - long_leg["last"]
    if width <= 0 or credit <= 0:
        # inverted/stale wing marks -> not a real credit spread; don't mislabel it
        return None, (f"marcações de fechamento de {underlying} não formam uma trava de crédito "
                      "hoje (prêmios invertidos nas pontas).")

    dte = (date.fromisoformat(near_venc) - date.fromisoformat(asof)).days if asof else 21
    setup = Setup(
        ticker=short_leg["ticker"], underlying=underlying, structure="trava_alta_vendida",
        iv=short_leg["iv"], rv=round(rv, 4),
        max_gain_per_lot=round(credit, 2),
        max_loss_per_lot=round(min(width - credit, width), 2),  # a vertical can't lose more than its width
        breakeven=round(short_leg["strike"] + credit, 2),
        delta=short_leg.get("delta"),  # real or None — never a fabricated 0.3
        liquidity_brl=stocks[0].get("liquidez") or 0.0,
        dte=max(dte, 1), capital=capital,
    )
    return build_briefing(setup), None


__all__ = ["call_spread_briefing", "Briefing"]
