"""Camada de decisão: sizing Kelly+CVaR sob incerteza, score de confiança, abstenção honesta."""
from atlas_api.predict.decision import _confidence, _kelly_lots, _verdict


def test_kelly_zero_when_no_growth_edge():
    # EV≤0 → sem edge → 0 lotes (a abstenção cai da fórmula)
    card = {"pop": 0.60, "vol_stance": "vender",
            "per_lot": {"ev": -5.0, "cvar": -200.0, "max_gain": 100.0, "max_loss": -300.0}}
    out = _kelly_lots(card=card, capital=20000.0, perfil="moderado", size_conf=0.9, gate=0.95)
    assert out["lots"] == 0


def test_kelly_sizes_within_cvar_budget():
    # edge positivo, alta POP → dimensiona, mas nunca acima do orçamento de CVaR do perfil (5% moderado)
    card = {"pop": 0.85, "vol_stance": "vender",
            "per_lot": {"ev": 20.0, "cvar": -250.0, "max_gain": 150.0, "max_loss": -3000.0}}
    out = _kelly_lots(card=card, capital=20000.0, perfil="moderado", size_conf=1.0, gate=1.0)
    assert out["lots"] >= 1
    assert out["cvar_at_risk"] <= 0.05 * 20000.0 + 250.0        # dentro do budget (±1 lote)
    # perfil conservador arrisca MENOS que o agressivo
    cons = _kelly_lots(card=card, capital=20000.0, perfil="conservador", size_conf=1.0, gate=1.0)
    agg = _kelly_lots(card=card, capital=20000.0, perfil="agressivo", size_conf=1.0, gate=1.0)
    assert cons["lots"] <= out["lots"] <= agg["lots"]


def test_confidence_geomean_and_pit_break_gate():
    cal = {"available": True, "pit_p": 0.5, "coverage": 0.8, "nominal": 0.8, "n_test": 250}
    health = {"available": True, "calibrated_now": True, "current_p": 0.5, "last_break_days_ago": 90}
    smile = {"usable": True, "rmse": 0.0}
    c = _confidence(cal=cal, health=health, smile=smile, backtest_dsr=1.0, agree_frac=1.0)
    assert c["score"] > 90                                      # todos os fatores ~1 → score alto
    # PIT quebrado HOJE → fator calibração = 0 (o kill honesto)
    c2 = _confidence(cal=cal, health={**health, "calibrated_now": False}, smile=smile,
                     backtest_dsr=1.0, agree_frac=1.0)
    assert c2["factors"]["calibracao"] == 0.0
    assert c2["score"] < c["score"]


def test_verdict_bands_and_abstention():
    assert _verdict(80.0, 5, abstain=True) == "EVITAR"          # abstenção força EVITAR
    assert _verdict(80.0, 0, abstain=False) == "OBSERVAR"       # 0 lotes → observar
    assert _verdict(70.0, 5, abstain=False) == "OPERAR"
    assert _verdict(40.0, 5, abstain=False) == "OPERAR PEQUENO"
