"""HAR-Leverage forecaster + ensemble por média simples.

Reduz exatamente ao HAR quando não há leverage (coluna zerada desacopla o sistema).
"""
import pytest

from atlas_api.predict.forecast import VolForecast, har_leverage, vol_ensemble
from atlas_api.pricing.har import fit_har, forecast_har


def test_har_leverage_reduces_to_har_when_no_leverage():
    rv = [0.2, 0.21, 0.19, 0.22, 0.2, 0.23, 0.21] * 5
    base, lev = har_leverage(rv, neg_returns=[0.0] * len(rv))
    assert base == forecast_har(fit_har(rv), rv)              # base é o HAR puro
    assert abs(lev - forecast_har(fit_har(rv), rv)) < 1e-6    # leverage zerado => idêntico ao HAR


def test_har_leverage_lifts_forecast_when_recent_drop():
    # vol que SOBE após retorno negativo: o termo de leverage deve elevar a previsão
    rv = [0.18, 0.19, 0.18, 0.20, 0.30, 0.32, 0.31] * 5
    neg = [0.0] * len(rv)
    neg[-2] = -0.05                                           # queda recente
    base, lev = har_leverage(rv, neg_returns=neg)
    assert lev != base                                       # o leverage moveu a previsão


def test_ensemble_is_simple_average():
    assert vol_ensemble([0.2, 0.3, 0.4]) == 0.30
    assert vol_ensemble([0.25]) == 0.25


def test_volforecast_holds_band_invariant():
    f = VolForecast(sigma=0.20, lo=0.15, hi=0.25)
    assert f.sigma > 0 and f.lo < f.sigma < f.hi
    with pytest.raises(ValueError):
        VolForecast(sigma=0.20, lo=0.25, hi=0.15)            # lo>hi é incoerente
