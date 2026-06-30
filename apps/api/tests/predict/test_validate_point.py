"""O GATE (forecast pontual): QLIKE + Diebold-Mariano (HAC) + walk-forward sem vazamento."""
import numpy as np

from atlas_api.predict.validate import diebold_mariano, qlike, walk_forward


def test_qlike_zero_at_equality():
    assert abs(qlike(0.04, 0.04)) < 1e-12


def test_qlike_positive_under_error():
    # QLIKE é uma divergência >= 0, mínima na igualdade; penaliza erro p/ cima e p/ baixo
    assert qlike(0.04, 0.06) > 0
    assert qlike(0.04, 0.02) > 0


def test_dm_detects_injected_edge():
    rng = np.random.default_rng(0)
    var = np.abs(rng.normal(0.04, 0.008, 600))           # UNIDADE = variância (σ²)
    good = var * np.exp(rng.normal(0, 0.05, 600))         # ruído MULTIPLICATIVO log-normal => >0
    bad = var * np.exp(rng.normal(0, 0.40, 600))
    stat, p = diebold_mariano(var, good, bad, loss="qlike")
    assert stat < 0 and p < 0.05                          # 'good' tem perda menor, com significância


def test_walk_forward_is_point_in_time():
    # forecaster ingênuo (último valor observado): prova que treina em [0,t) e prevê t
    series = list(range(10))
    out = list(walk_forward(series, lambda tr: None, lambda _m, tr: tr[-1], min_train=3))
    actuals = [a for a, _ in out]
    preds = [p for _, p in out]
    assert actuals == [3, 4, 5, 6, 7, 8, 9]
    assert preds == [2, 3, 4, 5, 6, 7, 8]                 # cada previsão = valor em t-1 (sem ver o futuro)
