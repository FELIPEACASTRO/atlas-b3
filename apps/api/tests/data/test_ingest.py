import os

import pytest

from atlas_api.data import store
from atlas_api.data.ingest import _pct_change, ingest_cotahist

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "cotahist_sample.txt")


def test_pct_change_handles_missing_prior():
    assert _pct_change(37.0, 37.78) == 2.11
    assert _pct_change(None, 37.78) is None
    assert _pct_change(0.0, 37.78) is None  # no division by a zero prior


def test_ingest_var_pct_uses_prior_close_not_intraday(tmp_path):
    # var % must be day-over-day (vs prior session close), not intraday open->close (S7)
    db = str(tmp_path / "v.db")
    conn = store.connect(db)
    store.upsert_prices(conn, [("PETR4", "2020-01-01", 36.5, 37.1, 36.4, 37.0)])
    conn.commit()
    conn.close()
    ingest_cotahist(FIXTURE, db, rate=0.1165)  # fixture PETR4 close = 37.78
    conn = store.connect(db)
    assert store.get_instrument(conn, "PETR4")["var_pct"] == 2.11  # (37.78/37.0 - 1)*100
    conn.close()


def test_ingest_accepts_dividend_yield_map(tmp_path):
    # q_by_ticker must thread through without error; PETR3 gets a real yield
    db = str(tmp_path / "q.db")
    n = ingest_cotahist(FIXTURE, db, rate=0.1165, q_by_ticker={"PETR3": 0.07})
    assert n >= 3


def test_ingest_rejects_multi_date_file(tmp_path):
    line = open(FIXTURE, encoding="latin-1").read().splitlines()[0]  # date at [2:10]
    other_day = line[:2] + "20240103" + line[10:]
    p = tmp_path / "multi.txt"
    p.write_text(line + "\n" + other_day + "\n", encoding="latin-1")
    with pytest.raises(ValueError):
        ingest_cotahist(str(p), str(tmp_path / "x.db"), rate=0.1165)


def test_ingest_maps_option_to_correct_underlying_via_isin(tmp_path):
    db = str(tmp_path / "atlas.db")
    n = ingest_cotahist(FIXTURE, db, rate=0.1165)
    assert n >= 3

    conn = store.connect(db)
    tickers = {r["ticker"] for r in store.query_screener(conn)}
    assert {"PETR4", "PETR3"} <= tickers
    # PETRA274 is an option on PETR3 (ON), not PETR4 — must map via the CODISI/ISIN.
    assert any(r["ticker"] == "PETRA274" for r in store.query_chain(conn, "PETR3"))
    assert not any(r["ticker"] == "PETRA274" for r in store.query_chain(conn, "PETR4"))
    conn.close()


def test_ingest_persists_ohlc_to_history(tmp_path):
    db = str(tmp_path / "h.db")
    ingest_cotahist(FIXTURE, db, rate=0.1165)
    conn = store.connect(db)
    h = store.price_history(conn, "PETR4")
    assert len(h) == 1 and h[0][3] == 37.78  # one session persisted; close = last element
    conn.close()


def test_ingest_accumulates_history_non_destructively(tmp_path):
    # seed 2 prior PETR3 sessions; ingesting the fixture adds a 3rd -> RV becomes
    # computable. The key fix: ingest must NOT wipe the accumulated history.
    db = str(tmp_path / "rv.db")
    conn = store.connect(db)
    store.upsert_prices(conn, [
        ("PETR3", "2023-12-28", 35.0, 35.6, 34.8, 35.1),
        ("PETR3", "2023-12-29", 35.2, 36.0, 35.0, 35.9),
    ])
    conn.commit()
    conn.close()
    ingest_cotahist(FIXTURE, db, rate=0.1165)
    conn = store.connect(db)
    assert len(store.price_history(conn, "PETR3")) == 3  # 2 seeded + 1 ingested, not wiped
    conn.close()
