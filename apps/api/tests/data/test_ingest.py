import os

from atlas_api.data import store
from atlas_api.data.ingest import ingest_cotahist

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "cotahist_sample.txt")


def test_ingest_fixture_writes_enriched_rows(tmp_path):
    db = str(tmp_path / "atlas.db")
    n = ingest_cotahist(FIXTURE, db)
    assert n >= 2

    conn = store.connect(db)
    tickers = {r["ticker"] for r in store.query_screener(conn)}
    assert "PETR4" in tickers

    chain = store.query_chain(conn, "PETR4")
    # PETRA274 is a (deep-ITM) call on PETR4; it should be mapped to the underlying
    assert any(r["ticker"] == "PETRA274" for r in chain)
    conn.close()
