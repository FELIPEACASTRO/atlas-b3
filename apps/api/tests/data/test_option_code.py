from atlas_api.data.option_code import code_consistent, parse_option_code


def test_parse_call_january():
    assert parse_option_code("PETRA274") == {"root": "PETR", "kind": "call", "month": 1}


def test_parse_put_january():
    assert parse_option_code("VALEM55") == {"root": "VALE", "kind": "put", "month": 1}


def test_parse_call_december():
    # 'L' is the December call letter
    assert parse_option_code("BBASL30")["month"] == 12


def test_unparseable_returns_none():
    assert parse_option_code("PE") is None


def test_consistent_when_kind_and_month_match():
    assert code_consistent("PETRA274", "call", 1) is True


def test_inconsistent_kind_is_rejected():
    # 'A' is a call letter; labeling it a put is a contradiction
    assert code_consistent("PETRA274", "put", 1) is False


def test_inconsistent_month_is_rejected():
    assert code_consistent("PETRA274", "call", 7) is False


def test_unparseable_is_permissive():
    assert code_consistent("XY", "call", 3) is True
