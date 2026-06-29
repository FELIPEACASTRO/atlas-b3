import os

import pytest

from atlas_api.data import store
from atlas_api.data.ingest import ingest_cotahist

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "cotahist_sample.txt")


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
