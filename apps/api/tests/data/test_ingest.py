import os

from atlas_api.data import store
from atlas_api.data.ingest import ingest_cotahist

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "cotahist_sample.txt")


def test_ingest_maps_option_to_correct_underlying_via_isin(tmp_path):
    db = str(tmp_path / "atlas.db")
    n = ingest_cotahist(FIXTURE, db)
    assert n >= 3

    conn = store.connect(db)
    tickers = {r["ticker"] for r in store.query_screener(conn)}
    assert {"PETR4", "PETR3"} <= tickers
    # PETRA274 is an option on PETR3 (ON), not PETR4 — must map via the CODISI/ISIN,
    # not the root+suffix heuristic (which wrongly picked PETR4).
    assert any(r["ticker"] == "PETRA274" for r in store.query_chain(conn, "PETR3"))
    assert not any(r["ticker"] == "PETRA274" for r in store.query_chain(conn, "PETR4"))
    conn.close()
