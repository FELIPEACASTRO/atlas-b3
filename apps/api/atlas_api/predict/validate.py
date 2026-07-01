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


# ---- Harness de multiple-testing (ML-2): Deflated Sharpe · MCS · Hansen SPA ----

_EULER = 0.5772156649015329          # constante de Euler-Mascheroni


def _expected_max_normal(n: int) -> float:
    """E[máx de n normais padrão iid] (aprox. de López de Prado via estatística de ordem)."""
    if n < 2:
        return 0.0
    return (1.0 - _EULER) * float(stats.norm.ppf(1.0 - 1.0 / n)) + _EULER * float(
        stats.norm.ppf(1.0 - 1.0 / (n * math.e))
    )


def deflated_sharpe(returns, trial_sharpes) -> float:
    """Deflated Sharpe Ratio (López de Prado 2014): P(Sharpe verdadeiro > 0) descontando o
    multiple-testing (nº de tentativas) e a não-normalidade (skew/curtose). Em [0,1]."""
    r = np.asarray(returns, dtype=float)
    ts = np.asarray(trial_sharpes, dtype=float)
    n = r.size
    sd = r.std(ddof=1)
    if sd <= 0 or n < 3:
        return 0.0
    sr = float(r.mean() / sd)
    z = (r - r.mean()) / sd
    skew = float(np.mean(z ** 3))
    kurt = float(np.mean(z ** 4))                       # não-excesso (normal = 3)
    n_trials = ts.size
    sr0 = math.sqrt(float(np.var(ts, ddof=1))) * _expected_max_normal(n_trials) if n_trials >= 2 else 0.0
    denom = math.sqrt(max(1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr, 1e-12))
    return float(stats.norm.cdf((sr - sr0) * math.sqrt(n - 1) / denom))


def _block_bootstrap_index(n: int, block: int, rng) -> np.ndarray:
    """Índices de um bootstrap de blocos circular (preserva autocorrelação)."""
    idx: list[int] = []
    while len(idx) < n:
        start = int(rng.integers(0, n))
        idx.extend((start + np.arange(block)) % n)
    return np.asarray(idx[:n], dtype=int)


def model_confidence_set(losses: dict, *, alpha: float = 0.1, B: int = 500,
                         block: int = 10, seed: int = 0) -> set:
    """Model Confidence Set (Hansen-Lunde-Nason 2011): o conjunto de modelos indistinguíveis
    do melhor a confiança 1−α. Elimina o pior enquanto a igualdade de acurácia é rejeitada."""
    names = list(losses)
    L = np.column_stack([np.asarray(losses[k], dtype=float) for k in names])
    n = L.shape[0]
    rng = np.random.default_rng(seed)
    boot_idx = [_block_bootstrap_index(n, block, rng) for _ in range(B)]
    surviving = list(range(len(names)))
    while len(surviving) > 1:
        Ls = L[:, surviving]
        dev = Ls - Ls.mean(axis=1, keepdims=True)       # perda de cada modelo menos a média do conjunto
        di = dev.mean(axis=0)
        boot_di = np.array([dev[ix].mean(axis=0) for ix in boot_idx])
        sd = np.sqrt(np.maximum(boot_di.var(axis=0, ddof=1), 1e-15))
        t = di / sd
        t_max = float(t.max())
        boot_t_max = ((boot_di - di) / sd).max(axis=1)   # recentrado sob H0
        p = float(np.mean(boot_t_max >= t_max))
        if p >= alpha:
            break                                        # não rejeita: todos os sobreviventes entram no MCS
        surviving.remove(surviving[int(np.argmax(t))])   # elimina o pior
    return {names[i] for i in surviving}


def hansen_spa(benchmark, models: dict, *, B: int = 500, block: int = 10, seed: int = 0) -> float:
    """Hansen SPA (Reality-Check studentizado): p-valor de H0 = 'nenhum modelo bate o benchmark'.
    ``d = perda_benchmark − perda_modelo`` (positivo = modelo melhor). p pequeno → há edge."""
    b = np.asarray(benchmark, dtype=float)
    d = np.column_stack([b - np.asarray(models[k], dtype=float) for k in models])
    n = d.shape[0]
    dbar = d.mean(axis=0)
    rng = np.random.default_rng(seed)
    boot = np.array([d[_block_bootstrap_index(n, block, rng)].mean(axis=0) for _ in range(B)])
    sd = np.maximum(boot.std(axis=0, ddof=1), 1e-15)
    t_spa = float(np.max(np.maximum(dbar / sd, 0.0)))
    boot_t = np.max(np.maximum((boot - dbar) / sd, 0.0), axis=1)  # recentrado
    return float(np.mean(boot_t >= t_spa))
