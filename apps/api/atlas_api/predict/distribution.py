"""Densidade FÍSICA da vol — o coração de "distribuição, não direção" (spec §83).

A distribuição dos log-retornos no horizonte T é uma Student-t (caudas gordas,
Mandelbrot/Fama) centrada em 0 (drift=0 **declarado** — não prevemos direção),
com escala calibrada para que o desvio-padrão seja σ_fís·√T, onde

    σ_fís = rv + (1 − λ) · vrp        (ajuste físico via VRP; λ=0.5 default)

encolhe a vol implícita rumo à realizada (o VRP é prêmio, não previsão). Isto é a
densidade do MUNDO REAL (física), distinta da risco-neutra (SSVI, ML-2). POP e
quantis saem da CDF. Não é recomendação — é cenário-alvo com probabilidade.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from scipy import stats


@dataclass(frozen=True)
class Density:
    """Densidade física dos log-retornos no horizonte. ``sigma`` é σ_fís ANUALIZADA."""

    spot: float
    sigma: float        # σ_fís anualizada = previsão de E[RV] (usada no VRP/painel; NÃO inclui κ)
    nu: float           # graus de liberdade da Student-t (caudas)
    T: float            # horizonte em anos
    _scale: float       # escala da t sobre log-retornos no horizonte (std = σ_fís·κ·√T)

    def logret_cdf(self, x):
        return stats.t.cdf(x, df=self.nu, loc=0.0, scale=self._scale)

    def logret_pdf(self, x):
        return stats.t.pdf(x, df=self.nu, loc=0.0, scale=self._scale)

    def logret_ppf(self, q):
        return stats.t.ppf(q, df=self.nu, loc=0.0, scale=self._scale)


def physical_density(
    *, spot: float, sigma_iv: float, rv: float, vrp: float, T: float, lam: float = 0.5,
    nu: float = 5.0, kappa: float = 1.10, tol: float = 1e-6,
) -> Density:
    """Densidade física dos log-retornos no horizonte ``T``.

    ``sigma_iv`` é **redundante** (por construção ``vrp ≈ sigma_iv − rv``, features.py:18) e
    serve só ao painel "mercado vs físico"; validamos a coerência para não admitir
    estados incoerentes (review F6). ``nu>2`` p/ variância finita. ``kappa`` infla a LARGURA da
    densidade para corrigir a subcobertura sistemática (YZ enviesa p/ baixo, HAR encolhe p/ a
    média); medido em walk-forward (10 nomes líquidos): mediana de cobertura 0.774→0.805 (nominal
    0.80) de κ=1.0→1.10. Não altera ``sigma`` (previsão de E[RV]), só a incerteza da densidade.
    """
    if abs((rv + vrp) - sigma_iv) > tol:
        raise ValueError(
            f"incoerente: rv+vrp={rv + vrp:.6f} != sigma_iv={sigma_iv:.6f} (vrp deve ser sigma_iv-rv)"
        )
    if nu <= 2:
        raise ValueError("nu must be > 2 for finite variance")
    if T <= 0:
        raise ValueError("T must be > 0")
    sigma_fis = rv + (1.0 - lam) * vrp                      # previsão de E[RV]: encolhe a IV rumo à RV via VRP
    horizon_std = sigma_fis * kappa * math.sqrt(T)          # κ infla a LARGURA (cobertura), não a previsão pontual
    scale = horizon_std * math.sqrt((nu - 2.0) / nu)         # t.q. std da t = σ_fís·κ·√T
    return Density(spot=spot, sigma=sigma_fis, nu=nu, T=T, _scale=scale)


def pop(dist: Density, target: float, side: str = "above") -> float:
    """Probabilidade do preço terminar acima/abaixo de ``target`` (cenário-alvo, não profecia)."""
    if side not in ("above", "below"):
        raise ValueError("side must be 'above' or 'below'")
    x = math.log(target / dist.spot)                         # log-retorno alvo
    cdf = float(dist.logret_cdf(x))
    return 1.0 - cdf if side == "above" else cdf


def quantiles(dist: Density, qs: list[float]) -> list[float]:
    """Quantis de PREÇO terminal para as probabilidades ``qs`` (via os quantis de log-retorno)."""
    return [float(dist.spot * math.exp(float(dist.logret_ppf(q)))) for q in qs]
