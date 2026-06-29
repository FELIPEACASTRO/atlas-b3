import os
from datetime import date

from atlas_api.data.cotahist import parse_file, parse_line

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "cotahist_sample.txt")


def _lines() -> list[str]:
    with open(FIXTURE, encoding="latin-1") as f:
        return [ln.rstrip("\r\n") for ln in f]


def test_parse_real_stock_line():
    line = next(ln for ln in _lines() if ln[24:27] == "010" and ln[12:24].strip() == "PETR4")
    q = parse_line(line)
    assert q.ticker == "PETR4"
    assert q.tipo == "acao"
    assert q.preco_ult == 37.78
    assert q.strike is None
    assert q.venc is None
    assert q.data == date(2024, 1, 2)
    assert q.negocios == 39280
    assert q.isin == "BRPETRACNPR6"  # PETR4 (PN)


def test_parse_real_option_line():
    line = next(ln for ln in _lines() if ln[24:27] in ("070", "080"))
    q = parse_line(line)
    assert q.tipo == "call"
    assert q.strike == 26.17
    assert q.venc == date(2024, 1, 19)
    assert q.preco_ult == 13.33
    # the option carries the UNDERLYING's ISIN (PETR3 ON), not its own
    assert q.isin == "BRPETRACNOR9"


def test_parse_file_returns_traded_quotes():
    assert {q.ticker for q in parse_file(FIXTURE)} == {"PETR4", "PETR3", "PETRA274"}


def test_parse_file_skips_malformed_line(tmp_path):
    good = open(FIXTURE, encoding="latin-1").read().splitlines()
    bad = "01" + "X" * 243  # 245 chars, data-row prefix, but non-numeric fields
    p = tmp_path / "f.txt"
    p.write_text("\n".join(good + [bad]) + "\n", encoding="latin-1")
    assert len(parse_file(str(p))) == 3  # malformed skipped, the 3 good rows survive
