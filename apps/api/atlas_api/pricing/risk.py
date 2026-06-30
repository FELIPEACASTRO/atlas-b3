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
