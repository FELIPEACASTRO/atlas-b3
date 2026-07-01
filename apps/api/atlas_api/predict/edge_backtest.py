"""Backtest econômico do edge — o gate ligado ponta-a-ponta (a prova que faltava).

A maior lacuna vs o estado-da-arte (ORATS prova o edge desde 2007): não basta a densidade passar
no PIT, o SINAL econômico tem que sobreviver. Aqui testamos "vender vol quando a NOSSA física diz
que está cara" (VRP físico > 0), walk-forward, e passamos pelo Deflated Sharpe (López de Prado) que
desconta o multiple-testing sobre o universo. HONESTO: se não sobrevive à deflação (com 1 ano a
potência é baixa), reportamos isso — como PDV e HARX foram reprovados.

P&L: proxy de PRÊMIO DE VOL diário (não P&L de opção delta-hedgeada): vende vol a ``iv`` e paga a
vol realizada do dia (``|retorno|·√(π/2)·√252``, estimador não-enviesado de vol via desvio absoluto).
``premium = iv − realizada``. É o prêmio de variância capturado por dia — o que o vendedor de vol
embolsa em média. Análise, não recomendação.
"""
from __future__ import annotations

import math

import numpy as np

from atlas_api.pricing.har import fit_har, forecast_har

from .validate import deflated_sharpe

_ANN = math.sqrt(252.0)
_ABS2STD = math.sqrt(math.pi / 2.0)                       # E[|r|]·√(π/2) = σ (proxy não-enviesado)


def sharpe(pnl, *, annualize: bool = True) -> float:
    """Sharpe de uma série de P&L diária. ``annualize`` ×√252 (exibição); sem, por observação
    (a unidade que o ``deflated_sharpe`` usa internamente — casar evita comparar maçã com laranja)."""
    a = np.asarray(pnl, dtype=float)
    sd = a.std(ddof=1) if a.size > 2 else 0.0
    if sd <= 1e-12:
        return 0.0
    return float(a.mean() / sd * (_ANN if annualize else 1.0))   # tol: variância ~0 (soma) → 0, não explode


def vol_premium_pnl(iv_history: list[float], rv: list[float], closes: list[float],
                    *, window: int, min_train: int = 30) -> tuple[list[float], list[float]]:
    """P&L diário de vender vol: CONDICIONAL (só quando o físico diz cara, VRP>0) vs INCONDICIONAL.

    Alinha ``iv_history`` (grade diária dos closes) à série ``rv`` (que termina ``window-1`` barras à
    frente). Retorna ``(pnl_condicional, pnl_incondicional)`` em unidades de vol anualizada.
    """
    pnl_c: list[float] = []
    pnl_u: list[float] = []
    offset = len(closes) - len(iv_history)               # iv e closes terminam no asof; iv pode faltar no começo
    for i in range(min_train, len(rv)):
        day = i + window - 1                             # índice em closes alinhado a rv[i]
        if day + 1 >= len(closes):
            break
        iv_idx = day - offset                            # alinha iv à direita (mesma data que closes[day])
        if iv_idx < 0 or iv_idx >= len(iv_history):
            continue
        iv_t = iv_history[iv_idx]
        if not (iv_t and iv_t > 0) or closes[day] <= 0 or closes[day + 1] <= 0:
            continue
        fc = forecast_har(fit_har(rv[:i]), rv[:i])       # previsão física point-in-time (sem look-ahead)
        if not (fc > 0):
            continue
        realized = abs(math.log(closes[day + 1] / closes[day])) * _ABS2STD * _ANN
        premium = iv_t - realized                        # vende vol a iv, paga a realizada
        pnl_u.append(premium)                            # incondicional: vende sempre
        pnl_c.append(premium if (iv_t - fc) > 0 else 0.0)  # condicional: só quando o físico diz cara
    return pnl_c, pnl_u


def run_edge_backtest(universe: list[dict], *, window: int, min_train: int = 30,
                      min_days: int = 60) -> dict:
    """Backtest gated do sinal VRP sobre um universo. ``universe``: [{ticker, rv, closes, iv_history}].

    Deflated Sharpe sobre o pool, com ``trial_sharpes`` = os Sharpes por nome (deflação de
    multiple-testing). Verdicto HONESTO: só "confirmado" se sobrevive à deflação (P>0.95).
    """
    per_name: list[dict] = []
    trial_sharpes: list[float] = []
    pooled_c: list[float] = []
    pooled_u: list[float] = []
    for u in universe:
        pc, pu = vol_premium_pnl(u["iv_history"], u["rv"], u["closes"], window=window, min_train=min_train)
        if len(pc) < min_days:
            continue
        sc, su = sharpe(pc), sharpe(pu)                  # anualizados (exibição)
        n_trades = int(sum(1 for x in pc if x != 0.0))
        per_name.append({
            "ticker": u["ticker"], "n": len(pc), "trades": n_trades,
            "sharpe_cond": round(sc, 2), "sharpe_uncond": round(su, 2),
            "total_pnl": round(float(np.sum(pc)), 3),
            "hit_rate": round(float(np.mean([1.0 if x > 0 else 0.0 for x in pc if x != 0.0]) if n_trades else 0.0), 3),
        })
        trial_sharpes.append(sharpe(pc, annualize=False))  # por observação: casa com o sr interno do gate
        pooled_c.extend(pc)
        pooled_u.extend(pu)
    if len(trial_sharpes) < 2 or len(pooled_c) < min_days:
        return {"available": False, "note": "universo/histórico insuficiente para o backtest gated"}
    dsr = deflated_sharpe(pooled_c, trial_sharpes)       # P(Sharpe verdadeiro > 0), deflacionado (unidades casadas)
    pooled_sh = sharpe(pooled_c)
    uncond_sh = sharpe(pooled_u)
    significant = dsr > 0.95
    return {
        "available": True, "n_names": len(per_name), "pooled_days": len(pooled_c),
        "pooled_sharpe_cond": round(pooled_sh, 2), "pooled_sharpe_uncond": round(uncond_sh, 2),
        "deflated_sharpe": round(float(dsr), 3), "significant": bool(significant),
        "adds_value_vs_uncond": bool(pooled_sh > uncond_sh),
        "per_name": sorted(per_name, key=lambda r: r["sharpe_cond"], reverse=True),
        "verdict": (
            "CONFIRMADO: o sinal de VRP físico sobrevive à deflação de multiple-testing"
            if significant else
            "NÃO CONFIRMADO: o sinal não sobrevive à deflação (com ~1 ano a potência é baixa) — registrado honestamente, como PDV e HARX"
        ),
    }
