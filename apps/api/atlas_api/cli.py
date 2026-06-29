"""CLI to populate the local store from REAL B3 COTAHIST files (no mocks).

From apps/api, with the venv's python:
  python -m atlas_api.cli ingest --date 02012024 --date 03012024
  python -m atlas_api.cli ingest --file /path/COTAHIST_Dxxxx.TXT
  python -m atlas_api.cli ingest --date 02012024 --rate 0.1165   # historical backfill

Downloads each daily COTAHIST zip from B3, unzips, and ingests in the order
given (chronological for a correct realized-vol series). Writes to --db (default
ATLAS_DB env or data_cache/atlas.db) — the same DB the API reads.
"""
from __future__ import annotations

import argparse
import io
import os
import urllib.request
import zipfile

from atlas_api.data.ingest import ingest_cotahist

_URL = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_D{date}.ZIP"


def download_cotahist(date: str, dest_dir: str) -> str:
    """Download + unzip the daily COTAHIST for DDMMYYYY; return the .TXT path."""
    req = urllib.request.Request(_URL.format(date=date), headers={"User-Agent": "atlas/0.1"})
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 (trusted B3 host)
        blob = resp.read()
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        name = next(n for n in zf.namelist() if n.upper().endswith(".TXT"))
        zf.extract(name, dest_dir)
    return os.path.join(dest_dir, name)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="atlas")
    sub = parser.add_subparsers(dest="cmd", required=True)
    ing = sub.add_parser("ingest", help="download/ingest COTAHIST days into the local store")
    ing.add_argument("--date", action="append", default=[], help="DDMMYYYY (repeatable)")
    ing.add_argument("--file", action="append", default=[], help="local COTAHIST .TXT (repeatable)")
    ing.add_argument("--db", default=os.environ.get("ATLAS_DB", "data_cache/atlas.db"))
    ing.add_argument("--cache", default="data_cache/cotahist")
    ing.add_argument("--rate", type=float, default=None, help="risk-free override (else live BCB-SGS)")
    args = parser.parse_args(argv)

    if os.path.dirname(args.db):
        os.makedirs(os.path.dirname(args.db), exist_ok=True)
    os.makedirs(args.cache, exist_ok=True)

    files = list(args.file)
    for d in args.date:
        print(f"baixando COTAHIST {d} ...")
        files.append(download_cotahist(d, args.cache))
    for path in files:
        total = ingest_cotahist(path, args.db, rate=args.rate)
        print(f"ingerido {os.path.basename(path)} -> {total} instrumentos | db={args.db}")


if __name__ == "__main__":
    main()
