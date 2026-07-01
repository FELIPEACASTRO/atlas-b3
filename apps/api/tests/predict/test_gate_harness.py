"""Harness do gate (multiple-testing): Deflated Sharpe, Model Confidence Set, Hansen SPA.

Cada método é verificado numericamente (Monte Carlo / cenário sintético onde a resposta é
conhecida) para não introduzir erro sutil. É o 'produto de verdade' do spec: julgar edges
com honestidade sob busca múltipla.
"""
import numpy as np

from atlas_api.predict.validate import (
    _expected_max_normal,
    deflated_sharpe,
    hansen_spa,
    model_confidence_set,
)


# ---- Deflated Sharpe Ratio ----

def test_expected_max_normal_matches_monte_carlo():
    rng = np.random.default_rng(1)
    for n in (10, 50, 200):
        mc = float(np.mean([rng.standard_normal(n).max() for _ in range(30000)]))
        assert abs(_expected_max_normal(n) - mc) < 0.1     # aproximação bate o MC


def test_deflated_sharpe_falls_with_more_trials():
    rng = np.random.default_rng(0)
    rets = rng.normal(0.0012, 0.01, 600)                   # Sharpe positivo
    dsr_few = deflated_sharpe(rets, rng.normal(0, 0.05, 5))
    dsr_many = deflated_sharpe(rets, rng.normal(0, 0.05, 300))
    assert 0.0 <= dsr_many <= 1.0 and 0.0 <= dsr_few <= 1.0
    assert dsr_many < dsr_few                              # mais tentativas → mais defla → menos confiança


def test_deflated_sharpe_low_for_no_edge():
    rng = np.random.default_rng(2)
    rets = rng.normal(0.0, 0.01, 600)                      # sem edge
    assert deflated_sharpe(rets, rng.normal(0, 0.05, 100)) < 0.6


# ---- Model Confidence Set ----

def test_mcs_keeps_only_the_dominant_model():
    rng = np.random.default_rng(3)
    n = 500
    good = np.abs(rng.normal(0.02, 0.005, n))              # perdas pequenas (melhor)
    bad1 = good + np.abs(rng.normal(0.05, 0.01, n))        # claramente piores
    bad2 = good + np.abs(rng.normal(0.06, 0.01, n))
    mcs = model_confidence_set({"good": good, "bad1": bad1, "bad2": bad2}, alpha=0.1, seed=0)
    assert mcs == {"good"}                                  # só o dominante sobrevive


def test_mcs_keeps_all_when_indistinguishable():
    rng = np.random.default_rng(4)
    n = 500
    base = np.abs(rng.normal(0.02, 0.005, n))
    losses = {"a": base + rng.normal(0, 1e-6, n), "b": base + rng.normal(0, 1e-6, n),
              "c": base + rng.normal(0, 1e-6, n)}
    mcs = model_confidence_set(losses, alpha=0.1, seed=0)
    assert mcs == {"a", "b", "c"}                          # empate → todos ficam


# ---- Hansen SPA ----

def test_spa_rejects_when_a_model_beats_benchmark():
    rng = np.random.default_rng(5)
    n = 500
    bench = np.abs(rng.normal(0.05, 0.01, n))              # benchmark (perdas maiores)
    better = np.abs(rng.normal(0.02, 0.005, n))           # bate o benchmark
    p = hansen_spa(bench, {"m": better}, seed=0)
    assert p < 0.05                                        # rejeita H0 (nenhum bate) → há edge


def test_spa_does_not_reject_when_no_model_beats():
    rng = np.random.default_rng(6)
    n = 500
    bench = np.abs(rng.normal(0.02, 0.005, n))
    worse = bench + np.abs(rng.normal(0.03, 0.01, n))     # pior que o benchmark
    p = hansen_spa(bench, {"m": worse}, seed=0)
    assert p > 0.10                                        # não rejeita (nada bate o benchmark)
