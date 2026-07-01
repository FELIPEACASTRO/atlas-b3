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

    # IV alta (35%) > realizada e > física → VRP>0 sempre → condicional == incondicional, prêmio +
    pc, pu = vol_premium_pnl([0.35] * len(closes), rv, closes, window=window, min_train=30)
    assert len(pc) > 40
    assert sum(pc) > 0
    assert pc == pu

    # IV baixa (10%) < física (~20%) → VRP<0 sempre → condicional zera todos os dias
    pcl, pul = vol_premium_pnl([0.10] * len(closes), rv, closes, window=window, min_train=30)
    assert all(x == 0.0 for x in pcl)
    assert any(x != 0.0 for x in pul)                    # incondicional ainda opera (e perde: vende vol barata)
