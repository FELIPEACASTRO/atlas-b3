"""Montagem da predição: adapter → forecast → densidade física → conformal → auditoria.

Função PURA (testável sem FastAPI). O endpoint só busca dados do store e chama aqui.
Tudo sobre o dado real; nada fabricado — quando falta histórico, devolve flags honestas.
"""
from __future__ import annotations

import numpy as np
from scipy import stats

from atlas_api.pricing.features import skew_25d
from atlas_api.pricing.har import fit_har, forecast_har
from atlas_api.pricing.signal import iv_rank

from .conformal import split_conformal
from .distribution import physical_density, pop, quantiles
from .forecast import har_leverage, vol_ensemble
from .regime import regime, strategy_bias
from .series import neg_return_series, rv_series
from .validate import coverage, pit_uniformity

YZ_WINDOW = 5          # janela do Yang-Zhang rolante (RV diária para o HAR)
_MONTHLY = 21
_MIN_BARS = YZ_WINDOW + _MONTHLY + 6   # mínimo p/ um HAR honesto sobre a série de RV


def _term_and_skew(chain: list[dict], spot: float):
    """term_slope = IV(venc longo) − IV(venc curto); skew = 25Δ put − ATM (reusa features)."""
    by_venc: dict[str, list[dict]] = {}
    for o in chain:
        if o.get("iv") is not None and o.get("venc") and o.get("strike") is not None:
            by_venc.setdefault(o["venc"], []).append(o)
    atm_by_venc = {}
    for venc, opts in by_venc.items():
        atm = min(opts, key=lambda o: abs(o["strike"] - spot))
        atm_by_venc[venc] = atm["iv"]
    term_slope = None
    if len(atm_by_venc) >= 2:
        vencs = sorted(atm_by_venc)
        term_slope = atm_by_venc[vencs[-1]] - atm_by_venc[vencs[0]]
    # skew: puts do venc mais curto com ATM IV de referência
    skew = None
    if atm_by_venc:
        ref_venc = sorted(atm_by_venc)[0]
        atm_iv = atm_by_venc[ref_venc]
        put_deltas = [
            (o["delta"], o["iv"]) for o in by_venc.get(ref_venc, [])
            if o.get("kind") == "put" and o.get("delta") is not None and o.get("iv") is not None
        ]
        skew = skew_25d(put_deltas, atm_iv)
    return term_slope, skew


def _calibration(rv: list[float], *, min_train: int = 30, alpha: float = 0.2) -> dict:
    """Backtest HONESTO: walk-forward HAR + envelope conformal; cobertura e PIT no out-of-sample.

    Série curta → recusa (``available: False``), nunca fabrica. A cobertura conformal é
    garantida por construção (sanidade); o PIT audita a forma da distribuição.
    """
    nominal = round(1.0 - alpha, 3)
    if len(rv) < min_train + 20:
        return {"available": False, "reason": "série curta para backtest robusto", "nominal": nominal}
    realized, fc = [], []
    for t in range(min_train, len(rv)):
        coef = fit_har(rv[:t])
        realized.append(rv[t])
        fc.append(forecast_har(coef, rv[:t]))
    realized = np.asarray(realized, dtype=float)
    fc = np.asarray(fc, dtype=float)
    n = len(realized)
    k = n // 2
    resid = realized[:k] - fc[:k]
    s = float(np.std(resid)) or 1e-6
    lo, hi = split_conformal(
        realized[:k], fc[:k], np.full(k, s), fc[k:], np.full(n - k, s), alpha=alpha
    )
    cov = coverage(realized[k:], lo, hi)
    pit_vals = stats.norm.cdf((realized[k:] - fc[k:]) / s)
    p = pit_uniformity(pit_vals)
    return {
        "available": True,
        "coverage": round(cov, 3),
        "nominal": nominal,
        "pit_p": round(float(p), 3),
        "pit_ok": bool(p > 0.05),
        "n_test": int(n - k),
    }


def build_prediction(
    *, ticker: str, ohlc: list[tuple], closes: list[float], iv_history: list[float],
    spot: float, chain: list[dict], asof: str | None, T_days: int = 30, lam: float = 0.5,
) -> dict:
    """Predição calibrada de vol/distribuição para um ativo. Sempre honesta sobre limites."""
    prov = f"COTAHIST EOD {asof}" if asof else "COTAHIST EOD"
    base_out = {"ticker": ticker, "provenance": prov, "asof": asof}
    if spot is None or spot <= 0 or len(ohlc) < _MIN_BARS:
        return {**base_out, "sigma": None, "dist": None, "regime": strategy_bias("indisponivel"),
                "calibration": {"available": False, "reason": "histórico insuficiente", "nominal": 0.8},
                "note": f"need >= {_MIN_BARS} barras de preço para prever; tem {len(ohlc)}"}

    # forecast de vol: HAR-Leverage + ensemble (Yang-Zhang como RV diária)
    rv = rv_series(ohlc, window=YZ_WINDOW)
    neg = neg_return_series(closes)[YZ_WINDOW - 2:]            # alinha ao rv (ver series.py)
    m = min(len(rv), len(neg))
    rv, neg = rv[-m:], neg[-m:]
    base, lev = har_leverage(rv, neg)
    sigma = vol_ensemble([base, lev])                          # média simples (combination puzzle)

    # densidade física: σ_fís = λ·forecast + (1−λ)·IV  (via VRP); coerência F6 por construção
    current_iv = iv_history[-1] if iv_history else None
    sigma_iv = current_iv if current_iv is not None else sigma
    vrp = sigma_iv - sigma
    dens = physical_density(spot=spot, sigma_iv=sigma_iv, rv=sigma, vrp=vrp, T=T_days / 365.0, lam=lam)
    pop_targets = [
        {"moneyness": mny, "price": round(spot * mny, 2),
         "above": round(pop(dens, spot * mny, "above"), 3),
         "below": round(pop(dens, spot * mny, "below"), 3)}
        for mny in (0.95, 1.0, 1.05)
    ]
    qs = quantiles(dens, [0.10, 0.25, 0.50, 0.75, 0.90])
    dist = {
        "sigma_phys": round(dens.sigma, 4), "nu": dens.nu, "horizon_days": T_days,
        "pop_targets": pop_targets,
        "quantiles": {"p10": round(qs[0], 2), "p25": round(qs[1], 2), "p50": round(qs[2], 2),
                      "p75": round(qs[3], 2), "p90": round(qs[4], 2)},
    }

    # regime (reusa iv_rank/skew; term_slope da cadeia) — None honesto quando falta dado
    ivr = iv_rank(iv_history, current_iv) if (iv_history and current_iv is not None) else None
    term_slope, skew = _term_and_skew(chain, spot)
    reg = strategy_bias(regime(ivr, vrp, term_slope, skew))

    return {
        **base_out,
        "sigma": round(sigma, 4),
        "market_vs_physical": {
            "iv": round(sigma_iv, 4) if sigma_iv is not None else None,
            "physical": round(dens.sigma, 4),
            "vrp": round(vrp, 4),
        },
        "dist": dist,
        "regime": {**reg, "iv_rank": round(ivr, 1) if ivr is not None else None,
                   "term_slope": round(term_slope, 4) if term_slope is not None else None,
                   "skew": round(skew, 4) if skew is not None else None},
        "calibration": _calibration(rv),
        "note": "predição calibrada (cenário-alvo + probabilidade), não profecia nem ordem",
    }
