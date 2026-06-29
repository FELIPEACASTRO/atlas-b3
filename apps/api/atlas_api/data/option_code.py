"""B3 equity-option code convention: 4-letter root + series letter + strike.

The 5th letter encodes call/put + expiration month: calls A-L (Jan-Dec), puts
M-X (Jan-Dec). We use it to cross-check the COTAHIST ``TPMERC`` (call/put) and
``DATVEN`` (expiry month) — a disagreement flags a dirty or misparsed row, which
we then drop rather than feed a wrong IV downstream.

Source: AIForge — B3_Options_and_Derivatives_Brazil.md (B3 settlement-code spec).
"""
from __future__ import annotations

_CALL_LETTERS = "ABCDEFGHIJKL"  # Jan..Dec
_PUT_LETTERS = "MNOPQRSTUVWX"  # Jan..Dec


def parse_option_code(code: str) -> dict | None:
    """Return ``{root, kind, month}`` from a standard B3 equity-option code, or
    ``None`` when the code doesn't follow the monthly convention (weekly/odd
    series, index codes, etc.)."""
    if len(code) < 5:
        return None
    letter = code[4].upper()
    if letter in _CALL_LETTERS:
        return {"root": code[:4], "kind": "call", "month": _CALL_LETTERS.index(letter) + 1}
    if letter in _PUT_LETTERS:
        return {"root": code[:4], "kind": "put", "month": _PUT_LETTERS.index(letter) + 1}
    return None


def code_consistent(code: str, tpmerc_kind: str, venc_month: int | None) -> bool:
    """True if the code agrees with the COTAHIST kind and expiry month.

    Permissive by design: an unparseable code returns True (we don't reject what
    we can't check), so only a *contradiction* drops the row.
    """
    parsed = parse_option_code(code)
    if parsed is None:
        return True
    if parsed["kind"] != tpmerc_kind:
        return False
    if venc_month is not None and parsed["month"] != venc_month:
        return False
    return True
