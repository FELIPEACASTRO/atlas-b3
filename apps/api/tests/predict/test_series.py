"""Adapter store→entradas do modelo: rolling Yang-Zhang, série RV diária, neg-returns.

Reusa rv.yang_zhang/rv.realized_vol — nunca reimplementa a fórmula (review B1).
"""
from atlas_api.predict.series import rolling_yang_zhang, rv_series, neg_return_series
from atlas_api.pricing.rv import yang_zhang


def test_rolling_yz_reuses_existing_estimator():
    ohlc = [(10 + 0.1 * i, 10.3 + 0.1 * i, 9.9 + 0.1 * i, 10.1 + 0.1 * i) for i in range(8)]
    out = rolling_yang_zhang(ohlc, window=4)
    assert len(out) == len(ohlc) - 4 + 1
    assert out[-1] == yang_zhang(ohlc[-4:])         # mesma função — sem duplicar a fórmula


def test_rv_series_prefers_yang_zhang_from_real_ohlc():
    ohlc = [(10 + 0.1 * i, 10.3 + 0.1 * i, 9.9 + 0.1 * i, 10.1 + 0.1 * i) for i in range(8)]
    s = rv_series(ohlc, window=4)
    assert s[-1] == rolling_yang_zhang(ohlc, window=4)[-1]   # usa YZ (OHLC real, ~5× mais eficiente)


def test_rv_series_gates_collapsed_bars():
    # janela DOMINADA por colapsadas (O=H=L=C) + 1 barra com range VÁLIDO: a vol real > 0
    ohlc = [(10.0, 10.0, 10.0, 10.0)] * 3 + [(10.0, 10.3, 9.9, 10.2)]
    s = rv_series(ohlc, window=4)
    assert s[-1] > 0.0


def test_rv_series_all_collapsed_is_honest_zero():
    # tudo parado: a vol REAL é 0 — reportar 0.0, NÃO fabricar
    s = rv_series([(10.0, 10.0, 10.0, 10.0)] * 5, window=4)
    assert s[-1] == 0.0


def test_neg_return_series_is_strictly_negative_indicator():
    closes = [10.0, 10.2, 10.0, 9.8, 9.9]           # alta, queda, queda, alta
    nr = neg_return_series(closes)
    assert len(nr) == len(closes) - 1
    assert all(v <= 0.0 for v in nr) and any(v < 0.0 for v in nr)   # estritamente r<0 (não r≤0)
