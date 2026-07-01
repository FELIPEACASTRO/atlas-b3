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
from .decision import (
    _asset_signals,
    _confidence,
    _invalidation,
    _kelly_lots,
    _verdict,
    _why,
    reactivate_hint,
)
from .edge import premium_map
from .edge_backtest import run_edge_backtest, vol_premium_pnl
from .fair_iv import fair_iv_smile
from .kernel import kernel_shape, pricing_kernel
from .forecast import har_leverage, vol_ensemble
from .regime import regime, strategy_bias
from .series import neg_return_series, rv_series
from .ssvi import fit_market_smile
from .strategies import build_catalog, rationale
from .validate import pit_uniformity

_RECAL_WINDOW = 60     # janela da recalibração isotônica online (medido: rolante conserta, estático piora)
# A recalibração é ajustada no PIT de 1 dia (é o horizonte com amostra robusta). Aplicá-la a
# densidades de horizonte longo é INVÁLIDO (medido em backtest walk-forward por 2 agentes: a
# forma da t de 1 dia não transfere para 30 dias — desloca até a mediana, e o PIT do 30d cai de
# ~90% cru para ~16% ao aplicar a R de 1 dia). Só recalibra horizontes curtos; nos longos serve
# a t crua (a √T + inflação de escala já cobrem). Honestidade > fingir calibração transferida.
_RECAL_MAX_H_DAYS = 5

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


def _walk_forward_pit(rv: list[float], closes: list[float], *, min_train: int = 26, alpha: float = 0.2):
    """PIT out-of-sample dia-a-dia (point-in-time) + cobertura do intervalo (1−α).

    Para cada dia: prevê a vol 1-passo (HAR, sem look-ahead), monta a densidade física de 1 dia,
    registra o PIT da CDF e se o retorno caiu no intervalo nominal. Base compartilhada do gate de
    calibração e do monitor de descalibração (PIT-break). Retorna ``(pit_vals, covered)``.
    """
    q_lo, q_hi = alpha / 2.0, 1.0 - alpha / 2.0
    pit_vals: list[float] = []
    covered: list[bool] = []
    for i in range(min_train, len(rv)):
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
    return pit_vals, covered


def _calibration(rv: list[float], closes: list[float], *, min_train: int = 26, alpha: float = 0.2):
    """Backtest HONESTO da densidade servida + recalibração isotônica ONLINE.

    Roda o walk-forward do PIT (``_walk_forward_pit``) e recalibra a forma com janela rolante
    (medido no dado real: rolante conserta, estático piora). Retorna ``(métricas,
    recalibrador_para_servir | None)``. Série curta → recusa, nunca fabrica.
    """
    nominal = round(1.0 - alpha, 3)
    n = len(rv)
    if n < min_train + 20:
        return {"available": False, "reason": "série curta para backtest robusto", "nominal": nominal}, None
    q_lo, q_hi = alpha / 2.0, 1.0 - alpha / 2.0
    pit_vals, covered = _walk_forward_pit(rv, closes, min_train=min_train, alpha=alpha)
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
    recal = r_serve if T_days <= _RECAL_MAX_H_DAYS else None   # R de 1 dia não transfere p/ horizontes longos
    pop_targets = [
        {"moneyness": mny, "price": round(spot * mny, 2),
         "above": _recal_pop(dens, spot * mny, "above", recal),
         "below": _recal_pop(dens, spot * mny, "below", recal)}
        for mny in (0.95, 1.0, 1.05)
    ]
    qs = [_recal_quantile(dens, q, recal) for q in (0.10, 0.25, 0.50, 0.75, 0.90)]
    dist = {
        "sigma_phys": round(dens.sigma, 4), "nu": dens.nu, "horizon_days": T_days,
        "recalibrated": recal is not None,
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
    mvp = pred["market_vs_physical"]
    for s in cat:                                              # o 'porquê' humano por estratégia
        s["rationale"] = rationale(s, market_iv=mvp.get("iv"), physical=mvp.get("physical"))
    return {
        **base,
        "regime": pred["regime"],
        "market_vs_physical": pred["market_vs_physical"],
        "strategies": cat[:8],
        "note": "análise probabilística (POP + valor esperado sobre a densidade), não recomendação de compra/venda",
        "liquidez_caveat": "sizing por risco; a liquidez real da opção (volume/contratos em aberto) NÃO está na base EOD — confira antes de executar",
    }


def _fit_smile_near(chain: list[dict], spot: float, asof: str | None, target_days: int):
    """Ajusta a smile SVI no vencimento RICO mais próximo de ``target_days``; retorna (fit, dte) ou (None, None)."""
    if not chain or not asof or spot is None or spot <= 0:
        return None, None
    try:
        a = datetime.date.fromisoformat(asof)
    except (ValueError, TypeError):
        return None, None
    by_venc: dict[str, list[dict]] = {}
    for o in chain:
        if o.get("venc") and o.get("iv") is not None and o.get("strike") is not None:
            by_venc.setdefault(o["venc"], []).append(o)
    dated = []
    for venc, opts in by_venc.items():
        try:
            dte = (datetime.date.fromisoformat(venc) - a).days
        except ValueError:
            continue
        if dte > 0:
            dated.append((dte, opts))
    rich = [(dte, opts) for dte, opts in dated if len(opts) >= 20]
    pool = rich if rich else [(dte, opts) for dte, opts in dated if len(opts) >= 6]
    if not pool:
        return None, None
    dte, opts = min(pool, key=lambda do: abs(do[0] - target_days))
    fit = fit_market_smile([o["strike"] for o in opts], [o["iv"] for o in opts], spot=spot, T=dte / 365.0)
    return (fit if fit and fit["usable"] else None), dte


def build_edge_map(
    *, ticker: str, ohlc: list[tuple], closes: list[float], iv_history: list[float],
    spot: float, chain: list[dict], asof: str | None, T_days: int = 30,
) -> dict:
    """MAPA DE PRÊMIO (o diferencial): P_mercado(S≤K) (RN/SVI) vs P_física(S≤K) (calibrada), por strike.

    Só quando a smile é confiável (arb-free + RMSE baixo) — senão recusa honesto. Ambas no forward
    (isola vol/skew, remove o carry). ``edge>0`` = put rica; ``edge<0`` = call rica.
    """
    prov = f"COTAHIST EOD {asof}" if asof else "COTAHIST EOD"
    base = {"ticker": ticker, "spot": round(spot, 2) if spot else None, "provenance": prov, "asof": asof}
    pred = build_prediction(ticker=ticker, ohlc=ohlc, closes=closes, iv_history=iv_history,
                            spot=spot, chain=chain, asof=asof, T_days=T_days)
    if pred["sigma"] is None or spot is None or spot <= 0:
        return {**base, "edge": None, "note": "histórico insuficiente para o mapa de prêmio"}
    fit, dte = _fit_smile_near(chain, spot, asof, T_days)
    if fit is None:
        return {**base, "edge": None, "market_vs_physical": pred["market_vs_physical"],
                "note": "smile de mercado não confiável (sem arbitragem-livre) — mapa de prêmio omitido"}
    physical = pred["market_vs_physical"]["physical"]
    rv = rv_series(ohlc, window=YZ_WINDOW)
    _, r_serve = _calibration(rv, closes)
    recal = r_serve if dte <= _RECAL_MAX_H_DAYS else None   # não aplica R de 1 dia à densidade de ~30 dias
    dens = physical_density(spot=spot, sigma_iv=physical, rv=physical, vrp=0.0, T=dte / 365.0)

    def phys_cdf(x):
        c = float(dens.logret_cdf(x))
        return float(recal.apply(c)) if recal is not None else c

    grid = [round(x, 3) for x in np.linspace(0.85, 1.15, 13)]
    emap = premium_map(spot=spot, forward=fit["forward"], phys_cdf=phys_cdf,
                       svi_k=fit["k"], svi_density=fit["density"], moneyness=grid)
    return {
        **base, "dte": dte, "recalibrated": recal is not None,
        "market_vs_physical": pred["market_vs_physical"], "regime": pred["regime"],
        "edge": emap,
        "note": "prêmio físico-vs-risco-neutro por strike (isola vol/skew) — análise, não recomendação",
    }


def build_pricing_kernel(
    *, ticker: str, ohlc: list[tuple], closes: list[float], iv_history: list[float],
    spot: float, chain: list[dict], asof: str | None, T_days: int = 30,
) -> dict:
    """PRICING KERNEL empírico (SDF): ``M(S)=q(S)/p(S)`` — a razão risco-neutra/física por preço.

    A forma teoricamente correta do Edge Map: razão de densidades (não diferença de CDFs). Só o
    ATLAS consegue (exige a densidade física calibrada). ``slope<0`` = aversão a risco padrão;
    ``puzzle=True`` = M sobe na cauda (Rosenberg-Engle). Recusa honesto se a smile não é confiável.
    """
    prov = f"COTAHIST EOD {asof}" if asof else "COTAHIST EOD"
    base = {"ticker": ticker, "spot": round(spot, 2) if spot else None, "provenance": prov, "asof": asof}
    pred = build_prediction(ticker=ticker, ohlc=ohlc, closes=closes, iv_history=iv_history,
                            spot=spot, chain=chain, asof=asof, T_days=T_days)
    if pred["sigma"] is None or spot is None or spot <= 0:
        return {**base, "kernel": None, "note": "histórico insuficiente para o pricing kernel"}
    fit, dte = _fit_smile_near(chain, spot, asof, T_days)
    if fit is None:
        return {**base, "kernel": None, "market_vs_physical": pred["market_vs_physical"],
                "note": "smile de mercado não confiável (sem arbitragem-livre) — pricing kernel omitido"}
    physical = pred["market_vs_physical"]["physical"]
    dens = physical_density(spot=spot, sigma_iv=physical, rv=physical, vrp=0.0, T=dte / 365.0)
    grid = [round(float(x), 4) for x in np.linspace(0.85, 1.15, 25)]
    kern = pricing_kernel(spot=spot, forward=fit["forward"], phys_pdf=dens.logret_pdf,
                          svi_k=fit["k"], svi_density=fit["density"], moneyness=grid)
    return {
        **base, "dte": dte, "market_vs_physical": pred["market_vs_physical"], "regime": pred["regime"],
        "kernel": kern, "shape": kernel_shape(kern),
        "note": "razão densidade risco-neutra / física = pricing kernel (SDF) empírico — análise, não recomendação",
    }


def build_fair_iv(
    *, ticker: str, ohlc: list[tuple], closes: list[float], iv_history: list[float],
    spot: float, chain: list[dict], asof: str | None, T_days: int = 30,
) -> dict:
    """FAIR IV: a smile "justa" pela nossa vol física vs a smile de mercado, em VOL POINTS por strike.

    O VRP decomposto por strike na língua do trader (vol points). Recusa honesto se a smile não é
    confiável. Nota: física simétrica → linha justa ~plana; o gap é leitura de nível (VRP) forte.
    """
    prov = f"COTAHIST EOD {asof}" if asof else "COTAHIST EOD"
    base = {"ticker": ticker, "spot": round(spot, 2) if spot else None, "provenance": prov, "asof": asof}
    pred = build_prediction(ticker=ticker, ohlc=ohlc, closes=closes, iv_history=iv_history,
                            spot=spot, chain=chain, asof=asof, T_days=T_days)
    if pred["sigma"] is None or spot is None or spot <= 0:
        return {**base, "smile": None, "note": "histórico insuficiente para a fair IV"}
    fit, dte = _fit_smile_near(chain, spot, asof, T_days)
    if fit is None:
        return {**base, "smile": None, "market_vs_physical": pred["market_vs_physical"],
                "note": "smile de mercado não confiável (sem arbitragem-livre) — fair IV omitida"}
    phys_vol = pred["market_vs_physical"]["physical"]
    grid = [round(float(x), 4) for x in np.linspace(0.85, 1.15, 25)]
    fv = fair_iv_smile(spot=spot, forward=fit["forward"], phys_vol=phys_vol,
                       svi_params=fit["params"], T=dte / 365.0, moneyness=grid)
    return {
        **base, "dte": dte, "market_vs_physical": pred["market_vs_physical"], "regime": pred["regime"],
        **fv,
        "note": "smile de mercado vs vol física justa (VRP por strike, em vol points) — análise, não recomendação",
    }


def build_calibration_health(
    *, ticker: str, ohlc: list[tuple], closes: list[float], asof: str | None,
    window: int = 40, min_train: int = 26,
) -> dict:
    """MONITOR DE DESCALIBRAÇÃO (PIT-break): a saúde da densidade ao longo do tempo.

    O PIT out-of-sample já é calculado dia-a-dia; aqui ele NÃO é descartado — vira uma série
    rolante do p-valor de uniformidade. Quando cai sob 0.05 o modelo perdeu o regime: a densidade
    servida é uma mentira estatística naquele momento. Damos a saúde atual e há quantos pregões foi
    a última quebra. Honestidade auditada virando sinal — o oposto do POP que nunca admite erro.
    """
    prov = f"COTAHIST EOD {asof}" if asof else "COTAHIST EOD"
    base = {"ticker": ticker, "provenance": prov, "asof": asof, "window": window}
    rv = rv_series(ohlc, window=YZ_WINDOW)
    pit, _ = _walk_forward_pit(rv, closes, min_train=min_train)
    if len(pit) < window + 5:
        return {**base, "available": False,
                "note": "histórico curto para monitorar a calibração ao longo do tempo"}
    parr = np.asarray(pit, dtype=float)
    series = [round(float(pit_uniformity(parr[t - window:t])), 3) for t in range(window, len(parr) + 1)]
    current = series[-1]
    # Janelas rolantes COMPARTILHAM ~window−1 observações (autocorr ~0.9); contá-las como eventos
    # independentes engana ("45 quebras" = 1-2 episódios). Agrupa janelas <0.05 CONTÍGUAS num episódio.
    below = [i for i, p in enumerate(series) if p < 0.05]
    episodes: list[list[int]] = []
    for i in below:
        if episodes and i - episodes[-1][1] <= 1:
            episodes[-1][1] = i
        else:
            episodes.append([i, i])
    last_end = episodes[-1][1] if episodes else None
    return {
        **base, "available": True, "n": len(series), "series": series,   # mais recente = fim
        "current_p": current, "calibrated_now": bool(current >= 0.05),
        "ever_broke": bool(episodes), "n_breaks": len(episodes),
        "last_break_days_ago": (len(series) - 1 - last_end) if last_end is not None else None,
        "note": f"p-valor rolante do PIT (janela {window}d, KS de baixa potência); janelas sobrepostas "
                "agrupadas em episódios: <0.05 = densidade perdeu o regime — análise, não recomendação",
    }


def build_decision(
    *, ticker: str, ohlc: list[tuple], closes: list[float], iv_history: list[float],
    spot: float, chain: list[dict], asof: str | None, visao: str = "alta",
    capital: float = 20000.0, prazo: int = 30, perfil: str = "moderado",
    backtest_dsr: float | None = None,
) -> dict:
    """CAMADA DE DECISÃO: sintetiza todos os sinais num Cartão de Decisão por estrutura.

    O quê (estrutura) + por quê (concordância dos sinais) + quanto (Kelly+CVaR sob incerteza) + com
    que confiança (score de 5 fatores). Sabe se abster (PIT quebrado / smile ruim). Compõe os
    build_* já validados; não duplica lógica. Análise, nunca ordem.
    """
    prov = f"COTAHIST EOD {asof}" if asof else "COTAHIST EOD"
    perfil = perfil if perfil in ("conservador", "moderado", "agressivo") else "moderado"
    base = {"ticker": ticker, "spot": round(spot, 2) if spot else None, "provenance": prov, "asof": asof,
            "visao": visao, "capital": capital, "prazo": prazo, "perfil": perfil}
    pred = build_prediction(ticker=ticker, ohlc=ohlc, closes=closes, iv_history=iv_history,
                            spot=spot, chain=chain, asof=asof, T_days=prazo)
    if pred["sigma"] is None or spot is None or spot <= 0:
        return {**base, "available": False, "abstain": {"is_abstained": True, "reason": "histórico insuficiente"},
                "cards": [], "note": "sem dado suficiente para uma decisão honesta"}
    mvp, cal, reg, dist = (pred["market_vs_physical"], pred["calibration"], pred["regime"], pred["dist"])
    smile = mvp.get("market_smile")
    health = build_calibration_health(ticker=ticker, ohlc=ohlc, closes=closes, asof=asof)
    physical = mvp["physical"]
    dens = physical_density(spot=spot, sigma_iv=physical, rv=physical, vrp=0.0, T=prazo / 365.0)
    fit_smile = _fit_smile_near(chain, spot, asof, prazo)
    signals = _asset_signals(spot=spot, chain=chain, asof=asof, prazo=prazo, dens=dens, mvp=mvp,
                             regime=reg, fit_smile=fit_smile)
    # confiança da smile pela MESMA fonte dos sinais (_fit_smile_near, o fit rico), não o ponto ATM
    smile_conf = fit_smile[0] if fit_smile[0] is not None else smile
    conf = _confidence(cal=cal, health=health, smile=smile_conf, backtest_dsr=backtest_dsr,
                       agree_frac=signals["agree_frac"])
    # abstenção (gate duro): sem calibração ou densidade descalibrada HOJE → não opere
    hard = None
    if not cal.get("available"):
        hard = "sem histórico para uma densidade honesta"
    elif health.get("available") and not health.get("calibrated_now"):
        hard = "a densidade perdeu o regime hoje (PIT quebrado) — POP/EV não confiáveis agora"
    is_abstained = hard is not None
    # catálogo de estruturas (mesma base do consultor)
    opts = _expiry_options(chain, asof, prazo)
    cat = build_catalog(spot, dens, opts, visao=visao, capital=capital) if opts else []
    for s in cat:
        s["rationale"] = rationale(s, market_iv=mvp.get("iv"), physical=mvp.get("physical"))
    want = "neutro" if visao == "renda" else visao
    # não recomendar estruturas que CONTRADIZEM a visão do usuário (alta↔baixa); mantém a tese + neutras
    if want in ("alta", "baixa"):
        cat = [s for s in cat if s["thesis"] in (want, "neutro")]
    cards: list[dict] = []
    for s in cat:
        sizing = _kelly_lots(card=s, capital=capital, perfil=perfil,
                             size_conf=conf["size_confidence"], gate=conf["gate_backtest"])
        if is_abstained:
            sizing = {"lots": 0, "kelly_frac": 0.0, "reason": hard}   # dict limpo (sem metadados pré-abstenção)
        stance = 1 if s.get("vol_stance") == "vender" else -1
        aligned = signals["consensus"] == 0 or stance == signals["consensus"]
        card_score = round(conf["score"] * (1.0 if aligned else 0.6) * (1.0 if s["thesis"] == want else 0.85), 1)
        verdict = _verdict(card_score, sizing["lots"], is_abstained)
        cards.append({
            "name": s["name"], "thesis": s["thesis"], "defined_risk": s["defined_risk"],
            "vol_stance": s.get("vol_stance"), "legs": s["legs"], "breakevens": s["breakevens"],
            "verdict": verdict, "decision_score": card_score,
            "reactivate": reactivate_hint(verdict=verdict, lots=sizing["lots"],
                                          factors=conf["factors"], is_abstained=is_abstained),
            "sizing": sizing,
            "economics": {"pop": s["pop"], "ev_lot": s["per_lot"]["ev"], "cvar_lot": s["per_lot"]["cvar"],
                          "max_loss_lot": s["per_lot"]["max_loss"], "max_gain_lot": s["per_lot"]["max_gain"]},
            "why": _why(card=s, mvp=mvp, signals=signals, conf=conf, verdict=verdict),
            "invalidation": _invalidation(dens=dens, spot=spot, quantiles=dist["quantiles"],
                                          mvp=mvp, vol_stance=s.get("vol_stance"), thesis=s["thesis"]),
        })
    cards.sort(key=lambda c: (c["verdict"] not in ("EVITAR", "OBSERVAR"), c["decision_score"]), reverse=True)
    return {
        **base, "available": True,
        "confidence": conf,
        "abstain": {"is_abstained": is_abstained, "reason": hard},
        "signals": signals,
        "market_view": {"iv": mvp.get("iv"), "physical": mvp.get("physical"), "vrp": mvp.get("vrp"),
                        "regime": reg.get("regime"), "bias": reg.get("bias"), "iv_rank": reg.get("iv_rank")},
        "cards": cards,
        "liquidez_caveat": "sizing por risco/confiança; a liquidez real da opção (volume/OI) não está na base EOD — confira antes de executar",
        "note": "cartão de decisão: síntese dos sinais em o quê/por quê/quanto/confiança — análise, nunca ordem",
    }


def build_edge_backtest(*, ticker: str, universe: list[dict], asof: str | None, min_train: int = 30) -> dict:
    """BACKTEST ECONÔMICO do edge (gate ponta-a-ponta): o sinal de VRP físico sobrevive à deflação?

    ``universe``: ``[{ticker, ohlc, closes, dates, iv_series}]`` (``dates`` alinhado ao ``closes``;
    ``iv_series`` = ``[(date, iv)]`` datado). Roda o backtest gated (Deflated Sharpe sobre o portfólio)
    com join IV↔close por DATA e dá a curva de equity do ``ticker`` pedido. Verdicto HONESTO.
    """
    prov = f"COTAHIST EOD {asof}" if asof else "COTAHIST EOD"
    base = {"ticker": ticker, "provenance": prov, "asof": asof}
    uni = [{"ticker": u["ticker"], "rv": rv_series(u["ohlc"], window=YZ_WINDOW),
            "closes": u["closes"], "dates": u["dates"], "iv_by_date": dict(u["iv_series"])}
           for u in universe if len(u["closes"]) > YZ_WINDOW + min_train + 20]
    res = run_edge_backtest(uni, window=YZ_WINDOW, min_train=min_train)
    curve = None
    tgt = next((u for u in uni if u["ticker"] == ticker), None)
    if tgt is not None:
        pc, _ = vol_premium_pnl(tgt["iv_by_date"], tgt["dates"], tgt["rv"], tgt["closes"], window=YZ_WINDOW, min_train=min_train)
        if len(pc) >= 20:
            cum = np.cumsum(pc)
            curve = [round(float(c), 3) for c in cum]
    return {**base, "equity_curve": curve, **res}
