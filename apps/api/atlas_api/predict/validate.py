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
