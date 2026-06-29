# ATLAS Terminal B3 — v1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build v1 of ATLAS — an EOD decision-support terminal for B3 (ações + opções + derivativos): a Python data/quant backend that ingests COTAHIST and computes IV/greeks/RV, exposed via FastAPI, and a Next.js terminal UI (shell + screener + options desk) consuming it.

**Architecture:** Monorepo with two independent subsystems. `apps/api` (Python/FastAPI) owns all data + quant; it produces a typed JSON contract. `apps/web` (Next.js/TS) owns the UI and never does quant — it renders the contract. A shared JSON schema (`packages/contract`) lets the web app develop against fixtures before the API is wired. Data is EOD, cached in DuckDB/Parquet, refreshed daily.

**Tech Stack:** Python 3.11+ (FastAPI, polars, numpy, scipy, duckdb, pytest, ruff); Next.js + TypeScript (shadcn/Radix, TanStack Table/Query, cmdk, lightweight-charts, visx, Tremor, Motion, next-themes, Tailwind v4).

**Reference spec:** `docs/superpowers/specs/2026-06-29-atlas-terminal-b3-design.md`

---

## Scope & build order

This plan delivers **two independently testable subsystems**. Recommended order:

1. **Backend (Chunks 0–5)** — riskiest part (data quality, IV correctness). Build and validate first; it de-risks the whole product (this is also the cheap "Gate A" reality check: building COTAHIST→IV reveals data quality early).
2. **Frontend (Chunks 6–7)** — can start in parallel against the typed contract fixtures, then wire to the live API.

A separate, expanded frontend plan (`2026-06-29-atlas-frontend.md`) should be written before Chunk 6 if the team builds frontend-first; the chunks here are sufficient to start.

---

## File structure

```
apps/api/
  atlas_api/
    data/
      cotahist.py        # parse COTAHIST fixed-width → typed records
      curve.py           # pré-DI curve loader + interpolation
      corp_actions.py    # provento strike adjustment (FatorPROPSTRIKE)
      store.py           # DuckDB/Parquet point-in-time store
    pricing/
      bs.py              # Black-Scholes price + greeks (European)
      iv.py              # IV solver (bracket+brent, NaN-safe, vega clamp)
      rv.py              # realized vol (close-to-close, HAR components)
      signal.py          # IV-vs-RV classifier (rico/barato/neutro)
    api/
      main.py            # FastAPI app
      routes_screener.py
      routes_chain.py
    models.py            # pydantic contract models
  tests/
    data/ pricing/ api/  # mirrors source
  pyproject.toml
packages/contract/
  schema.json            # JSON schema shared with web
  fixtures/              # sample payloads for web dev
apps/web/
  app/                   # Next.js App Router
  components/
  lib/
  styles/tokens.css      # OKLCH design tokens
  tailwind.config.ts
docs/superpowers/...
```

---

## Chunk 0: Monorepo scaffold & tooling

### Task 0.1: Initialize repo and Python project

**Files:**
- Create: `apps/api/pyproject.toml`, `apps/api/atlas_api/__init__.py`, `apps/api/tests/__init__.py`

- [ ] **Step 1: Init git (repo is not yet a git repo)**

Run:
```bash
git init && printf "node_modules/\n.venv/\n__pycache__/\n*.parquet\n.duckdb\n.next/\ndata_cache/\n" > .gitignore
```

- [ ] **Step 2: Create `apps/api/pyproject.toml`**

```toml
[project]
name = "atlas-api"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["fastapi", "uvicorn", "polars", "numpy", "scipy", "duckdb", "pydantic", "httpx"]

[project.optional-dependencies]
dev = ["pytest", "ruff", "pytest-cov"]

[tool.ruff]
line-length = 100

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Create venv and install**

Run:
```bash
cd apps/api && python -m venv .venv && . .venv/Scripts/activate && pip install -e ".[dev]"
```
Expected: install succeeds; `pytest --version` works.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "chore: scaffold monorepo and python api project"
```

### Task 0.2: Scaffold Next.js app

- [ ] **Step 1: Create the app**

Run:
```bash
npx create-next-app@latest apps/web --ts --tailwind --app --eslint --use-npm --no-src-dir
```
Expected: `apps/web` created; `npm --prefix apps/web run dev` serves on :3000.

- [ ] **Step 2: Install UI deps**

Run:
```bash
npm --prefix apps/web i @tanstack/react-table @tanstack/react-query cmdk lightweight-charts @visx/visx motion next-themes lucide-react @tabler/icons-react
```

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "chore: scaffold next.js web app with ui deps"
```

---

## Chunk 1: COTAHIST ingestion

COTAHIST is a fixed-width EOD file. Options are `TPMERC` 070 (call) / 080 (put); strike at cols 189–201 (÷100), expiry `DATVEN` cols 203–210. We parse into typed records and filter junk.

### Task 1.1: Parse a COTAHIST record line

**Files:**
- Create: `apps/api/atlas_api/data/cotahist.py`
- Test: `apps/api/tests/data/test_cotahist.py`

- [ ] **Step 1: Write the failing test**

```python
from atlas_api.data.cotahist import parse_line, Quote

SAMPLE = (
    "012019010202PETR4       010PETROBRAS   PN      "
    .ljust(56)
    + "0000000002842" .rjust(0)  # placeholder; real fixture below
)

def test_parse_line_extracts_ticker_price_and_type():
    # Use a real 245-byte COTAHIST line fixture stored in tests/data/fixtures/cotahist_line.txt
    with open("tests/data/fixtures/cotahist_line.txt", "r", encoding="latin-1") as f:
        line = f.readline().rstrip("\n")
    q = parse_line(line)
    assert isinstance(q, Quote)
    assert q.ticker == "PETR4"
    assert q.tipo == "acao"
    assert q.preco_ult > 0
    assert q.data.year == 2026
```

- [ ] **Step 2: Add a real fixture line**

Create `apps/api/tests/data/fixtures/cotahist_line.txt` with one real 245-char COTAHIST quote line for PETR4 (download a sample from B3 Séries Históricas and copy one line). Add a second line for a PETR4 call option (`TPMERC` 070).

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/data/test_cotahist.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 4: Implement `parse_line`**

```python
from dataclasses import dataclass
from datetime import date

@dataclass
class Quote:
    data: date
    ticker: str
    tipo: str            # "acao" | "call" | "put" | "outro"
    preco_ult: float
    preco_ofc: float     # melhor oferta compra
    preco_ofv: float     # melhor oferta venda
    strike: float | None
    venc: date | None
    volume: float
    negocios: int

_TPMERC = {"010": "acao", "070": "call", "080": "put"}

def _d(s: str) -> date:
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))

def parse_line(line: str) -> Quote:
    tpmerc = line[24:27]
    tipo = _TPMERC.get(tpmerc, "outro")
    strike = int(line[188:201]) / 100 if tipo in ("call", "put") else None
    venc = _d(line[202:210]) if tipo in ("call", "put") else None
    return Quote(
        data=_d(line[2:10]),
        ticker=line[12:24].strip(),
        tipo=tipo,
        preco_ult=int(line[108:121]) / 100,
        preco_ofc=int(line[188+0:0]) if False else int(line[197:210]) / 100,  # adjust to layout
        preco_ofv=int(line[210:223]) / 100,
        strike=strike,
        venc=venc,
        volume=int(line[170:188]) / 100,
        negocios=int(line[147:152]),
    )
```

> NOTE for implementer: the exact column offsets MUST be verified against the official B3 layout PDF (`SeriesHistoricas_Layout.pdf`). The test with the real fixture line is the source of truth — adjust slices until it passes. Do not trust these offsets blindly.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/data/test_cotahist.py -v` → PASS

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(data): parse COTAHIST quote lines"
```

### Task 1.2: Parse a full file with junk filtering

- [ ] **Step 1: Failing test** — `parse_file(path)` returns only data lines (skip header `00`/trailer `99`), and drops options with `negocios == 0` (stale/never-traded).
- [ ] **Step 2: Run, fail.**
- [ ] **Step 3: Implement** `parse_file` using polars for speed; filter `tipo != "outro"`, `negocios > 0` for options.
- [ ] **Step 4: Run, pass.**
- [ ] **Step 5: Commit** `feat(data): parse full COTAHIST file with stale filtering`.

---

## Chunk 2: Risk-free curve + corporate-action strike adjustment

### Task 2.1: pré-DI curve with interpolation

**Files:** Create `apps/api/atlas_api/data/curve.py`; Test `tests/data/test_curve.py`

- [ ] **Step 1: Failing test** — `rate_for(curve, du)` interpolates (flat-forward, base 252) and a known point returns its exact rate; an interpolated point lies between neighbors.
- [ ] **Step 2: Run, fail.**
- [ ] **Step 3: Implement** loader (accepts a list of `(du, rate)`) + log-linear/flat-forward interpolation on 252-business-day basis.
- [ ] **Step 4: Run, pass.**
- [ ] **Step 5: Commit** `feat(data): pré-DI curve interpolation`.

### Task 2.2: Strike adjustment by cash proventos (the silent-bug guard)

**Files:** Create `apps/api/atlas_api/data/corp_actions.py`; Test `tests/data/test_corp_actions.py`

- [ ] **Step 1: Write the failing test**

```python
from atlas_api.data.corp_actions import adjust_strike

def test_strike_reduced_by_cash_dividend_factor():
    # B3 multiplies strike by FatorPROPSTRIKE on ex-date for cash events.
    raw_strike = 38.00
    factor = 0.9742  # example provento factor
    assert abs(adjust_strike(raw_strike, factor) - 37.02) < 0.01

def test_no_adjustment_when_factor_is_one():
    assert adjust_strike(38.00, 1.0) == 38.00
```

- [ ] **Step 2: Run, fail.**
- [ ] **Step 3: Implement**

```python
def adjust_strike(strike: float, fator_prop_strike: float) -> float:
    return round(strike * fator_prop_strike, 2)
```

- [ ] **Step 4: Run, pass.**
- [ ] **Step 5: Commit** `feat(data): provento strike adjustment guard`.

---

## Chunk 3: Pricing engine (IV + greeks)

### Task 3.1: Black-Scholes price + greeks (European)

**Files:** Create `apps/api/atlas_api/pricing/bs.py`; Test `tests/pricing/test_bs.py`

- [ ] **Step 1: Write the failing test** (known textbook values)

```python
import math
from atlas_api.pricing.bs import bs_price, bs_greeks

def test_bs_call_known_value():
    # S=100,K=100,r=0.05,q=0,T=1,sigma=0.2 -> call ~10.4506
    p = bs_price("call", 100, 100, 0.05, 0.0, 1.0, 0.20)
    assert abs(p - 10.4506) < 1e-3

def test_bs_put_call_parity():
    c = bs_price("call", 100, 95, 0.05, 0.0, 0.5, 0.25)
    p = bs_price("put", 100, 95, 0.05, 0.0, 0.5, 0.25)
    assert abs((c - p) - (100 - 95*math.exp(-0.05*0.5))) < 1e-6

def test_delta_in_range():
    g = bs_greeks("call", 100, 100, 0.05, 0.0, 1.0, 0.20)
    assert 0 < g["delta"] < 1
```

- [ ] **Step 2: Run, fail.**
- [ ] **Step 3: Implement** `bs_price` and `bs_greeks` (delta, gamma, vega, theta, rho) with continuous dividend yield `q`. Use `scipy.stats.norm`.
- [ ] **Step 4: Run, pass.**
- [ ] **Step 5: Commit** `feat(pricing): black-scholes price and greeks`.

### Task 3.2: IV solver (NaN-safe, vega-clamped)

**Files:** Create `apps/api/atlas_api/pricing/iv.py`; Test `tests/pricing/test_iv.py`

- [ ] **Step 1: Write the failing test**

```python
import math
from atlas_api.pricing.bs import bs_price
from atlas_api.pricing.iv import implied_vol

def test_iv_recovers_sigma():
    price = bs_price("call", 100, 100, 0.05, 0.0, 1.0, 0.20)
    iv = implied_vol("call", price, 100, 100, 0.05, 0.0, 1.0)
    assert abs(iv - 0.20) < 1e-4

def test_iv_returns_nan_below_intrinsic():
    # price below intrinsic has no root
    iv = implied_vol("call", 0.01, 100, 50, 0.05, 0.0, 1.0)
    assert math.isnan(iv)
```

- [ ] **Step 2: Run, fail.**
- [ ] **Step 3: Implement** using `scipy.optimize.brentq` with a bracket `[1e-4, 5.0]`; before solving, check no-arbitrage lower bound (price ≥ intrinsic discounted) and return `float("nan")` if violated or if vega at solution < epsilon.
- [ ] **Step 4: Run, pass.**
- [ ] **Step 5: Commit** `feat(pricing): nan-safe implied vol solver`.

> American-call note (deferred to v2): for stock calls with an ex-dividend before expiry, BS underprices the early-exercise premium. v1 uses European BS for puts/index and stock calls without intervening ex-div (the common case, since B3 adjusts strike for cash dividends). Flag affected series in the API with `pricing_model: "bs_european"` so the UI can label any approximation honestly.

---

## Chunk 4: Realized vol + IV-vs-RV signal

### Task 4.1: Close-to-close realized vol

**Files:** Create `apps/api/atlas_api/pricing/rv.py`; Test `tests/pricing/test_rv.py`

- [ ] **Step 1: Failing test** — `realized_vol(closes, window=21)` of a constant series is 0; of a known series matches a hand-computed annualized (×√252) stdev of log returns.
- [ ] **Step 2: Run, fail.**
- [ ] **Step 3: Implement** log-returns → rolling stdev → annualize ×√252. Also expose HAR components `rv_d, rv_w, rv_m` (1/5/21-day).
- [ ] **Step 4: Run, pass.**
- [ ] **Step 5: Commit** `feat(pricing): realized vol and HAR components`.

### Task 4.2: IV-vs-RV classifier (honest heuristic)

**Files:** Create `apps/api/atlas_api/pricing/signal.py`; Test `tests/pricing/test_signal.py`

- [ ] **Step 1: Failing test** — `classify(iv, rv, band=0.10)` → `"rico"` when `iv > rv*(1+band)`, `"barato"` when `iv < rv*(1-band)`, else `"neutro"`.
- [ ] **Step 2: Run, fail.**
- [ ] **Step 3: Implement** the band classifier. It returns a label + the raw ratio (no recommendation).
- [ ] **Step 4: Run, pass.**
- [ ] **Step 5: Commit** `feat(pricing): iv-vs-rv heuristic classifier`.

---

## Chunk 5: FastAPI contract

### Task 5.1: Pydantic contract models + schema export

**Files:** Create `apps/api/atlas_api/models.py`, `packages/contract/schema.json`; Test `tests/api/test_models.py`

- [ ] **Step 1: Failing test** — `ScreenerRow` model validates a sample dict with all fields (`ticker, tipo, ultimo, var_pct, liquidez, iv, iv_vs_rv, provenance, asof`); serializing matches `packages/contract/fixtures/screener_row.json`.
- [ ] **Step 2: Run, fail.**
- [ ] **Step 3: Implement** pydantic models incl. `provenance: str` and `asof: datetime` (honesty fields), export JSON schema to `packages/contract/schema.json`.
- [ ] **Step 4: Run, pass.**
- [ ] **Step 5: Commit** `feat(api): contract models with provenance + asof`.

### Task 5.2: Screener and chain endpoints

**Files:** Create `apps/api/atlas_api/api/main.py`, `routes_screener.py`, `routes_chain.py`; Test `tests/api/test_routes.py`

- [ ] **Step 1: Failing test** — using `fastapi.testclient`, `GET /screener?tipo=opcao&min_liq=20000000` returns 200 and rows respect the filter; `GET /chain/PETR4` returns calls+puts with iv/greeks; every row has `asof` and `provenance`.
- [ ] **Step 2: Run, fail.**
- [ ] **Step 3: Implement** routes reading from the DuckDB store, applying filters, attaching `provenance="COTAHIST EOD"` + `asof`.
- [ ] **Step 4: Run, pass.**
- [ ] **Step 5: Commit** `feat(api): screener and chain endpoints`.

### Task 5.3: Daily ingestion job

- [ ] **Step 1: Failing test** — `ingest_day(path)` parses a COTAHIST file, computes IV/greeks/RV for option rows, writes Parquet, and the row count > 0.
- [ ] **Step 2–4:** Implement orchestrator (`cotahist → curve → corp_actions → pricing → store`), run, pass.
- [ ] **Step 5: Commit** `feat(data): daily EOD ingestion job`.

---

## Chunk 6: Frontend shell (design system + navigation)

> Build against `packages/contract/fixtures/*` until the API is live. Apply the ATLAS design system (spec §7). TDD here = component tests with `@testing-library/react` + visual check via `npm run dev`.

### Task 6.1: Design tokens

- [ ] Create `apps/web/styles/tokens.css` with the OKLCH tokens from the spec (dark-first; semantic color discipline: green/red = price only, amber = brand, IV thermal ramp). Wire into `tailwind.config.ts`. Add `next-themes` provider. Commit `feat(web): design tokens and theming`.

### Task 6.2: App shell — sidebar + topbar + bento grid

- [ ] Build collapsible dense sidebar (modules: Mercado, Screener, Opções, Carteira), contextual topbar (pregão status, clock, EOD badge), and a resizable bento layout (`react-resizable-panels`). Keyboard: `[` toggles sidebar. Commit `feat(web): app shell with sidebar, topbar, bento`.

### Task 6.3: Command palette (⌘K)

- [ ] Integrate `cmdk`: navigation actions ("ir para PETR4", "cadeia VALE3") wired to routes; placeholder for desk actions. Commit `feat(web): command palette navigation`.

---

## Chunk 7: Frontend modules (Screener + Options desk)

### Task 7.1: Screener table

- [ ] TanStack Table + Virtual, columns per spec, filter chips (liquidez/IV/gregas/moneyness), IV-vs-RV badge with thermal colors + "heurística" tooltip, EOD/provenance shown. Wire to `GET /screener` via TanStack Query. Commit `feat(web): screener module`.

### Task 7.2: Options desk

- [ ] Option chain (virtualized) for a selected underlying from `GET /chain/:ticker`; IV smile (visx); 2-leg structure builder with payoff diagram (visx) + net greeks; drag-to-update with Motion spring. All numbers mono/tabular. Commit `feat(web): options desk with payoff builder`.

### Task 7.3: Wire live API + honesty pass

- [ ] Replace fixtures with live API base URL; add global "dados EOD · asof" indicator; ensure no element implies a buy/sell recommendation (review against spec §1 régua de honestidade). Commit `feat(web): wire live api and honesty review`.

---

## Chunk 8: Analista (consultor) — briefing honesto

> Depends on Chunks 3–4 (IV/greeks/RV) + 5 (API). Assembles a structured briefing from transparent rules + data, then uses an LLM only to write the readable prose. Honesty guard: no buy/sell call, max-loss always present, all three risk profiles.

### Task 8.1: Briefing assembler (pure, deterministic, no LLM)

**Files:** Create `apps/api/atlas_api/analyst/briefing.py`; Test `tests/analyst/test_briefing.py`

- [ ] **Step 1: Failing test** — `build_briefing(setup)` for a rich-IV call-spread returns a `Briefing` with: `setup_facts`, `case_for[]`, `case_against[]`, `risk_reward` (max_gain, max_loss, breakeven, ratio), `sizing` with **all three** profiles (`conservador/moderado/agressivo`, each = % capital, lotes, max_loss_brl), `invalidation`, `confidence`, and `verdict`. Assert `case_against` is non-empty and `sizing` has 3 entries.
- [ ] **Step 2: Run, fail.**
- [ ] **Step 3: Implement** deterministic assembler from rules (band of IV-vs-RV, greeks, liquidity, DTE) + a sizing function `size(profile, capital, max_loss_per_lot)`.
- [ ] **Step 4: Run, pass.**
- [ ] **Step 5: Commit** `feat(analyst): deterministic briefing assembler with 3 risk profiles`.

### Task 8.2: LLM prose layer (honesty-guarded)

**Files:** Create `apps/api/atlas_api/analyst/writer.py`; Test `tests/analyst/test_writer.py`

- [ ] **Step 1: Failing test** — `to_prose(briefing)` builds a prompt that includes the facts and BOTH sides; `guard(text)` rejects output containing forbidden phrases ("compre", "venda", "vai subir", "garantido", "recomendo") and requires the max-loss + "decisão é sua" disclaimer. Test the guard with a stubbed LLM client (no network).
- [ ] **Step 2: Run, fail.**
- [ ] **Step 3: Implement** prompt builder + `guard()`; LLM client is injected (Claude via `anthropic`, key from env) and mockable. The guard runs on every output; on violation, re-prompt once then fall back to the deterministic template.
- [ ] **Step 4: Run, pass.**
- [ ] **Step 5: Commit** `feat(analyst): honesty-guarded llm prose writer`.

### Task 8.3: `/briefing/:setup_id` endpoint + frontend card

- [ ] **Step 1: Failing test** — `GET /briefing/...` returns a contract-valid briefing with 3 profiles + provenance + asof.
- [ ] **Step 2–4:** Implement route; build the frontend briefing card (the ATLAS-style component: setup, A favor / Contra, risk-reward tiles, **all 3 profiles shown together**, invalidation, honest verdict + disclaimer). Run, pass.
- [ ] **Step 5: Commit** `feat(analyst): briefing endpoint and frontend card`.

---

## Acceptance (v1)

- Backend: `pytest` green; `ingest_day` produces a Parquet for one real COTAHIST day; IV/greeks validated against a textbook value (Task 3.1) and one real series sanity-checked.
- API: `GET /screener` and `GET /chain/PETR4` return contract-valid JSON with `provenance` + `asof`.
- Web: `npm run dev` shows the dark shell (sidebar + topbar + ⌘K + bento); Screener filters the universe; Options desk shows a chain + a 2-leg payoff; every number shows EOD provenance; nothing implies a prophecy.
