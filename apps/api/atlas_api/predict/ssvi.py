"""Smile SVI (Gatheral) + densidade risco-neutra — a densidade de MERCADO (spec §86, ML-2).

Hoje o painel usa a IV ATM como proxy do "mercado". Aqui ajustamos a smile inteira
(SVI raw, Gatheral-Jacquier arXiv:1204.0646) e extraímos a densidade risco-neutra do
retorno via a fórmula de Gatheral (equivalente a Breeden-Litzenberger ∂²C/∂K²), com a
checagem de no-arbitragem de butterfly g(k) ≥ 0. Gate de liquidez: só nomes com strikes
suficientes e bem distribuídos (PETR4/VALE3/bancos/BOVA11), recusa honesta nos demais.

SVI raw:  w(k) = a + b·(ρ·(k−m) + √((k−m)² + s²)),  com w = σ²·T (variância total), k = ln(K/F).
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares

SviParams = tuple[float, float, float, float, float]   # a, b, rho, m, s


def svi_total_variance(params: SviParams, k):
    a, b, rho, m, s = params
    k = np.asarray(k, dtype=float)
    z = k - m
    return a + b * (rho * z + np.sqrt(z * z + s * s))


def _derivs(params: SviParams, k):
    """(w, w', w'') do SVI em k."""
    a, b, rho, m, s = params
    k = np.asarray(k, dtype=float)
    z = k - m
    root = np.sqrt(z * z + s * s)
    w = a + b * (rho * z + root)
    wp = b * (rho + z / root)
    wpp = b * s * s / root ** 3
    return w, wp, wpp


def svi_g(params: SviParams, k):
    """Função g de Gatheral: g(k) ≥ 0 ⇔ sem arbitragem de butterfly (densidade ≥ 0)."""
    w, wp, wpp = _derivs(params, k)
    k = np.asarray(k, dtype=float)
    return (1.0 - k * wp / (2.0 * w)) ** 2 - (wp * wp / 4.0) * (1.0 / w + 0.25) + wpp / 2.0


def svi_density(params: SviParams, k):
    """Densidade risco-neutra do log-retorno em k (Gatheral). ≥ 0 sse arb-free."""
    w, wp, wpp = _derivs(params, k)
    k = np.asarray(k, dtype=float)
    g = (1.0 - k * wp / (2.0 * w)) ** 2 - (wp * wp / 4.0) * (1.0 / w + 0.25) + wpp / 2.0
    d2 = -k / np.sqrt(w) - np.sqrt(w) / 2.0
    return g / np.sqrt(2.0 * np.pi * w) * np.exp(-d2 * d2 / 2.0)


def fit_svi(k, w, weights=None) -> SviParams:
    """Ajusta SVI raw à variância total ``w`` por mínimos quadrados com limites (no-arb soft)."""
    k = np.asarray(k, dtype=float)
    w = np.asarray(w, dtype=float)
    wt = np.ones_like(w) if weights is None else np.asarray(weights, dtype=float)
    a0 = max(float(np.min(w)), 1e-6)
    x0 = [a0, 0.1, -0.3, 0.0, 0.1]
    lo = [1e-8, 0.0, -0.999, float(np.min(k)) - 0.5, 1e-3]
    hi = [max(float(np.max(w)) * 2.0, 1.0), 5.0, 0.999, float(np.max(k)) + 0.5, 5.0]
    res = least_squares(
        lambda p: wt * (svi_total_variance(p, k) - w), x0, bounds=(lo, hi), max_nfev=4000
    )
    return tuple(float(v) for v in res.x)  # type: ignore[return-value]


def risk_neutral_density(params: SviParams, k) -> dict:
    """Densidade de mercado em ``k`` + flag de no-arbitragem (butterfly)."""
    k = np.asarray(k, dtype=float)
    g = svi_g(params, k)
    p = svi_density(params, k)
    return {
        "density": p,
        "k": k,
        "arbitrage_free": bool(np.all(g >= -1e-8)),
        "params": params,
    }


def fit_market_smile(
    strikes, ivs, *, spot: float, T: float, r: float = 0.0, q: float = 0.0,
    min_strikes: int = 6, mny_lo: float = 0.85, mny_hi: float = 1.15,
    atm_sigma: float = 0.08, max_rmse: float = 0.04,
) -> dict | None:
    """Ajusta a smile de MERCADO e devolve ATM vol + densidade RN, com gate de qualidade.

    Gate de LIQUIDEZ: filtra strikes fora do núcleo ``[mny_lo, mny_hi]·F`` e IV não-positiva;
    exige ``>= min_strikes`` — senão recusa (``None``). O fit pondera o ATM (gaussiano, σ=
    ``atm_sigma``), onde a IV da B3 é mais confiável (medido: wings stale geram arbitragem).
    Gate de QUALIDADE: ``usable`` só é True se a smile é arb-free **e** o RMSE ponderado ≤
    ``max_rmse`` — senão a densidade de mercado não é confiável e o caller deve omiti-la.
    """
    strikes = np.asarray(strikes, dtype=float)
    ivs = np.asarray(ivs, dtype=float)
    if spot is None or spot <= 0 or T <= 0 or strikes.size != ivs.size:
        return None
    fwd = spot * np.exp((r - q) * T)
    mny = strikes / fwd
    ok = (ivs > 0) & np.isfinite(ivs) & (mny >= mny_lo) & (mny <= mny_hi) & (strikes > 0)
    if int(ok.sum()) < min_strikes:
        return None
    k = np.log(strikes[ok] / fwd)
    w = (ivs[ok] ** 2) * T
    weights = np.exp(-(((mny[ok] - 1.0) / atm_sigma) ** 2))     # peso concentrado no ATM
    order = np.argsort(k)
    k, w, weights, iv_used = k[order], w[order], weights[order], ivs[ok][order]
    params = fit_svi(k, w, weights)
    iv_fit = np.sqrt(np.maximum(svi_total_variance(params, k), 0.0) / T)
    rmse = float(np.sqrt(np.average((iv_fit - iv_used) ** 2, weights=weights)))
    atm_var = float(svi_total_variance(params, np.array([0.0]))[0])
    # No-arbitragem checada na região COM DADOS (±0.1 além dos strikes) — não na extrapolação das
    # asas, que penalizaria smiles boas por um artefato do SVI longe de onde há mercado.
    core = np.linspace(float(k.min()) - 0.1, float(k.max()) + 0.1, 2000)
    arb_free = risk_neutral_density(params, core)["arbitrage_free"]
    # Densidade servida num grid ESTENDIDO (±3σ além do núcleo) → captura >99.9% da massa, para a
    # CDF do Edge Map não enviesar as asas ao renormalizar (bug medido: −0.026 nas puts baixas).
    pad = max(0.1, 3.0 * float(np.sqrt(max(atm_var, 1e-8))))
    grid = np.linspace(float(k.min()) - pad, float(k.max()) + pad, 3000)
    rnd = risk_neutral_density(params, grid)
    return {
        "params": params,
        "atm_vol": float(np.sqrt(max(atm_var, 0.0) / T)),
        "arbitrage_free": arb_free,
        "rmse": round(rmse, 4),
        "usable": bool(arb_free and rmse <= max_rmse),
        "n_strikes": int(ok.sum()),
        "forward": float(fwd),
        "density": rnd["density"],
        "k": grid,
    }
