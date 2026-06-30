"""B3 fundamentals from the brapi.dev open API (stdlib urllib only).

Used to supply a *real dividend yield* ``q`` per ticker to the option pricer —
COTAHIST carries no dividend data, so the engine previously assumed ``q = 0``,
which biases IV/greeks on high-yield names (PETR4 ~7.5%: ATM IV off by ~+2.2
vol points, delta ~5%). Offline-safe: every fetch returns None / skips on error
so ingestion always falls back to ``q = 0``.

Free tier serves PETR4, VALE3, ITUB4, MGLU3 without a token; other tickers need
a Bearer/`?token=` (set ``BRAPI_TOKEN``). Quotes are EOD/delayed; do not
redistribute (brapi terms). See docs/research/07-aiforge-financial-markets-v2.md.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import urllib.parse
import urllib.request

_URL = "https://brapi.dev/api/quote/{ticker}?dividends=true"
_MAX_Q = 0.5  # sanity cap; a trailing-12m yield above 50% is a data glitch, not a real q


def _parse_date(s: str | None) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s[:10])
    except ValueError:
        return None


def dividend_yield_from_result(result: dict, asof: dt.date) -> float | None:
    """Trailing-12m cash dividend yield (fraction) from one brapi ``results`` item.

    Sums ``cashDividends.rate`` paid in the 365 days up to ``asof`` over the last
    price. Returns None when price or dividend data is unusable. Capped at
    ``_MAX_Q`` to keep a glitchy special-dividend record from poisoning the pricer.
    """
    price = result.get("regularMarketPrice")
    if not price or price <= 0:
        return None
    cds = (result.get("dividendsData") or {}).get("cashDividends") or []
    total = 0.0
    for c in cds:
        pd = _parse_date(c.get("paymentDate"))
        if pd is None:
            continue
        if 0 <= (asof - pd).days <= 365:
            try:
                total += float(c.get("rate") or 0.0)
            except (TypeError, ValueError):
                continue
    if total <= 0:
        return 0.0
    return min(total / price, _MAX_Q)


def fetch_dividend_yield(
    ticker: str, *, asof: dt.date | None = None, token: str | None = None, timeout: float = 5.0
) -> float | None:
    """Fetch trailing-12m dividend yield for one B3 ticker, or None on any error."""
    asof = asof or dt.date.today()
    token = token or os.environ.get("BRAPI_TOKEN")
    url = _URL.format(ticker=urllib.parse.quote(ticker))
    if token:
        url += "&token=" + urllib.parse.quote(token)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "atlas/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted host)
            payload = json.loads(resp.read().decode("utf-8"))
        results = payload.get("results") or []
        if not results:
            return None
        return dividend_yield_from_result(results[0], asof)
    except Exception:
        return None


def fetch_dividend_yields(
    tickers: list[str], *, asof: dt.date | None = None, token: str | None = None, timeout: float = 5.0
) -> dict[str, float]:
    """Best-effort map ticker -> dividend yield; tickers that fail are omitted."""
    out: dict[str, float] = {}
    for t in tickers:
        q = fetch_dividend_yield(t, asof=asof, token=token, timeout=timeout)
        if q is not None:
            out[t] = q
    return out
