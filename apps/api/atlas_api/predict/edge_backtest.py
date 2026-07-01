"""Backtest econômico do edge — o gate ligado ponta-a-ponta (a prova que faltava).

A maior lacuna vs o estado-da-arte (ORATS prova o edge desde 2007): não basta a densidade passar
no PIT, o SINAL econômico tem que sobreviver. Aqui testamos "vender vol quando a NOSSA física diz
que está cara" (VRP físico > 0), walk-forward, e passamos pelo Deflated Sharpe (López de Prado) que
desconta o multiple-testing sobre o universo. HONESTO: se não sobrevive à deflação (com 1 ano a
potência é baixa), reportamos isso — como PDV e HARX foram reprovados.

P&L: proxy GROSSEIRO de prêmio de variância diário — NÃO um P&L de vendedor de vol (sem delta-hedge,
sem gamma/vega path-dependente, sem custos). Vende vol a ``iv`` e paga a vol realizada do dia
(``|retorno|·√(π/2)·√252``, estimador não-enviesado de vol via desvio absoluto). ``premium = iv −
realizada``. O Sharpe por-nome anualizado é inflado pelo horizonte (√252 sobre um edge diário) e
subestima o risco de cauda (um crash aparece como UM dia ruim, não wipeout); por isso a decisão usa o
PORTFÓLIO deflacionado, não os Sharpes por-nome. Análise, não recomendação.
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
    # Alinhamento à direita assume que iv e closes terminam no MESMO dia (asof) e que a iv só falta no
    # COMEÇO. Se iv_history > closes, a assunção falha → não fabrica (retorna vazio). Limitação conhecida:
    # buracos INTERNOS na iv (dias sem atm_iv no meio) desalinham por posição; correção ideal = juntar por data.
    offset = len(closes) - len(iv_history)
    if offset < 0:
        return [], []
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


def _equal_weight_portfolio(series: list[list[float]]) -> list[float]:
    """Portfólio equal-weight: média cross-section por dia, alinhada à DIREITA (todos terminam ~asof).

    Concatenar nomes correlacionados (pool) e usar n=Σdias é ANTI-conservador (trata dias
    correlacionados como independentes → infla o t-stat) e dilui o Sharpe. O objeto negociável e a
    unidade estatística correta é o portfólio: média diária dos nomes, n = nº de dias do portfólio.
    """
    series = [s for s in series if s]
    if not series:
        return []
    maxlen = max(len(s) for s in series)
    arr = np.full((len(series), maxlen), np.nan)
    for i, s in enumerate(series):
        arr[i, maxlen - len(s):] = s                     # alinha à direita: última obs = ~asof
    with np.errstate(invalid="ignore"):
        port = np.nanmean(arr, axis=0)
    return [float(x) for x in port if not math.isnan(x)]


def run_edge_backtest(universe: list[dict], *, window: int, min_train: int = 30,
                      min_days: int = 60) -> dict:
    """Backtest gated do sinal VRP sobre um universo. ``universe``: [{ticker, rv, closes, iv_history}].

    Deflated Sharpe (López de Prado) aplicado ao PORTFÓLIO equal-weight (o objeto negociável), com
    ``trial_sharpes`` = Sharpes por-observação por nome (deflação de multiple-testing). Verdicto
    HONESTO em 3 faixas: confirmado (P>0.95), limítrofe (0.5–0.95), não confirmado (<0.5).
    """
    per_name: list[dict] = []
    trial_sharpes: list[float] = []
    series_c: list[list[float]] = []
    series_u: list[list[float]] = []
    for u in universe:
        pc, pu = vol_premium_pnl(u["iv_history"], u["rv"], u["closes"], window=window, min_train=min_train)
        if len(pc) < min_days:
            continue
        n_trades = int(sum(1 for x in pc if x != 0.0))
        traded = [x for x in pc if x != 0.0]             # Sharpe condicional sobre dias NEGOCIADOS (M4b)
        per_name.append({
            "ticker": u["ticker"], "n": len(pc), "trades": n_trades,
            "sharpe_cond": round(sharpe(traded), 2), "sharpe_uncond": round(sharpe(pu), 2),
            "total_pnl": round(float(np.sum(pc)), 3),
            "hit_rate": round(float(np.mean([1.0 if x > 0 else 0.0 for x in traded]) if traded else 0.0), 3),
        })
        trial_sharpes.append(sharpe(pc, annualize=False))  # por observação: casa com o sr interno do gate
        series_c.append(pc)
        series_u.append(pu)
    port_c = _equal_weight_portfolio(series_c)
    port_u = _equal_weight_portfolio(series_u)
    if len(trial_sharpes) < 2 or len(port_c) < min_days:
        return {"available": False, "note": "universo/histórico insuficiente para o backtest gated"}
    dsr = float(deflated_sharpe(port_c, trial_sharpes))  # objeto certo: o portfólio; n = dias do portfólio
    port_sh, uncond_sh = sharpe(port_c), sharpe(port_u)
    significant, borderline = dsr > 0.95, 0.5 <= dsr <= 0.95
    adds_value = port_sh > uncond_sh + 0.10              # margem MATERIAL (não flip na 4ª casa — M4b)
    verdict = (
        "CONFIRMADO: o prêmio de VRP sobrevive à deflação de multiple-testing no portfólio"
        if significant else
        f"LIMÍTROFE: o prêmio de VRP é quase-significativo no portfólio (deflated Sharpe {dsr:.2f}); "
        "com ~1 ano a evidência é sugestiva, não conclusiva"
        if borderline else
        "NÃO CONFIRMADO: o prêmio não sobrevive à deflação"
    )
    if not adds_value:
        verdict += " — e o condicionamento pela nossa física não agrega valor material vs vender vol sempre (o edge é o VRP em si, não a nossa seleção)"
    return {
        "available": True, "n_names": len(per_name), "portfolio_days": len(port_c),
        "portfolio_sharpe_cond": round(port_sh, 2), "portfolio_sharpe_uncond": round(uncond_sh, 2),
        "deflated_sharpe": round(dsr, 3), "significant": bool(significant), "borderline": bool(borderline),
        "adds_value_vs_uncond": bool(adds_value),
        "per_name": sorted(per_name, key=lambda r: r["sharpe_cond"], reverse=True),
        "verdict": verdict,
    }
