import pytest

from atlas_api.data.curve import rate_for

CURVE = [(21, 0.105), (63, 0.108), (126, 0.110), (252, 0.112)]


def test_exact_point():
    assert rate_for(CURVE, 63) == 0.108


def test_interpolates_between():
    r = rate_for(CURVE, 42)  # midpoint of 21..63
    assert 0.105 < r < 0.108
    assert abs(r - 0.1065) < 1e-9


def test_flat_extrapolation():
    assert rate_for(CURVE, 1) == 0.105
    assert rate_for(CURVE, 999) == 0.112


def test_empty_curve_raises():
    with pytest.raises(ValueError):
        rate_for([], 30)
