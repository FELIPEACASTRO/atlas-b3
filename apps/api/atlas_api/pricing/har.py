"""HAR-RV (Corsi 2009) by ordinary least squares — pure stdlib.

There is no maintained HAR library (only notebooks); the model *is* a linear
regression of next-period realized vol on its daily/weekly/monthly averages, so
we fit it directly via the normal equations, keeping the core dependency-free.
This replaces the weak ``rv.har_components`` proxy once a multi-day RV series is
available. Validate the coefficients offline against statsmodels/arch.
"""
from __future__ import annotations


def _solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting for a small dense system."""
    n = len(matrix)
    aug = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-15:
            raise ValueError("singular system (collinear features)")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        for r in range(n):
            if r != col:
                factor = aug[r][col] / aug[col][col]
                for c in range(col, n + 1):
                    aug[r][c] -= factor * aug[col][c]
    return [aug[i][n] / aug[i][i] for i in range(n)]


def fit_har(rv: list[float], *, weekly: int = 5, monthly: int = 22) -> tuple[float, float, float, float]:
    """Fit HAR-RV; return ``(beta0, beta_d, beta_w, beta_m)``.

    ``rv`` is a realized-vol (or variance) series, oldest first. Targets RV_t on
    [1, RV_{t-1}, mean(RV daily..weekly), mean(RV daily..monthly)].
    """
    rows: list[list[float]] = []
    targets: list[float] = []
    for t in range(monthly, len(rv)):
        rows.append([
            1.0,
            rv[t - 1],
            sum(rv[t - weekly:t]) / weekly,
            sum(rv[t - monthly:t]) / monthly,
        ])
        targets.append(rv[t])
    if len(rows) < 4:
        raise ValueError("not enough data for HAR (need > monthly + 4 points)")

    p = 4
    xtx = [[0.0] * p for _ in range(p)]
    xty = [0.0] * p
    for i, row in enumerate(rows):
        for a in range(p):
            xty[a] += row[a] * targets[i]
            for b in range(p):
                xtx[a][b] += row[a] * row[b]
    beta = _solve(xtx, xty)
    return (beta[0], beta[1], beta[2], beta[3])


def forecast_har(coef: tuple[float, float, float, float], rv: list[float], *, weekly: int = 5, monthly: int = 22) -> float:
    b0, bd, bw, bm = coef
    return (
        b0
        + bd * rv[-1]
        + bw * (sum(rv[-weekly:]) / weekly)
        + bm * (sum(rv[-monthly:]) / monthly)
    )
