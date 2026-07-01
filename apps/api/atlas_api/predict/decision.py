"""Camada de Decisão — a síntese que vira decisão (o diferencial que ninguém tem).

O ATLAS tem 7 telas de análise isoladas; o usuário integra tudo na cabeça. Aqui está a 8ª chamada:
dado a VISÃO + CAPITAL + PERFIL do usuário, um **Cartão de Decisão** por estrutura — o quê, por quê,
quanto e com que confiança — que **sabe dizer "fique de fora"**.

Princípio (decisão sob ambiguidade de Knight/Ellsberg — Gilboa-Schmeidler, Hansen-Sargent):
    tamanho = (edge em que os sinais concordam) × (o quanto confio na minha densidade HOJE).
Quando a confiança cai (PIT quebrou, sinais divergem, backtest não confirma), o 2º fator → 0 e a
decisão converge SOZINHA para "não opere" — a abstenção é o limite da fórmula, não um caso especial.

Só é possível porque o ATLAS tem a densidade física PIT-auditada (o monitor de calibração é a
"medida de confiança" que nenhuma plataforma tem). Análise, nunca ordem.
"""
from __future__ import annotations

import math

import numpy as np

from .fair_iv import fair_iv_smile
from .kernel import pricing_kernel

# Perfis: KELLY_CAP = meio-Kelly (parâmetros estimados de 1 ano têm drawdown violento em full-Kelly).
# CVAR_BUDGET = fração do capital tolerada como PERDA ESPERADA na cauda 5%, por perfil (o teto de cauda).
KELLY_CAP = 0.5
_CVAR_BUDGET = {"conservador": 0.02, "moderado": 0.05, "agressivo": 0.10}


def _sign(x: float, tol: float = 1e-4) -> int:
    return 1 if x > tol else -1 if x < -tol else 0


def _asset_signals(*, spot, chain, asof, prazo, dens, mvp, regime, fit_smile) -> dict:
    """Sinais de 'vol cara' no nível do ativo (near-the-money): VRP, regime, Edge Map, Kernel, Fair IV.

    Cada um é uma leitura INDEPENDENTE do mesmo prêmio. Retorna os sinais (+1 vol cara/vender,
    −1 barata/comprar, 0 neutro) e a concordância (fração que aponta a direção majoritária).
    """
    sig: dict[str, int] = {}
    sig["vrp"] = _sign(mvp.get("vrp") or 0.0)                       # mercado − física
    bias = (regime or {}).get("bias", "")
    sig["regime"] = 1 if "vend" in bias else -1 if ("compr" in bias or "debit" in bias) else 0
    fit, dte = fit_smile
    if fit is not None and fit.get("usable"):
        grid = [round(float(x), 4) for x in np.linspace(0.97, 1.03, 5)]  # near-the-money
        forward = fit["forward"]
        # Edge Map (P_mercado − P_física) no NTM: >0 = mercado sobrevaloriza (vender)
        from .edge import premium_map
        emap = premium_map(spot=spot, forward=forward, phys_cdf=dens.logret_cdf,
                           svi_k=fit["k"], svi_density=fit["density"], moneyness=grid)
        sig["edge"] = _sign(float(np.mean([r["edge"] for r in emap])))
        # Pricing Kernel: M>1 no NTM = estado caro (vender)
        kern = pricing_kernel(spot=spot, forward=forward, phys_pdf=dens.logret_pdf,
                              svi_k=fit["k"], svi_density=fit["density"], moneyness=grid)
        sig["kernel"] = _sign(float(np.mean([r["m"] for r in kern])) - 1.0)
        # Fair IV: nível (VRP) > 0 = vol cara (vender)
        fv = fair_iv_smile(spot=spot, forward=forward, phys_vol=dens.sigma, svi_params=fit["params"],
                           T=dte / 365.0, moneyness=grid)
        sig["fair_iv"] = _sign(fv["level_gap"])
    present = {k: v for k, v in sig.items() if v != 0}
    if not present:
        return {"signals": sig, "consensus": 0, "agree_frac": 0.5, "n_signals": 0}
    n_sell = sum(1 for v in present.values() if v > 0)
    n_buy = len(present) - n_sell
    consensus = 1 if n_sell > n_buy else -1 if n_buy > n_sell else 0
    agree_frac = max(n_sell, n_buy) / len(present)
    return {"signals": sig, "consensus": consensus, "agree_frac": round(agree_frac, 3), "n_signals": len(present)}


def _confidence(*, cal, health, smile, backtest_dsr, agree_frac) -> dict:
    """Score de decisão 0–100 = PRODUTO de 5 fatores em [0,1] (um fator ruim derruba tudo — honestidade).

    C_calib (a densidade está calibrada HOJE) · C_data (amostra) · C_smile · C_agree (concordância) ·
    C_backtest (o edge sobrevive à deflação). Todos de campos que o motor já produz.
    """
    pit_p = float(cal.get("pit_p", 0.0)) if cal.get("available") else 0.0
    cov = float(cal.get("coverage", 0.0))
    nominal = float(cal.get("nominal", 0.8))
    n_test = int(cal.get("n_test", 0))
    calibrated_now = bool(health.get("calibrated_now", True)) if health.get("available") else True
    current_p = float(health.get("current_p", pit_p)) if health.get("available") else pit_p
    last_break = health.get("last_break_days_ago")

    s_pit = min(current_p / 0.5, 1.0)
    s_cov = max(0.0, 1.0 - abs(cov - nominal) / 0.10)
    c_calib = 0.0 if not calibrated_now else round(0.6 * s_pit + 0.4 * s_cov, 3)
    if last_break is not None and last_break < 10:                # quebra recente → regime instável
        c_calib *= 0.7
    c_data = min(n_test / 250.0, 1.0) if cal.get("available") else 0.0
    if smile and smile.get("usable"):                           # usável (arb-free + RMSE≤0.04) → [0.7, 1.0]
        c_smile = round(min(1.0, 0.7 + 0.3 * max(0.0, 1.0 - float(smile.get("rmse", 0.0)) / 0.04)), 3)
    else:
        c_smile = 0.5                                            # sem smile confiável: só direcional
    c_agree = round(agree_frac, 3)                               # 0.5 (empate) .. 1.0 (unânime)
    c_backtest = 0.85 if backtest_dsr is None else round(0.5 + 0.5 * float(backtest_dsr), 3)  # gate econômico

    factors = {"calibracao": round(c_calib, 3), "dados": round(c_data, 3), "smile": c_smile,
               "concordancia": c_agree, "backtest": c_backtest}
    vals = [c_calib, c_data, c_smile, c_agree, c_backtest]
    prod = 1.0
    for v in vals:
        prod *= max(v, 1e-6)
    # média geométrica: um fator fraco puxa o score; os KILLS de verdade (PIT quebrado, C_calib=0)
    # vêm da abstenção (gate duro), não de zerar o número aqui.
    score = round(100.0 * prod ** (1.0 / len(vals)), 1)
    band = "verde" if score >= 65 else "amarelo" if score >= 45 else "vermelho"
    return {"score": score, "band": band, "factors": factors,
            "size_confidence": round(min(max(c_calib, 0.0), 1.0), 3), "gate_backtest": c_backtest}


def _kelly_lots(*, card, capital, perfil, size_conf, gate) -> dict:
    """Sizing sob incerteza: Kelly (meio) usando o CVaR como perda de referência, teto de cauda por
    CVaR-budget, encolhido por confiança × gate. ``EV≤0`` ou Kelly≤0 → 0 lotes (a abstenção cai da fórmula)."""
    pl = card["per_lot"]
    ev, cvar, max_gain, max_loss = pl["ev"], pl["cvar"], pl["max_gain"], pl["max_loss"]
    pop = card["pop"]
    # perda de referência = CVaR (perda ESPERADA na cauda, não a catastrófica improvável do max_loss —
    # importante p/ estruturas de risco não-definido, onde max_loss é a ruína quase-impossível)
    loss_ref = abs(cvar) if cvar < 0 else abs(max_loss)
    if loss_ref <= 0 or max_gain <= 0 or ev <= 0:
        return {"lots": 0, "kelly_frac": 0.0, "reason": "sem edge (EV≤0) ou perda de referência inválida"}
    b = max_gain / loss_ref                                      # ganho : perda-esperada
    kelly = pop - (1.0 - pop) / b                                # fração de Kelly (crescimento log)
    if kelly <= 0:
        return {"lots": 0, "kelly_frac": round(kelly, 3), "reason": "Kelly ≤ 0: sem edge de crescimento"}
    n_kelly = kelly * KELLY_CAP * capital / loss_ref            # teto de crescimento (meio-Kelly)
    n_cvar = _CVAR_BUDGET[perfil] * capital / abs(cvar) if cvar < 0 else n_kelly  # teto de cauda por perfil
    lots = int(math.floor(min(n_kelly, n_cvar) * size_conf * gate))
    binding = "cauda (CVaR)" if n_cvar < n_kelly else "crescimento (Kelly)"
    return {"lots": max(lots, 0), "kelly_frac": round(kelly, 3), "kelly_used": round(kelly * KELLY_CAP * size_conf * gate, 3),
            "binding": binding, "cvar_at_risk": round(abs(cvar) * max(lots, 0), 2)}


def _invalidation(*, dens, spot, quantiles, mvp, vol_stance) -> dict:
    """Condições que MATAM a tese — da própria densidade e do VRP. A decisão tem prazo de validade."""
    selling = vol_stance == "vender"
    # invalidação de preço: cauda adversa (p10 p/ tese de alta/venda-de-put; p90 p/ baixa)
    price_stop = quantiles.get("p10") if mvp else None
    iv, phys = mvp.get("iv"), mvp.get("physical")
    vol_stop = None
    if iv is not None and phys is not None:
        vol_stop = ("VRP fecha: sair se a IV cair até a física (~%.0f%%)" % (phys * 100)) if selling \
            else ("sair se a IV subir muito acima da física (~%.0f%%)" % (phys * 100))
    return {"price_stop": price_stop, "vol_stop": vol_stop, "days_stop": 21,
            "calib_stop": "reavalie se o monitor de calibração (PIT) quebrar"}


def _verdict(score: float, lots: int, abstain: bool) -> str:
    if abstain or lots <= 0:
        return "EVITAR" if abstain else "OBSERVAR"
    if score >= 55:
        return "OPERAR"
    if score >= 30:
        return "OPERAR PEQUENO"
    return "OBSERVAR"


def _why(*, card, mvp, signals, conf, verdict) -> dict:
    """Explicação determinística em 3 atos: tese×fato → concordância dos sinais → a ressalva honesta."""
    iv, phys = mvp.get("iv"), mvp.get("physical")
    rich = iv is not None and phys is not None and iv > phys + 0.005
    selling = card.get("vol_stance") == "vender"
    ato1 = card.get("rationale", "")
    names = {"vrp": "VRP", "regime": "regime", "edge": "Edge Map", "kernel": "Pricing Kernel", "fair_iv": "Fair IV"}
    stance = 1 if selling else -1
    concord = [names[k] for k, v in signals["signals"].items() if v == stance and v != 0]
    diverge = [names[k] for k, v in signals["signals"].items() if v == -stance and v != 0]
    ato2 = (f"{len(concord)} de {signals['n_signals']} sinais apontam o mesmo lado ({', '.join(concord)})"
            if concord else "os sinais não sustentam essa direção")
    if diverge:
        ato2 += f"; divergem: {', '.join(diverge)}"
    caveats = []
    f = conf["factors"]
    if f["calibracao"] < 0.6:
        caveats.append("a densidade não está plenamente calibrada")
    if f["backtest"] < 0.9:
        caveats.append("o backtest do edge é apenas limítrofe com ~1 ano")
    if f["concordancia"] < 0.7:
        caveats.append("os sinais não são unânimes")
    if f["smile"] < 0.7:
        caveats.append("a smile de mercado é imperfeita")
    ato3 = ("Ressalva honesta: " + "; ".join(caveats) + " — por isso a confiança e o tamanho foram reduzidos.") \
        if caveats else "Os fatores de confiança estão sólidos."
    return {"tese": ato1, "sinais": ato2, "ressalva": ato3,
            "rich_vol": bool(rich), "concordam": concord, "divergem": diverge}
