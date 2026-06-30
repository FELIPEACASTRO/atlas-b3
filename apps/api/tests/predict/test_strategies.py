"""Consultor de estratégias — avaliador de estruturas por P&L, POP e valor esperado.

O núcleo do consultor: dada a densidade REAL do /predict e as pernas de uma estrutura,
computa payoff no vencimento, POP (prob. de lucro), valor esperado (∫payoff·densidade),
risco máximo, retorno máximo e breakevens. Análise, não recomendação.
"""
from atlas_api.predict.distribution import physical_density
from atlas_api.predict.strategies import Leg, evaluate, payoff


def test_long_call_payoff_and_breakeven():
    legs = [Leg("call", "long", 38.0, 2.0)]
    assert payoff(legs, 36.0) == -200.0          # abaixo do strike: perde o prêmio (×100)
    assert abs(payoff(legs, 40.0)) < 1e-9         # breakeven = K + prêmio
    assert payoff(legs, 42.0) == 200.0            # acima: lucro


def test_bull_call_spread_caps_gain_and_loss():
    legs = [Leg("call", "long", 38.0, 2.0), Leg("call", "short", 42.0, 0.8)]
    net = 1.2                                      # débito líquido
    assert abs(payoff(legs, 36.0) - (-net * 100)) < 1e-9          # perda máxima
    assert abs(payoff(legs, 44.0) - ((42 - 38 - net) * 100)) < 1e-9   # ganho máximo travado
    assert abs(payoff(legs, 38.0 + net)) < 1e-9                   # breakeven


def test_short_put_collects_premium_above_strike():
    legs = [Leg("put", "short", 36.0, 1.5)]
    assert payoff(legs, 40.0) == 150.0            # acima do strike: fica com o prêmio
    assert payoff(legs, 34.0) == -50.0            # abaixo: -(K−S) + prêmio = −(2)+1.5 = −0.5 ×100


def test_evaluate_returns_pop_ev_and_risk_on_real_density():
    legs = [Leg("call", "long", 38.0, 2.0), Leg("call", "short", 42.0, 0.8)]
    d = physical_density(spot=38.0, sigma_iv=0.30, rv=0.30, vrp=0.0, T=30 / 365)
    ev = evaluate(legs, d, spot=38.0)
    assert abs(ev["max_loss"] - (-120.0)) < 1.0          # spread de risco definido
    assert abs(ev["max_gain"] - 280.0) < 1.0
    assert 0.0 < ev["pop"] < 1.0                         # prob. de lucro entre 0 e 1
    assert ev["max_loss"] < ev["ev"] < ev["max_gain"]   # valor esperado entre os extremos
    assert len(ev["breakevens"]) >= 1                    # ao menos um breakeven


def test_evaluate_pop_matches_density_for_long_call():
    legs = [Leg("call", "long", 38.0, 2.0)]
    d = physical_density(spot=38.0, sigma_iv=0.30, rv=0.30, vrp=0.0, T=30 / 365)
    ev = evaluate(legs, d, spot=38.0)
    # POP do long call = P(S_T > breakeven=40) — bate a cauda da densidade
    import math
    p_above = 1.0 - float(d.logret_cdf(math.log(40.0 / 38.0)))
    assert abs(ev["pop"] - p_above) < 0.02
