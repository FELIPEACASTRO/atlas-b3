"""CLI to populate the local store from REAL B3 COTAHIST files (no mocks).

From apps/api, with the venv's python:
  python -m atlas_api.cli ingest --date 02012024 --date 03012024
  python -m atlas_api.cli ingest --file /path/COTAHIST_Dxxxx.TXT
  python -m atlas_api.cli backfill --sessions 120     # last 120 trading days -> now
  python -m atlas_api.cli backfill --to 26062026 --sessions 252

`ingest` downloads/ingests specific days (full chain). `backfill` walks back from
--to over trading days (skipping holidays via 404), ingests history light
(OHLC + ATM IV per underlying) for all but the most recent day, then ingests the
most recent day in full — so IV Rank / RV / charts get real depth while only the
current snapshot carries the whole chain. Writes to --db (default ATLAS_DB env or
data_cache/atlas.db), the same DB the API reads.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import os
import urllib.error
import urllib.request
import zipfile

from atlas_api.data.bcb_sgs import fetch_annual_rate
from atlas_api.data.brapi import fetch_dividend_yields
from atlas_api.data.ingest import ingest_cotahist, ingest_history

_URL = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_D{date}.ZIP"
_DEFAULT_RATE = 0.1165

# B3 option liquidity concentrates here; brapi serves PETR4/VALE3/ITUB4/MGLU3 free,
# the rest need BRAPI_TOKEN. Failures are skipped (q falls back to 0), so a long
# list is harmless offline.
_LIQUID_UNDERLYINGS = [
    "PETR4", "VALE3", "ITUB4", "MGLU3", "BBAS3", "BBDC4", "BOVA11",
    "B3SA3", "ABEV3", "PRIO3", "ITSA4", "PETR3", "VALE5", "WEGE3",
]


def download_cotahist(date: str, dest_dir: str) -> str:
    """Download + unzip the daily COTAHIST for DDMMYYYY; return the .TXT path.

    Skips the download if the .TXT is already cached (the file name is the
    predictable COTAHIST_D{date}.TXT) — makes a re-backfill fast.
    """
    cached = os.path.join(dest_dir, f"COTAHIST_D{date}.TXT")
    if os.path.exists(cached) and os.path.getsize(cached) > 0:
        return cached
    req = urllib.request.Request(_URL.format(date=date), headers={"User-Agent": "atlas/0.1"})
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 (trusted B3 host)
        blob = resp.read()
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        name = next(n for n in zf.namelist() if n.upper().endswith(".TXT"))
        zf.extract(name, dest_dir)
    return os.path.join(dest_dir, name)


def _discover_sessions(to_date: dt.date, sessions: int, cache: str) -> list[tuple[dt.date, str]]:
    """Walk back from to_date over weekdays, downloading each existing daily file.

    A 404 means a non-trading day (holiday) — skipped. Returns (date, txt_path)
    oldest-first. Stops after collecting ``sessions`` files or scanning ~2x that
    many calendar days (safety against an unbounded loop).
    """
    found: list[tuple[dt.date, str]] = []
    d = to_date
    scanned = 0
    while len(found) < sessions and scanned < sessions * 2 + 30:
        scanned += 1
        if d.weekday() < 5:  # Mon-Fri
            ds = d.strftime("%d%m%Y")
            for attempt in range(2):  # one retry: B3 occasionally times out
                try:
                    found.append((d, download_cotahist(ds, cache)))
                    break
                except urllib.error.HTTPError:
                    break  # 404 -> holiday / not published, no point retrying
                except Exception:  # noqa: BLE001 — timeout/conn/zip: best-effort, skip on persistent failure
                    if attempt == 1:
                        print(f"  (pulando {d}: download falhou)")
        d -= dt.timedelta(days=1)
    return list(reversed(found))


def _cmd_ingest(args) -> None:
    q_by_ticker: dict[str, float] = {}
    if not args.no_dividends:
        q_asof = max((dt.datetime.strptime(d, "%d%m%Y").date() for d in args.date), default=None)
        q_by_ticker = fetch_dividend_yields(_LIQUID_UNDERLYINGS, asof=q_asof)
        print(f"dividend yields (brapi, asof={q_asof or 'today'}): {len(q_by_ticker)} tickers")

    files = list(args.file)
    for d in args.date:
        print(f"baixando COTAHIST {d} ...")
        files.append(download_cotahist(d, args.cache))
    for path in files:
        total = ingest_cotahist(path, args.db, rate=args.rate, q_by_ticker=q_by_ticker)
        print(f"ingerido {os.path.basename(path)} -> {total} instrumentos | db={args.db}")


def _cmd_update(args) -> None:
    """Daily job: ingest the latest available trading day (full chain)."""
    days = _discover_sessions(dt.date.today(), 1, args.cache)
    if not days:
        print("nenhum pregão disponível (B3 fora do ar ou ainda não publicado)")
        return
    d, path = days[0]
    rate = args.rate or fetch_annual_rate() or _DEFAULT_RATE
    q_by_ticker = fetch_dividend_yields(_LIQUID_UNDERLYINGS, asof=d)
    total = ingest_cotahist(path, args.db, rate=rate, q_by_ticker=q_by_ticker)
    print(f"atualizado {d} -> {total} instrumentos | db={args.db}")


def _cmd_backfill(args) -> None:
    to_date = dt.datetime.strptime(args.to, "%d%m%Y").date() if args.to else dt.date.today()
    print(f"descobrindo até {args.sessions} pregões até {to_date} ...")
    days = _discover_sessions(to_date, args.sessions, args.cache)
    if not days:
        print("nenhum pregão encontrado (B3 fora do ar ou datas inválidas)")
        return
    rate = args.rate or fetch_annual_rate() or _DEFAULT_RATE
    q_by_ticker = fetch_dividend_yields(_LIQUID_UNDERLYINGS, asof=days[-1][0])
    print(f"{len(days)} pregões: {days[0][0]} -> {days[-1][0]} | rate={rate:.4f} | q={len(q_by_ticker)} tickers")
    for i, (d, path) in enumerate(days):
        last = i == len(days) - 1
        if last:
            total = ingest_cotahist(path, args.db, rate=rate, q_by_ticker=q_by_ticker)
            print(f"  [{i+1}/{len(days)}] {d} FULL -> {total} instrumentos")
        else:
            n = ingest_history(path, args.db, rate=rate, q_by_ticker=q_by_ticker)
            print(f"  [{i+1}/{len(days)}] {d} hist -> {n} subjacentes c/ IV ATM")
    print(f"backfill completo: {len(days)} pregões em {args.db}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="atlas")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ing = sub.add_parser("ingest", help="download/ingest specific COTAHIST days (full chain)")
    ing.add_argument("--date", action="append", default=[], help="DDMMYYYY (repeatable)")
    ing.add_argument("--file", action="append", default=[], help="local COTAHIST .TXT (repeatable)")
    ing.add_argument("--db", default=os.environ.get("ATLAS_DB", "data_cache/atlas.db"))
    ing.add_argument("--cache", default="data_cache/cotahist")
    ing.add_argument("--rate", type=float, default=None, help="risk-free override (else live BCB-SGS)")
    ing.add_argument("--no-dividends", action="store_true", help="skip brapi dividend-yield (q) fetch")

    up = sub.add_parser("update", help="daily job: ingest the latest available trading day (full)")
    up.add_argument("--db", default=os.environ.get("ATLAS_DB", "data_cache/atlas.db"))
    up.add_argument("--cache", default="data_cache/cotahist")
    up.add_argument("--rate", type=float, default=None, help="risk-free override (else live BCB-SGS)")

    bf = sub.add_parser("backfill", help="backfill N recent trading days (history light + latest full)")
    bf.add_argument("--to", default=None, help="end date DDMMYYYY (default: today)")
    bf.add_argument("--sessions", type=int, default=120, help="number of trading days to load")
    bf.add_argument("--db", default=os.environ.get("ATLAS_DB", "data_cache/atlas.db"))
    bf.add_argument("--cache", default="data_cache/cotahist")
    bf.add_argument("--rate", type=float, default=None, help="risk-free override (else live BCB-SGS)")

    args = parser.parse_args(argv)
    if os.path.dirname(args.db):
        os.makedirs(os.path.dirname(args.db), exist_ok=True)
    os.makedirs(args.cache, exist_ok=True)

    if args.cmd == "ingest":
        _cmd_ingest(args)
    elif args.cmd == "update":
        _cmd_update(args)
    elif args.cmd == "backfill":
        _cmd_backfill(args)


if __name__ == "__main__":
    main()
