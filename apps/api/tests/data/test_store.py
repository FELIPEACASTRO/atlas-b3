from atlas_api.data import store


def test_roundtrip(tmp_path):
    db = str(tmp_path / "s.db")
    conn = store.connect(db)
    store.insert_instruments(conn, [
        ("PETR4", "acao", 38.42, 1.2, 1.2e9, None, None, None, "2024-01-02"),
        ("VALE3", "acao", 61.30, -0.8, 9.8e8, None, None, None, "2024-01-02"),
    ])
    store.insert_options(conn, [
        ("PETR4", "PETRA399", "call", 38.67, "2024-01-19", 1.36, 0.512, 0.30, 0.04, 1.5, -0.02, "2024-01-02"),
    ])
    store.set_meta(conn, "asof", "2024-01-02")
    conn.commit()

    assert store.count(conn) == 2
    assert store.get_meta(conn, "asof") == "2024-01-02"

    scr = store.query_screener(conn, tipo="acao", min_liq=1e9)
    assert [r["ticker"] for r in scr] == ["PETR4"]  # only PETR4 passes the liquidity filter

    chain = store.query_chain(conn, "PETR4")
    assert len(chain) == 1 and chain[0]["ticker"] == "PETRA399"
    conn.close()


def test_reset_preserves_price_history(tmp_path):
    db = str(tmp_path / "p.db")
    conn = store.connect(db)
    store.upsert_prices(conn, [("X", "2024-01-02", 1.0, 2.0, 0.5, 1.5)])
    store.insert_instruments(conn, [("X", "acao", 1.5, 0.0, 100.0, None, None, None, "2024-01-02")])
    store.reset(conn)
    conn.commit()
    assert store.count(conn) == 0  # the per-day snapshot is wiped
    assert len(store.price_history(conn, "X")) == 1  # but the accumulating history survives
    conn.close()


def test_reset_preserves_user_positions(tmp_path):
    # the daily re-ingest (reset) must NOT wipe the user's portfolio
    db = str(tmp_path / "pos.db")
    conn = store.connect(db)
    store.set_position(conn, "PETR4", 1000)
    store.set_position(conn, "PETRA38", -10)
    store.insert_instruments(conn, [("X", "acao", 1.5, 0.0, 100.0, None, None, None, "2024-01-02")])
    store.reset(conn)
    conn.commit()
    assert dict(store.list_positions(conn)) == {"PETR4": 1000, "PETRA38": -10}  # book intact
    conn.close()

