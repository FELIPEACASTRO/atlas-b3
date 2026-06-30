"""Montagem da predição: adapter → forecast → densidade física → conformal → auditoria.

Função PURA (testável sem FastAPI). O endpoint só busca dados do store e chama aqui.
Tudo sobre o dado real; nada fabricado — quando falta histórico, devolve flags honestas.
"""
from __future__ import annotations

import datetime
import math

import numpy as np

from atlas_api.pricing.features import skew_25d
from atlas_api.pricing.har import fit_har, forecast_har
from atlas_api.pricing.signal import iv_rank

from .calibrate import IsotonicRecalibrator, online_recalibrator
from .distribution import Density, physical_density
from .forecast import har_leverage, vol_ensemble
from .regime import regime, strategy_bias
from .series import neg_return_series, rv_series
from .ssvi import fit_market_smile
from .strategies import build_catalog
from .validate import pit_uniformity

_RECAL_WINDOW = 60     # janela da recalibração isotônica online (medido: rolante conserta, estático piora)

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


def _market_smile(chain: list[dict], spot: float, asof: str | None, target_days: int) -> dict | None:
    """Densidade de MERCADO via SVI no vencimento líquido mais próximo de ``target_days``.

    Só devolve quando o fit é confiável (``usable``: arb-free + RMSE baixo) — senão None
    (BBAS3, p.ex., é recusado honestamente). Substitui o proxy IV-ATM no painel mercado-vs-físico.
    """
    if not chain or not asof or spot is None or spot <= 0:
        return None
    try:
        a = datetime.date.fromisoformat(asof)
    except (ValueError, TypeError):
        return None
    by_venc: dict[str, list[dict]] = {}
    for o in chain:
        if o.get("venc") and o.get("iv") is not None and o.get("strike") is not None:
            by_venc.setdefault(o["venc"], []).append(o)
    dated: list[tuple[int, list[dict]]] = []
    for venc, opts in by_venc.items():
        try:
            dte = (datetime.date.fromisoformat(venc) - a).days
        except ValueError:
            continue
        if dte > 0:
            dated.append((dte, opts))
    # prefere vencimentos RICOS (mensais da 3ª sexta, smile bem-determinada); só cai p/ finos se preciso
    rich = [(dte, opts) for dte, opts in dated if len(opts) >= 20]
    pool = rich if rich else [(dte, opts) for dte, opts in dated if len(opts) >= 6]
    if not pool:
        return None
    dte, opts = min(pool, key=lambda do: abs(do[0] - target_days))
    out = fit_market_smile([o["strike"] for o in opts], [o["iv"] for o in opts],
                           spot=spot, T=dte / 365.0)
    if out is None or not out["usable"]:
        return None
    k, p = out["k"], out["density"]
    std_rn = float(np.sqrt(max(np.trapezoid(k * k * p, k), 0.0)) / np.sqrt(dte / 365.0))
    return {
        "atm_vol": round(out["atm_vol"], 4), "std_rn": round(std_rn, 4),
        "dte": dte, "rmse": out["rmse"], "n_strikes": out["n_strikes"], "source": "SVI",
    }


def _recal_pop(dens: Density, target: float, side: str, recal: IsotonicRecalibrator | None) -> float:
    """POP recalibrada: ``R(CDF)`` corrige a forma quando há recalibrador; senão CDF crua."""
    cdf = float(dens.logret_cdf(math.log(target / dens.spot)))
    if recal is not None:
        cdf = float(recal.apply(cdf))
    return round((1.0 - cdf) if side == "above" else cdf, 3)


def _recal_quantile(dens: Density, q: float, recal: IsotonicRecalibrator | None) -> float:
    """Quantil de preço recalibrado: ``ppf(R⁻¹(q))`` quando há recalibrador; senão ``ppf(q)``."""
    level = float(recal.inverse(q)) if recal is not None else q
    return float(dens.spot * math.exp(float(dens.logret_ppf(level))))


def _calibration(rv: list[float], closes: list[float], *, min_train: int = 26, alpha: float = 0.2):
    """Backtest HONESTO da densidade servida + recalibração isotônica ONLINE.

    Para cada dia out-of-sample (point-in-time): prevê a vol (HAR), monta a densidade física
    de 1 dia, registra o PIT da CDF e se o retorno cai no intervalo nominal. Depois recalibra
    a forma com janela rolante (medido no dado real: rolante conserta, estático piora). Retorna
    ``(métricas, recalibrador_para_servir | None)``. Série curta → recusa, nunca fabrica.
    """
    nominal = round(1.0 - alpha, 3)
    n = len(rv)
    if n < min_train + 20:
        return {"available": False, "reason": "série curta para backtest robusto", "nominal": nominal}, None
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
        return {"available": False, "reason": "poucos pontos out-of-sample", "nominal": nominal}, None
    pit_arr = np.asarray(pit_vals, dtype=float)
    raw_p = float(pit_uniformity(pit_arr))
    # recalibração isotônica ONLINE (janela rolante): R(t) ajustada só no PIT recente, point-in-time
    recal_pit = [
        float(IsotonicRecalibrator().fit(pit_arr[t - _RECAL_WINDOW:t]).apply(pit_arr[t]))
        for t in range(_RECAL_WINDOW, len(pit_arr))
    ]
    r_serve = online_recalibrator(pit_arr, window=_RECAL_WINDOW)
    if len(recal_pit) >= 20 and r_serve is not None:
        rec = np.asarray(recal_pit, dtype=float)
        p = float(pit_uniformity(rec))
        return {
            "available": True, "recalibrated": True, "nominal": nominal,
            "coverage": round(float(np.mean((rec >= q_lo) & (rec <= q_hi))), 3),
            "pit_p": round(p, 3), "pit_ok": bool(p > 0.05),
            "pit_p_raw": round(raw_p, 3), "n_test": len(rec),
        }, r_serve
    return {
        "available": True, "recalibrated": False, "nominal": nominal,
        "coverage": round(float(np.mean(covered)), 3),
        "pit_p": round(raw_p, 3), "pit_ok": bool(raw_p > 0.05), "n_test": len(pit_vals),
    }, None


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

    # vol de MERCADO: ATM da smile SVI (robusta, fitada a dezenas de strikes) quando confiável;
    # senão o ponto IV ATM. Usada de forma consistente em mercado/física/gap.
    current_iv = iv_history[-1] if iv_history else None
    smile = _market_smile(chain, spot, asof, T_days)
    market_vol = smile["atm_vol"] if smile else current_iv
    sigma_iv = market_vol if market_vol is not None else sigma
    # densidade física: σ_fís = λ·forecast + (1−λ)·mercado (via VRP); coerência F6 por construção
    vrp = sigma_iv - sigma                              # VRP cru (mercado − previsão) — p/ regime e densidade
    dens = physical_density(spot=spot, sigma_iv=sigma_iv, rv=sigma, vrp=vrp, T=T_days / 365.0, lam=lam)
    gap = round(sigma_iv - dens.sigma, 4)              # gap exibido: mercado − densidade física servida
    # calibração + recalibrador isotônico online p/ servir (validado no dado real)
    cal, r_serve = _calibration(rv, closes)
    pop_targets = [
        {"moneyness": mny, "price": round(spot * mny, 2),
         "above": _recal_pop(dens, spot * mny, "above", r_serve),
         "below": _recal_pop(dens, spot * mny, "below", r_serve)}
        for mny in (0.95, 1.0, 1.05)
    ]
    qs = [_recal_quantile(dens, q, r_serve) for q in (0.10, 0.25, 0.50, 0.75, 0.90)]
    dist = {
        "sigma_phys": round(dens.sigma, 4), "nu": dens.nu, "horizon_days": T_days,
        "recalibrated": r_serve is not None,
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
            "iv": round(sigma_iv, 4) if sigma_iv is not None else None,   # vol de mercado (SVI quando confiável)
            "physical": round(dens.sigma, 4),
            "vrp": gap,                     # mercado − densidade física (consistente com os dois cards)
            "iv_point": round(current_iv, 4) if current_iv is not None else None,  # ponto IV ATM (transparência)
            "market_smile": smile,          # ATM/densidade RN da SVI (None se a smile não é confiável)
        },
        "dist": dist,
        "regime": {**reg, "iv_rank": round(ivr, 1) if ivr is not None else None,
                   "term_slope": round(term_slope, 4) if term_slope is not None else None,
                   "skew": round(skew, 4) if skew is not None else None},
        "calibration": cal,
        "note": "predição calibrada (cenário-alvo + probabilidade), não profecia nem ordem",
    }


def _expiry_options(chain: list[dict], asof: str | None, target_days: int) -> list[dict]:
    """Opções (com preço) do vencimento líquido mais próximo de ``target_days``."""
    if not chain or not asof:
        return []
    try:
        a = datetime.date.fromisoformat(asof)
    except (ValueError, TypeError):
        return []
    by_venc: dict[str, list[dict]] = {}
    for o in chain:
        if o.get("venc") and o.get("strike") and o.get("last") and o["last"] > 0:
            by_venc.setdefault(o["venc"], []).append(o)
    dated: list[tuple[int, list[dict]]] = []
    for venc, opts in by_venc.items():
        try:
            dte = (datetime.date.fromisoformat(venc) - a).days
        except ValueError:
            continue
        if dte > 0:
            dated.append((dte, opts))
    rich = [(dte, opts) for dte, opts in dated if len(opts) >= 10]
    pool = rich if rich else dated
    if not pool:
        return []
    return min(pool, key=lambda do: abs(do[0] - target_days))[1]


def build_strategies(
    *, ticker: str, ohlc: list[tuple], closes: list[float], iv_history: list[float],
    spot: float, chain: list[dict], asof: str | None, capital: float = 20000.0,
    prazo: int = 30, visao: str = "alta",
) -> dict:
    """Consultor de estratégias: catálogo avaliado por POP/EV sobre a densidade do motor.

    ``capital`` é o orçamento de risco; ``visao`` ∈ {alta, baixa, neutro, renda}. Honesto:
    sem dado/cadeia → catálogo vazio com nota. Análise, nunca ordem.
    """
    pred = build_prediction(ticker=ticker, ohlc=ohlc, closes=closes, iv_history=iv_history,
                            spot=spot, chain=chain, asof=asof, T_days=prazo)
    base = {"ticker": ticker, "spot": round(spot, 2) if spot else None, "visao": visao,
            "capital": capital, "prazo": prazo, "provenance": pred["provenance"], "asof": asof}
    if pred["sigma"] is None or spot is None or spot <= 0:
        return {**base, "strategies": [], "regime": pred["regime"],
                "note": pred.get("note", "histórico insuficiente para avaliar estratégias")}
    physical = pred["market_vs_physical"]["physical"]
    dens = physical_density(spot=spot, sigma_iv=physical, rv=physical, vrp=0.0, T=prazo / 365.0)
    opts = _expiry_options(chain, asof, prazo)
    cat = build_catalog(spot, dens, opts, visao=visao, capital=capital) if opts else []
    return {
        **base,
        "regime": pred["regime"],
        "market_vs_physical": pred["market_vs_physical"],
        "strategies": cat[:8],
        "note": "análise probabilística (POP + valor esperado sobre a densidade), não recomendação de compra/venda",
        "liquidez_caveat": "sizing por risco; a liquidez real da opção (volume/contratos em aberto) NÃO está na base EOD — confira antes de executar",
    }
