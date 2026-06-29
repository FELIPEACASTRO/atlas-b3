"""COTAHIST (B3 EOD) fixed-width parser — 245-byte records, latin-1.

Column offsets verified against a real daily file (COTAHIST_D02012024). Prices
are V99 (the last two digits are decimals). Options carry a strike (PREEXE) and
expiry (DATVEN); stocks have strike 0 and the sentinel expiry 99991231.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

_TPMERC = {"010": "acao", "070": "call", "080": "put"}


@dataclass
class Quote:
    data: date
    ticker: str
    tipo: str  # acao | call | put | outro
    preco_ult: float
    preco_ofc: float  # best bid
    preco_ofv: float  # best ask
    strike: float | None
    venc: date | None
    volume: float
    negocios: int


def _opt_date(s: str) -> date | None:
    if s == "99991231" or not s.strip():
        return None
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def parse_line(line: str) -> Quote:
    tipo = _TPMERC.get(line[24:27], "outro")
    is_opt = tipo in ("call", "put")
    return Quote(
        data=date(int(line[2:6]), int(line[6:8]), int(line[8:10])),
        ticker=line[12:24].strip(),
        tipo=tipo,
        preco_ult=int(line[108:121]) / 100,
        preco_ofc=int(line[121:134]) / 100,
        preco_ofv=int(line[134:147]) / 100,
        strike=(int(line[188:201]) / 100) if is_opt else None,
        venc=_opt_date(line[202:210]) if is_opt else None,
        volume=int(line[170:188]) / 100,
        negocios=int(line[147:152]),
    )


def parse_file(path: str, *, only_traded: bool = True) -> list[Quote]:
    """Parse a COTAHIST .TXT into quotes.

    Skips header/trailer, keeps only equities/options (drops other markets),
    and — by default — drops rows with zero trades, since their ``preco_ult`` is
    a stale last-trade that would poison any IV computed from it (spec §6).
    """
    quotes: list[Quote] = []
    with open(path, encoding="latin-1") as fh:
        for raw in fh:
            line = raw.rstrip("\r\n")
            if len(line) < 245 or line[:2] != "01":
                continue
            quote = parse_line(line)
            if quote.tipo == "outro":
                continue
            if only_traded and quote.negocios == 0:
                continue
            quotes.append(quote)
    return quotes
