"""Shared seed for the chat-agent tests: a small but real store.

PETR4 (spot 38.30, IV Rank 56.6, signal 'rico') with two call series
(PETRA38 @ strike 38, PETRA40 @ strike 40), 15 sessions of closes + ATM IV so
realized vol and the IV-history window are both computable.
"""
import datetime as dt

import pytest

from atlas_api.data import store


def _seed(db: str) -> None:
    conn = store.connect(db)
    base = dt.date(2024, 1, 1)
    prices, ivs = [], []
    for i in range(15):
        d = (base + dt.timedelta(days=i)).isoformat()
        prices.append(("PETR4", d, 38.0, 38.6, 37.4, 38.0 + 0.1 * (i % 5 - 2)))
        ivs.append(("PETR4", d, 0.28 + 0.003 * i))
    store.upsert_prices(conn, prices)
    store.upsert_iv_daily(conn, ivs)
    store.insert_instruments(conn, [
        ("PETR4", "acao", 38.3, 1.2, 1e9, 0.30, "rico", 56.6, "2024-01-15"),
        ("PETRA38", "call", 1.10, None, 1e6, 0.30, None, None, "2024-01-15"),
        ("PETRA40", "call", 0.40, None, 1e6, 0.32, None, None, "2024-01-15"),
    ])
    store.insert_options(conn, [
        ("PETR4", "PETRA38", "call", 38.0, "2024-02-16", 1.10, 0.30, 0.55, 0.04, 1.5, -0.03, "2024-01-15"),
        ("PETR4", "PETRA40", "call", 40.0, "2024-02-16", 0.40, 0.32, 0.30, 0.03, 1.2, -0.02, "2024-01-15"),
    ])
    store.insert_features(conn, [("PETR4", 0.07, 0.9, 0.02, "2024-01-15")])
    store.set_meta(conn, "asof", "2024-01-15")
    conn.commit()
    conn.close()


@pytest.fixture
def seeded_db(tmp_path) -> str:
    db = str(tmp_path / "atlas.db")
    _seed(db)
    return db


@pytest.fixture
def conn(seeded_db):
    c = store.connect(seeded_db)
    yield c
    c.close()
