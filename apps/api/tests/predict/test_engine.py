"""build_prediction: a montagem pura (adapter→forecast→densidade→conformal→auditoria)."""
import numpy as np

from atlas_api.predict.engine import build_prediction


def _synth(n=90, seed=0):
    """OHLC + closes + IV sintéticos, deterministas, com range intradiário real (não colapsado)."""
    rng = np.random.default_rng(seed)
    c_prev = 30.0
    ohlc, closes, iv = [], [], []
    for _ in range(n):
        c = c_prev * float(np.exp(rng.normal(0, 0.02)))
        o = c_prev * float(np.exp(rng.normal(0, 0.005)))
        hi = max(o, c) * float(np.exp(abs(rng.normal(0, 0.01))))
        lo = min(o, c) * float(np.exp(-abs(rng.normal(0, 0.01))))
        ohlc.append((o, hi, lo, c))
        closes.append(c)
        iv.append(0.30 + float(rng.normal(0, 0.02)))
        c_prev = c
    return ohlc, closes, iv


def test_build_prediction_shape_and_calibration():
    ohlc, closes, iv = _synth(90)
    chain = [
        {"kind": "call", "strike": 31.0, "venc": "2026-07-17", "iv": 0.30, "delta": 0.5},
        {"kind": "put", "strike": 29.0, "venc": "2026-07-17", "iv": 0.33, "delta": -0.25},
        {"kind": "call", "strike": 31.0, "venc": "2026-08-21", "iv": 0.31, "delta": 0.5},
    ]
    out = build_prediction(ticker="PETR4", ohlc=ohlc, closes=closes, iv_history=iv,
                           spot=closes[-1], chain=chain, asof="2026-06-26")
    assert out["sigma"] is not None and out["sigma"] > 0
    q = out["dist"]["quantiles"]
    assert q["p10"] < q["p50"] < q["p90"]                       # quantis monotônicos
    spot_t = next(t for t in out["dist"]["pop_targets"] if t["moneyness"] == 1.0)
    assert abs(spot_t["above"] - 0.5) < 0.05                    # POP no spot ~ 0.5 (drift 0)
    cal = out["calibration"]
    assert cal["available"] is True and cal["nominal"] == 0.8
    assert 0.6 <= cal["coverage"] <= 1.0                        # conformal ~ nominal
    assert out["market_vs_physical"]["physical"] > 0
    assert out["regime"]["regime"] != "indisponivel"           # term_slope/skew reais da cadeia
    assert "ordem" in out["note"]                              # análise, não recomendação


def test_build_prediction_insufficient_history_is_honest():
    ohlc, closes, iv = _synth(10)
    out = build_prediction(ticker="X", ohlc=ohlc, closes=closes, iv_history=iv,
                           spot=closes[-1], chain=[], asof=None)
    assert out["sigma"] is None                                 # não fabrica previsão
    assert out["calibration"]["available"] is False
