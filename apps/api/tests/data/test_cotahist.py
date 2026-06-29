import os
from datetime import date

from atlas_api.data.cotahist import parse_file, parse_line

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "cotahist_sample.txt")


def _lines() -> list[str]:
    with open(FIXTURE, encoding="latin-1") as f:
        return [ln.rstrip("\r\n") for ln in f]


def test_parse_real_stock_line():
    line = next(ln for ln in _lines() if ln[24:27] == "010")
    q = parse_line(line)
    assert q.ticker == "PETR4"
    assert q.tipo == "acao"
    assert q.preco_ult == 37.78
    assert q.strike is None
    assert q.venc is None
    assert q.data == date(2024, 1, 2)
    assert q.negocios == 39280


def test_parse_real_option_line():
    line = next(ln for ln in _lines() if ln[24:27] in ("070", "080"))
    q = parse_line(line)
    assert q.tipo == "call"
    assert q.strike == 26.17
    assert q.venc == date(2024, 1, 19)
    assert q.preco_ult == 13.33


def test_parse_file_returns_traded_quotes():
    quotes = parse_file(FIXTURE)
    assert len(quotes) == 2
    assert {q.ticker for q in quotes} == {"PETR4", "PETRA274"}
