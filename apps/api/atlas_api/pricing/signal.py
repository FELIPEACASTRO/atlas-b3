"""IV-vs-RV heuristic classifier (rico / barato / neutro / indisponivel).

A labeled heuristic, never a recommendation: it states whether implied vol sits
above or below realized vol by more than ``band``. Missing data (``nan``) is
surfaced as ``indisponivel`` rather than silently masked as ``neutro``.
"""
from __future__ import annotations

import math


def classify(iv: float, rv: float, band: float = 0.10) -> str:
    if math.isnan(iv) or math.isnan(rv):
        return "indisponivel"
    if rv <= 0:
        return "neutro"
    if iv > rv * (1 + band):
        return "rico"
    if iv < rv * (1 - band):
        return "barato"
    return "neutro"
