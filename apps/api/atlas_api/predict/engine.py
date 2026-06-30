"""Montagem da predição: adapter → forecast → densidade física → conformal → auditoria.

Função PURA (testável sem FastAPI). O endpoint só busca dados do store e chama aqui.
Tudo sobre o dado real; nada fabricado — quando falta histórico, devolve flags honestas.
"""
from __future__ import annotations

import numpy as np

from atlas_api.pricing.features import skew_25d
from atlas_api.pricing.har import fit_har, forecast_har
from atlas_api.pricing.signal import iv_rank

import math

from .distribution import physical_density, pop, quantiles
from .forecast import har_leverage, vol_ensemble
from .regime import regime, strategy_bias
from .series import neg_return_series, rv_series
from .validate import pit_uniformity

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


def _calibration(rv: list[float], closes: list[float], *, min_train: int = 26, alpha: float = 0.2) -> dict:
    """Backtest HONESTO da DENSIDADE SERVIDA contra os retornos diários realizados.

    Para cada dia out-of-sample, prevê a vol (HAR, point-in-time), monta a densidade física
    de 1 dia e checa se o retorno realizado cai no intervalo nominal — e o PIT da CDF. É o que
    o endpoint de fato entrega (Student-t), não um intervalo separado. Série curta → recusa.
    """
    nominal = round(1.0 - alpha, 3)
    n = len(rv)
    if n < min_train + 20:
        return {"available": False, "reason": "série curta para backtest robusto", "nominal": nominal}
    q_lo, q_hi = alpha / 2.0, 1.0 - alpha / 2.0
    pit_vals: list[float] = []
    covered: list[bool] = []
    for i in range(min_train, n):
        day = i + YZ_WINDOW - 1                 # índice em closes alinhado a rv[i] (fim da janela YZ)
        if day + 1 >= len(closes):
            break
        vol_fc = forecast_har(fit_har(rv[:i]), rv[:i])      # vol 1-passo, point-in-time (sem look-ahead)
        if not (vol_fc > 0) or closes[day] <= 0:
            continue
        dens = physical_density(spot=closes[day], sigma_iv=vol_fc, rv=vol_fc, vrp=0.0, T=1.0 / 252.0)
        realized = math.log(closes[day + 1] / closes[day])
        pit_vals.append(float(dens.logret_cdf(realized)))
        covered.append(bool(dens.logret_ppf(q_lo) <= realized <= dens.logret_ppf(q_hi)))
    if len(pit_vals) < 20:
        return {"available": False, "reason": "poucos pontos out-of-sample", "nominal": nominal}
    p = pit_uniformity(np.asarray(pit_vals, dtype=float))
    return {
        "available": True,
        "coverage": round(float(np.mean(covered)), 3),
        "nominal": nominal,
        "pit_p": round(float(p), 3),
        "pit_ok": bool(p > 0.05),
        "n_test": len(pit_vals),
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
        "calibration": _calibration(rv, closes),
        "note": "predição calibrada (cenário-alvo + probabilidade), não profecia nem ordem",
    }
