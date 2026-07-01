"""O 'porquê' humano de cada estratégia — explica a tese, a relação vol implícita×física e o risco."""
from atlas_api.predict.strategies import rationale


def test_rationale_explains_selling_when_vol_rich():
    s = {"thesis": "alta", "vol_stance": "vender", "pop": 0.86, "ev": 825.0, "defined_risk": True}
    txt = rationale(s, market_iv=0.30, physical=0.23)
    assert "86%" in txt
    assert "vend" in txt.lower()                 # vende prêmio
    assert "acima" in txt.lower()                # vol implícita acima da física (cara)


def test_rationale_warns_when_buying_rich_vol():
    s = {"thesis": "alta", "vol_stance": "comprar", "pop": 0.27, "ev": -659.0, "defined_risk": False}
    txt = rationale(s, market_iv=0.30, physical=0.23)
    assert "compra" in txt.lower()
    assert "negativ" in txt.lower()              # EV desfavorável sob nossa densidade


def test_rationale_flags_unlimited_risk():
    s = {"thesis": "neutro", "vol_stance": "vender", "pop": 0.83, "ev": 500.0, "defined_risk": False}
    txt = rationale(s, market_iv=0.30, physical=0.25)
    assert "ilimitado" in txt.lower()


def test_rationale_handles_missing_market_vol():
    s = {"thesis": "baixa", "vol_stance": "comprar", "pop": 0.4, "ev": 10.0, "defined_risk": True}
    txt = rationale(s, market_iv=None, physical=0.25)
    assert isinstance(txt, str) and len(txt) > 10   # não quebra sem IV
