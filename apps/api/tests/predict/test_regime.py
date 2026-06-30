"""Regime de vol → viés de ESTRUTURA (análise, não recomendação).

Backwardation (stress de curto prazo) tem prioridade sobre o sinal de vender prêmio
— gestão de risco primeiro. Entradas reusam iv_rank/vrp/skew do pricing; saída sempre
honesta ("indisponivel" quando falta dado), com gates B3 (liquidez, exercício americano).
"""
from atlas_api.predict.regime import regime, strategy_bias


def test_regime_sell_premium_when_ivr_high_vrp_pos_contango():
    assert regime(iv_rank=75, vrp=0.06, term_slope=0.02, skew=0.03) == "vender prêmio"


def test_regime_backwardation_stops_naked_selling_even_with_high_ivr():
    # backwardation overrides o sinal de vender prêmio (risco de cauda no curto prazo)
    assert regime(iv_rank=80, vrp=0.05, term_slope=-0.03, skew=0.05) == "parar venda a descoberto"


def test_regime_buy_debit_when_ivr_low():
    assert regime(iv_rank=15, vrp=-0.01, term_slope=0.01, skew=0.02) == "comprar/debit"


def test_regime_neutral_in_between():
    assert regime(iv_rank=45, vrp=0.01, term_slope=0.01, skew=0.02) == "neutro"


def test_regime_none_input_is_honest_indisponivel():
    assert regime(iv_rank=None, vrp=0.05, term_slope=0.02, skew=0.0) == "indisponivel"
    assert regime(iv_rank=70, vrp=None, term_slope=0.02, skew=0.0) == "indisponivel"


def test_strategy_bias_carries_b3_gates_and_is_analysis_not_order():
    b = strategy_bias("vender prêmio")
    assert isinstance(b["bias"], str) and b["examples"]
    assert b["b3_gates"]                                   # liquidez + exercício americano
    assert any("exerc" in g.lower() for g in b["b3_gates"])
    # indisponivel não inventa estrutura nem gates
    assert strategy_bias("indisponivel")["examples"] == []
