"""Corporate-action strike adjustment for B3 options.

B3 multiplies the strike (and quantity) by ``FatorPROPSTRIKE`` on the ex-date for
cash events (dividends, JCP). Using the UNADJUSTED strike after such an event
silently corrupts the IV (spec §6) — this guard is the cheap insurance.
"""
from __future__ import annotations


def adjust_strike(strike: float, fator_prop_strike: float) -> float:
    return round(strike * fator_prop_strike, 2)
