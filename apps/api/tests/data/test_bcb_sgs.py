import pytest

from atlas_api.data.bcb_sgs import parse_latest


def test_parse_latest_converts_percent_to_fraction():
    payload = [{"data": "01/06/2026", "valor": "10.40"}]
    assert abs(parse_latest(payload) - 0.104) < 1e-9


def test_parse_latest_uses_last_value():
    payload = [{"data": "01/06/2026", "valor": "9.0"}, {"data": "02/06/2026", "valor": "10.5"}]
    assert abs(parse_latest(payload) - 0.105) < 1e-9


def test_parse_latest_empty_raises():
    with pytest.raises(ValueError):
        parse_latest([])
