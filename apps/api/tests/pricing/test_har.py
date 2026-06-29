import math

import pytest

from atlas_api.pricing.har import _solve, fit_har, forecast_har


def test_solve_known_system():
    # 2x + y = 5 ; x + 3y = 10  ->  x=1, y=3
    sol = _solve([[2.0, 1.0], [1.0, 3.0]], [5.0, 10.0])
    assert abs(sol[0] - 1.0) < 1e-9
    assert abs(sol[1] - 3.0) < 1e-9


def test_fit_har_returns_four_coeffs_and_finite_forecast():
    rv = [0.2 + 0.08 * math.sin(i / 2.0) + 0.03 * math.cos(i / 5.0) + 0.01 * (i % 7) for i in range(150)]
    coef = fit_har(rv)
    assert len(coef) == 4
    assert math.isfinite(forecast_har(coef, rv))


def test_not_enough_data_raises():
    with pytest.raises(ValueError):
        fit_har([0.1, 0.2, 0.3])


def test_fit_har_rejects_nan_input():
    rv = [0.2] * 30 + [float("nan")] + [0.2] * 30
    with pytest.raises(ValueError):
        fit_har(rv)
