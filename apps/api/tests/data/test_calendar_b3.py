from datetime import date

from atlas_api.data.calendar_b3 import business_days, year_fraction


def test_business_days_excludes_weekends():
    # (Mon 2024-01-08, Fri 2024-01-12] -> Tue..Fri = 4
    assert business_days(date(2024, 1, 8), date(2024, 1, 12)) == 4


def test_business_days_excludes_b3_holidays():
    # Dec 24 and 25 2024 are B3 holidays -> only Dec 26, 27 count
    assert business_days(date(2024, 12, 23), date(2024, 12, 27)) == 2


def test_year_fraction_uses_252_basis():
    # ~13 business days between 2024-01-02 and 2024-01-19
    assert abs(year_fraction(date(2024, 1, 2), date(2024, 1, 19)) - 13 / 252) < 1e-9


def test_year_fraction_floors_at_one_day():
    assert year_fraction(date(2024, 1, 19), date(2024, 1, 19)) == 1 / 252
