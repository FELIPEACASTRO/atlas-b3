"""IV-vs-RV heuristic classifier (rico / barato / neutro).

A labeled heuristic, never a recommendation: it states whether implied vol sits
above or below realized vol by more than ``band``. Nothing more.
"""
from __future__ import annotations


def classify(iv: float, rv: float, band: float = 0.10) -> str:
    if rv <= 0:
        return "neutro"
    if iv > rv * (1 + band):
        return "rico"
    if iv < rv * (1 - band):
        return "barato"
    return "neutro"
