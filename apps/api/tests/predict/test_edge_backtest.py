"""Backtest econômico do edge: prêmio de vol diário, condicionado ao VRP físico, gated."""
import math
import random

from atlas_api.predict.edge_backtest import sharpe, vol_premium_pnl


def test_sharpe_handles_zero_variance_and_positive_series():
    assert sharpe([0.01] * 100) == 0.0                   # variância zero → 0 (não infinito/NaN)
    assert sharpe([0.02, -0.01, 0.03, 0.01, 0.02, -0.005] * 20) > 0


def _closes(n: int, sigma: float, seed: int = 3):
    random.seed(seed)
    px = 100.0
    out = [px]
    for _ in range(n):
        px = px * math.exp(random.gauss(0.0, sigma))
        out.append(px)
    return out


def test_premium_positive_and_conditions_on_vrp():
    window, n = 5, 160
    closes = _closes(n + window + 2, 0.01)               # vol realizada baixa (~16% a.a.)
    rv = [0.20 + 0.01 * math.sin(i / 3.0) for i in range(n)]   # física ~20%
    dates = [f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(len(closes))]  # datas sintéticas por índice

    # IV alta (35%) > realizada e > física → VRP>0 sempre → condicional == incondicional, prêmio +
    iv_hi = {d: 0.35 for d in dates}
    pc, pu = vol_premium_pnl(iv_hi, dates, rv, closes, window=window, min_train=30)
    assert len(pc) > 40
    assert sum(pc) > 0
    assert pc == pu

    # IV baixa (10%) < física (~20%) → VRP<0 sempre → condicional zera todos os dias
    iv_lo = {d: 0.10 for d in dates}
    pcl, pul = vol_premium_pnl(iv_lo, dates, rv, closes, window=window, min_train=30)
    assert all(x == 0.0 for x in pcl)
    assert any(x != 0.0 for x in pul)                    # incondicional ainda opera (e perde: vende vol barata)

    # JOIN POR DATA: se a IV falta em alguns dias (buraco interno), esses dias são pulados (não fabricados)
    iv_gaps = {d: 0.35 for i, d in enumerate(dates) if i % 3 != 0}   # ~1/3 dos dias sem IV
    pcg, pug = vol_premium_pnl(iv_gaps, dates, rv, closes, window=window, min_train=30)
    assert 0 < len(pcg) < len(pc)                        # menos dias operados (os sem IV foram pulados)
