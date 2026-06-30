"""Conformal prediction — cobertura marginal GARANTIDA, distribution-free.

A maior alavanca de honestidade do motor (spec §86): mesmo se a densidade-base
(Student-t) estiver mal especificada, o envelope conformal cobre ≥ 1−α dos casos,
em amostra finita, sem hipótese de distribuição. Padroniza o resíduo por σ (lida
com heterocedasticidade) e calibra a largura pelo quantil empírico com correção
finita. aci_update adapta α ao regime (Gibbs & Candès 2021), com clamp em [0,1].
"""
from __future__ import annotations

import math

import numpy as np


def split_conformal(y_cal, mu_cal, sigma_cal, mu_test, sigma_test, *, alpha: float):
    """Intervalo split-conformal padronizado. Cobertura marginal ≥ 1−α garantida.

    Resíduo de não-conformidade = ``|y − μ| / σ`` na calibração; o quantil empírico
    com correção finita (``ceil((n+1)(1−α))``) vira a meia-largura, escalada por
    ``σ_test``. Retorna ``(lo, hi)`` (arrays alinhados a ``mu_test``).
    """
    y_cal = np.asarray(y_cal, dtype=float)
    mu_cal = np.asarray(mu_cal, dtype=float)
    sigma_cal = np.asarray(sigma_cal, dtype=float)
    mu_test = np.asarray(mu_test, dtype=float)
    sigma_test = np.asarray(sigma_test, dtype=float)
    n = y_cal.size
    if n < 1:
        raise ValueError("need >= 1 calibration point")
    if np.any(sigma_cal <= 0) or np.any(sigma_test <= 0):
        raise ValueError("sigma must be > 0")
    scores = np.abs(y_cal - mu_cal) / sigma_cal              # resíduos padronizados
    k = math.ceil((n + 1) * (1.0 - alpha))                   # correção de amostra finita
    q = np.inf if k > n else float(np.sort(scores)[k - 1])   # n pequeno => intervalo = tudo
    lo = mu_test - q * sigma_test
    hi = mu_test + q * sigma_test
    return lo, hi


def aci_update(alpha: float, *, covered: bool, gamma: float, target: float = 0.1) -> float:
    """Adaptive Conformal Inference: ``α ← clip(α + γ·(target − miss), 0, 1)``.

    ``target`` é a miscobertura nominal (default 0.1 = 90%). Não-cobrir (``miss=1``)
    baixa α → alarga o próximo intervalo; cobrir (``miss=0``) sobe α → aperta. O clamp
    em [0,1] é OBRIGATÓRIO — sem ele a recursão diverge (review NIT-1).
    """
    miss = 0.0 if covered else 1.0
    return float(min(1.0, max(0.0, alpha + gamma * (target - miss))))
