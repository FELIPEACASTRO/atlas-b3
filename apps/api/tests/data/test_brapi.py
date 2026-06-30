import datetime as dt

from atlas_api.data.brapi import dividend_yield_from_result

ASOF = dt.date(2026, 6, 29)


def _result(price, dividends):
    return {"regularMarketPrice": price, "dividendsData": {"cashDividends": dividends}}


def test_trailing_12m_yield_sums_recent_cash_dividends():
    r = _result(40.0, [
        {"paymentDate": "2026-03-01", "rate": 1.0},
        {"paymentDate": "2025-09-01", "rate": 1.0},  # within 365d
        {"paymentDate": "2024-01-01", "rate": 5.0},  # older than 365d -> excluded
    ])
    assert abs(dividend_yield_from_result(r, ASOF) - (2.0 / 40.0)) < 1e-9


def test_no_dividends_yields_zero():
    assert dividend_yield_from_result(_result(40.0, []), ASOF) == 0.0


def test_missing_or_zero_price_returns_none():
    assert dividend_yield_from_result(_result(None, []), ASOF) is None
    assert dividend_yield_from_result(_result(0.0, []), ASOF) is None


def test_bad_dates_and_rates_are_skipped():
    r = _result(10.0, [
        {"paymentDate": None, "rate": 1.0},
        {"paymentDate": "not-a-date", "rate": 1.0},
        {"paymentDate": "2026-06-01", "rate": None},
        {"paymentDate": "2026-06-02", "rate": 0.5},  # the only valid one
    ])
    assert abs(dividend_yield_from_result(r, ASOF) - 0.05) < 1e-9


def test_yield_is_capped_against_glitches():
    # a single absurd special-dividend record must not poison q
    r = _result(1.0, [{"paymentDate": "2026-06-01", "rate": 999.0}])
    assert dividend_yield_from_result(r, ASOF) == 0.5  # _MAX_Q


def test_future_payment_dates_excluded():
    r = _result(10.0, [{"paymentDate": "2026-12-01", "rate": 1.0}])  # after asof
    assert dividend_yield_from_result(r, ASOF) == 0.0
