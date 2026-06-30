"""Portfolio risk: a second-order (delta-gamma-vega) scenario P&L.

A local Taylor approximation around the current book — honest about being an
approximation, not a full revaluation. Each position is shocked on *its own*
underlying's spot (a uniform % market move), so a mixed PETR4/VALE3 book is
handled correctly. Valid for moderate shocks; large moves need full repricing.
"""
from __future__ import annotations


def stress_pnl(positions: list[tuple[float, float, float, float]], shock: float, dvol: float = 0.0) -> float:
    """Approximate P&L for a uniform ``shock`` (fraction of spot) and ``dvol`` (vol points).

    ``positions`` is a list of (delta, gamma, vega, spot) where delta/gamma/vega
    are *position* greeks (already qty x per-contract x multiplier) and spot is the
    position's underlying price. P&L = delta*dS + 0.5*gamma*dS^2 + vega*dvol.
    """
    total = 0.0
    for delta, gamma, vega, spot in positions:
        ds = shock * (spot or 0.0)
        total += (delta or 0.0) * ds + 0.5 * (gamma or 0.0) * ds * ds + (vega or 0.0) * dvol
    return round(total, 2)


# the spot shocks (fractions) shown in the Carteira stress ladder
SPOT_SHOCKS = (-0.10, -0.05, -0.02, 0.0, 0.02, 0.05, 0.10)


def payoff_at_expiry(positions: list[tuple], shock: float) -> float:
    """Mark-to-market P&L at expiry for a uniform ``shock`` (fraction of spot).

    ``positions`` is a list of (kind, strike, spot, qty, mult, entry) where kind is
    None for a stock leg. Options settle to intrinsic; the P&L is relative to the
    current marks, so at shock 0 a long option already shows its lost time value.
    """
    total = 0.0
    for kind, strike, spot, qty, mult, entry, *_ in positions:
        s2 = (spot or 0.0) * (1.0 + shock)
        if kind is None:  # stock leg
            total += (qty or 0.0) * (s2 - (spot or 0.0))
        else:
            intrinsic = max(s2 - strike, 0.0) if kind == "call" else max(strike - s2, 0.0)
            total += (qty or 0.0) * mult * (intrinsic - (entry or 0.0))
    return round(total, 2)


def payoff_grid(lo: float = -0.30, hi: float = 0.30, n: int = 41) -> list[float]:
    """Evenly spaced spot shocks for the payoff/risk curve."""
    return [lo + (hi - lo) * i / (n - 1) for i in range(n)]
