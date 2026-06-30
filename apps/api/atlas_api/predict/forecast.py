"""Forecast de vol: HAR-Leverage + ensemble por média simples (pure-stdlib).

HAR-Leverage (Corsi-Renò LHAR): HAR-RV + um termo de leverage `β·1{r<0}·RV_d`,
montado como uma regressão de 5 features (HAR + coluna de leverage). Quando a
coluna de leverage é toda zero o sistema desacopla — os 4 coeficientes do HAR
ficam idênticos ao `fit_har`, então a previsão reduz EXATAMENTE ao HAR (a
previsão de leverage só pode ajudar se o sinal existir; senão, não atrapalha).

Combinação por **média simples** — não pesos ótimos (combination puzzle: pesos
estimados costumam piorar OOS; spec §83).
"""
from __future__ import annotations

from dataclasses import dataclass

from atlas_api.pricing.har import _solve, fit_har, forecast_har


@dataclass(frozen=True)
class VolForecast:
    """Previsão de vol com banda de incerteza. ``lo``/``hi`` vêm do conformal (Task 6)."""

    sigma: float
    lo: float
    hi: float

    def __post_init__(self) -> None:
        if not (self.sigma > 0):
            raise ValueError("sigma must be > 0")
        if not (self.lo <= self.sigma <= self.hi):
            raise ValueError("expected lo <= sigma <= hi")


def _fit_har_leverage(
    rv: list[float], neg_returns: list[float], *, weekly: int = 5, monthly: int = 21
) -> tuple[float, float, float, float, float]:
    """HAR + 1 coluna de leverage (`neg_returns[t-1]`). 5 features, mesma ridge do HAR."""
    rows: list[list[float]] = []
    targets: list[float] = []
    for t in range(monthly, len(rv)):
        rows.append([
            1.0,
            rv[t - 1],
            sum(rv[t - weekly:t]) / weekly,
            sum(rv[t - monthly:t]) / monthly,
            neg_returns[t - 1],
        ])
        targets.append(rv[t])
    if len(rows) < 5:
        raise ValueError("not enough data for HAR-Leverage (need > monthly + 5 points)")
    p = 5
    xtx = [[0.0] * p for _ in range(p)]
    xty = [0.0] * p
    for i, row in enumerate(rows):
        for a in range(p):
            xty[a] += row[a] * targets[i]
            for b in range(p):
                xtx[a][b] += row[a] * row[b]
    for a in range(p):
        xtx[a][a] += 1e-8  # mesma ridge do fit_har — garante a redução exata ao HAR
    beta = _solve(xtx, xty)
    return (beta[0], beta[1], beta[2], beta[3], beta[4])


def har_leverage(
    rv: list[float], neg_returns: list[float], *, weekly: int = 5, monthly: int = 21
) -> tuple[float, float]:
    """``(base, lev)``: previsão HAR pura e previsão HAR-Leverage para o próximo passo.

    ``rv`` é a série de RV (de `series.rv_series`), `neg_returns` alinhado (de
    `series.neg_return_series`). Com `neg_returns` todo-zero, ``lev == base``.
    """
    base = forecast_har(fit_har(rv, weekly=weekly, monthly=monthly), rv, weekly=weekly, monthly=monthly)
    b0, bd, bw, bm, bl = _fit_har_leverage(rv, neg_returns, weekly=weekly, monthly=monthly)
    lev = (
        b0
        + bd * rv[-1]
        + bw * (sum(rv[-weekly:]) / weekly)
        + bm * (sum(rv[-monthly:]) / monthly)
        + bl * neg_returns[-1]
    )
    return base, lev


def vol_ensemble(forecasts: list[float]) -> float:
    """Média simples das previsões — NÃO pesos ótimos (combination puzzle)."""
    if not forecasts:
        raise ValueError("empty forecasts")
    return sum(forecasts) / len(forecasts)
