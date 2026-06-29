"""Brazilian risk-free rate from the BCB SGS open API (stdlib urllib only).

Replaces a hardcoded flat rate in ingestion with a real, current annual rate —
no third-party dependency. Offline-safe: ``fetch_annual_rate`` returns None on
any error so the caller falls back to a default.

SGS series: 1178 = Selic annualized (base 252, % a.a.); 4389 = CDI annualized;
432 = Copom Selic target. (AIForge research finding: BCB-SGS for the DI/Selic.)
"""
from __future__ import annotations

import json
import urllib.request

_URL = "https://api.bcb.gov.br/dados/serie/bcdados.sgs.{code}/dados/ultimos/1?formato=json"


def parse_latest(payload: list[dict]) -> float:
    """Annual rate as a fraction from an SGS JSON payload (last 'valor' / 100)."""
    if not payload:
        raise ValueError("empty SGS payload")
    return float(payload[-1]["valor"]) / 100.0


def fetch_annual_rate(code: int = 1178, *, timeout: float = 5.0) -> float | None:
    """Fetch the latest annual rate (fraction) for an SGS series, or None on error."""
    try:
        req = urllib.request.Request(
            _URL.format(code=code), headers={"User-Agent": "atlas/0.1"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted host)
            payload = json.loads(resp.read().decode("utf-8"))
        return parse_latest(payload)
    except Exception:
        return None
