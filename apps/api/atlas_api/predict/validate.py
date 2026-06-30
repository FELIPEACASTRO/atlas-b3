"""O GATE — o verdadeiro produto: nada entra sem bater o HAR aqui (spec §90).

Forecast pontual: QLIKE (robusta a proxy ruidoso, sobre VARIÂNCIA) + Diebold-Mariano
com variância de longo prazo HAC (Newey-West, kernel de Bartlett) + walk-forward
estritamente point-in-time. Distribuição (CRPS/PIT/cobertura) entra na Task 7.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Iterator
from typing import Any

import numpy as np
from scipy import stats

_FLOOR = 1e-12  # piso p/ y, yhat: previsão de variância é estritamente positiva (evita log<=0)


def qlike(y, yhat):
    """QLIKE de Patton sobre **variância**: ``yhat/y - log(yhat/y) - 1`` (>=0, =0 na igualdade).

    Robusta a proxy de variância ruidoso. Exige ``y>0, yhat>0`` — aplica piso ``1e-12``
    (o forecast/walk-forward já entrega variância positiva). Escalar ou array.
    """
    y = np.maximum(np.asarray(y, dtype=float), _FLOOR)
    yhat = np.maximum(np.asarray(yhat, dtype=float), _FLOOR)
    r = yhat / y
    out = r - np.log(r) - 1.0
    return float(out) if out.ndim == 0 else out


def _loss(y: np.ndarray, f: np.ndarray, loss: str) -> np.ndarray:
    if loss == "qlike":
        return qlike(y, f)
    if loss == "mse":
        return (y - f) ** 2
    raise ValueError(f"unknown loss: {loss!r}")


def _newey_west_lag(n: int) -> int:
    """Truncamento automático de Newey-West: ``floor(4·(n/100)^(2/9))``."""
    return int(4.0 * (n / 100.0) ** (2.0 / 9.0))


def diebold_mariano(y, f1, f2, *, loss: str = "qlike") -> tuple[float, float]:
    """Teste DM de acurácia preditiva igual entre ``f1`` e ``f2`` contra realizado ``y``.

    Retorna ``(stat, p)`` bicaudal (t-Student, n-1 g.l.). ``stat<0`` => ``f1`` tem perda
    MENOR (é melhor). Variância de longo prazo via HAC Newey-West (kernel de Bartlett),
    robusta a autocorrelação dos diferenciais de perda.
    """
    y = np.asarray(y, dtype=float)
    f1 = np.asarray(f1, dtype=float)
    f2 = np.asarray(f2, dtype=float)
    d = _loss(y, f1, loss) - _loss(y, f2, loss)
    n = d.size
    if n < 2:
        raise ValueError("need >= 2 observations for Diebold-Mariano")
    dbar = float(d.mean())
    e = d - dbar
    g0 = float(e @ e) / n
    lag = _newey_west_lag(n)
    lrv = g0
    for k in range(1, lag + 1):
        w = 1.0 - k / (lag + 1.0)            # peso de Bartlett (garante variância >= 0)
        gk = float(e[k:] @ e[:-k]) / n
        lrv += 2.0 * w * gk
    if lrv <= 0.0:
        return 0.0, 1.0                      # diferenciais degenerados: sem evidência
    stat = dbar / math.sqrt(lrv / n)
    p = 2.0 * float(stats.t.cdf(-abs(stat), df=n - 1))
    return stat, p


def walk_forward(
    series: list[float],
    fit_fn: Callable[[list[float]], Any],
    predict_fn: Callable[[Any, list[float]], float],
    *,
    min_train: int,
) -> Iterator[tuple[float, float]]:
    """Gerador point-in-time: para cada ``t`` em ``[min_train, len)``, treina em
    ``series[:t]`` e prevê ``series[t]``. Yields ``(realizado, previsto)``. Sem look-ahead
    por construção — ``predict_fn`` nunca vê ``series[t:]``.
    """
    if min_train < 1:
        raise ValueError("min_train must be >= 1")
    for t in range(min_train, len(series)):
        train = series[:t]
        model = fit_fn(train)
        yield series[t], predict_fn(model, train)


# ---- Auditoria da distribuição (Task 7): CRPS + PIT + cobertura ----

_INV_SQRT_PI = 1.0 / math.sqrt(math.pi)


def crps_gaussian(y, mu, sigma):
    """CRPS de uma preditiva Normal, forma fechada de Gneiting: regra de pontuação própria.

    ``σ[z(2Φ(z)−1) + 2φ(z) − 1/√π]`` com ``z=(y−μ)/σ``. No limite ``σ→0`` tende a ``|y−μ|``.
    Menor é melhor; pontua a distribuição inteira (não só a média). Escalar ou array.
    """
    sigma = np.maximum(np.asarray(sigma, dtype=float), _FLOOR)
    z = (np.asarray(y, dtype=float) - np.asarray(mu, dtype=float)) / sigma
    out = sigma * (z * (2.0 * stats.norm.cdf(z) - 1.0) + 2.0 * stats.norm.pdf(z) - _INV_SQRT_PI)
    return float(out) if np.ndim(out) == 0 else out


def pit(y, cdf_fn) -> np.ndarray:
    """Probability Integral Transform: aplica a CDF preditiva aos realizados.

    Se o modelo é bem calibrado, ``pit(y, cdf)`` ~ Uniforme[0,1]. ``cdf_fn`` é a CDF
    preditiva (pode variar por observação se vier vetorizada).
    """
    return np.asarray(cdf_fn(np.asarray(y, dtype=float)), dtype=float)


def pit_uniformity(pit_vals) -> float:
    """p-valor do KS de ``pit_vals`` contra a Uniforme[0,1]. p>0.05 => não rejeita (calibrado)."""
    pit_vals = np.asarray(pit_vals, dtype=float)
    return float(stats.kstest(pit_vals, "uniform").pvalue)


def coverage(y, lo, hi) -> float:
    """Fração dos realizados dentro do envelope ``[lo, hi]`` (deveria bater o nominal)."""
    y = np.asarray(y, dtype=float)
    return float(np.mean((y >= np.asarray(lo, dtype=float)) & (y <= np.asarray(hi, dtype=float))))
