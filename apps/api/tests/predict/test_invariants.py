"""Invariantes do motor (property-based com seed fixo) — travam as garantias que não podem quebrar.

Segue o plano de QA: quantificadores universais ("∀ perfil, ∀ capital, ∀ card válido: ...") que
example-tests de 1 ponto não pegam. Sem dep nova (rng semeado em pytest cobre o essencial).
"""
import math
import random

from atlas_api.predict.decision import _confidence, _kelly_lots, _verdict
from atlas_api.predict.strategies import CVAR_BUDGET

_PERFIS = ("conservador", "moderado", "agressivo")


def _rand_card(rng: random.Random) -> dict:
    max_gain = rng.uniform(10.0, 2000.0)
    max_loss = -rng.uniform(50.0, 5000.0)
    cvar = -rng.uniform(20.0, abs(max_loss))         # |cvar| ≤ |max_loss|, cauda esperada
    ev = rng.uniform(-50.0, 100.0)
    pop = rng.uniform(0.3, 0.95)
    return {"pop": pop, "per_lot": {"ev": ev, "cvar": cvar, "max_gain": max_gain, "max_loss": max_loss}}


def test_kelly_invariants_over_random_cards():
    rng = random.Random(20260701)
    for _ in range(3000):
        card = _rand_card(rng)
        perfil = rng.choice(_PERFIS)
        capital = rng.uniform(1000.0, 1e8)
        sc, gate = rng.uniform(0.0, 1.0), rng.uniform(0.5, 1.0)
        out = _kelly_lots(card=card, capital=capital, perfil=perfil, size_conf=sc, gate=gate)
        # I6: lotes sempre inteiro ≥ 0
        assert isinstance(out["lots"], int) and out["lots"] >= 0
        # I5: sem edge (EV≤0) → 0 lotes
        if card["per_lot"]["ev"] <= 0:
            assert out["lots"] == 0
        # I1 (o invariante do dinheiro): risco de cauda NUNCA acima do budget do perfil (folga de 1 lote)
        loss_ref = abs(card["per_lot"]["cvar"])
        assert out.get("cvar_at_risk", 0.0) <= CVAR_BUDGET[perfil] * capital + loss_ref


def test_kelly_monotonic_in_capital_and_confidence():
    rng = random.Random(7)
    card = _rand_card(rng)
    card["per_lot"]["ev"] = 50.0                       # garante edge positivo
    lots_lo = _kelly_lots(card=card, capital=20000.0, perfil="moderado", size_conf=1.0, gate=1.0)["lots"]
    lots_hi = _kelly_lots(card=card, capital=200000.0, perfil="moderado", size_conf=1.0, gate=1.0)["lots"]
    assert lots_hi >= lots_lo                          # mais capital → não menos lotes
    less_conf = _kelly_lots(card=card, capital=20000.0, perfil="moderado", size_conf=0.3, gate=1.0)["lots"]
    assert less_conf <= lots_lo                        # menos confiança → não mais lotes
    # perfis: conservador ≤ moderado ≤ agressivo
    kw = dict(card=card, capital=20000.0, size_conf=1.0, gate=1.0)
    lc = [_kelly_lots(perfil=p, **kw)["lots"] for p in _PERFIS]
    assert lc[0] <= lc[1] <= lc[2]


def test_confidence_score_bounds_and_pit_gate():
    rng = random.Random(99)
    for _ in range(1000):
        cal = {"available": True, "pit_p": rng.uniform(0, 1), "coverage": rng.uniform(0.6, 0.95),
               "nominal": 0.8, "n_test": rng.randint(0, 400)}
        health = {"available": True, "calibrated_now": rng.random() > 0.3,
                  "current_p": rng.uniform(0, 1), "last_break_days_ago": rng.randint(0, 200)}
        smile = {"usable": rng.random() > 0.5, "rmse": rng.uniform(0, 0.04)}
        c = _confidence(cal=cal, health=health, smile=smile, backtest_dsr=rng.uniform(0, 1),
                        agree_frac=rng.uniform(0.5, 1.0))
        assert 0.0 <= c["score"] <= 100.0                         # I8
        assert all(0.0 <= v <= 1.0 for v in c["factors"].values())  # I10
        if not health["calibrated_now"]:
            assert c["factors"]["calibracao"] == 0.0              # I11: PIT quebrado hoje → 0


def test_verdict_bands():
    assert _verdict(80.0, 5, abstain=True) == "EVITAR"
    assert _verdict(80.0, 0, abstain=False) == "OBSERVAR"
    assert _verdict(54.9, 5, abstain=False) == "OPERAR PEQUENO"   # boundary abaixo de 55
    assert _verdict(55.0, 5, abstain=False) == "OPERAR"           # boundary em 55
    assert _verdict(29.9, 5, abstain=False) == "OBSERVAR"         # boundary abaixo de 30
