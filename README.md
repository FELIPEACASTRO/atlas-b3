# ATLAS — terminal de decisão de opções B3

Painel local de apoio à decisão para o mercado de opções da B3. **Fatos e análises
transparentes, nunca profecia**: cada número carrega proveniência e `asof`, o gate
de IV se recusa a inventar volatilidade de preço stale, e toda análise mostra os
dois lados (a decisão é sempre sua).

> Uso pessoal/local sobre dados reais EOD (COTAHIST). Não é recomendação de
> investimento.

## Módulos

- **Radar / Screener** — panorama do dia, filtros, IV, **IV Rank**, **VRP**, sinal IV-vs-RV.
- **Opções** — cadeia com IV/gregas (americanas via Bjerksund-Stensland; índice IBOV
  europeu), **gráfico IV vs RV** histórico, **superfície de volatilidade** (estrutura
  a termo + heatmap), e um **painel por opção** (prós/contras, comprar vs vender/sair,
  gregas traduzidas — clique em qualquer série).
- **Carteira** — posições ações+opções, risco líquido (Δ/Γ/vega/θ), **stress** de
  mercado e **diagrama de payoff** (hoje vs no vencimento).
- **Analista** — briefing honesto por subjacente (setup, dois lados, 3 perfis de risco).

## Stack

- `apps/api` — quant core **Python puro (stdlib, sem numpy/scipy)** + FastAPI + SQLite.
  Black-Scholes, Bjerksund-Stensland (americana), IV solver com gate econômico,
  realized vol / HAR, VRP/skew, IV Rank, risco de carteira. Dados: COTAHIST (B3),
  Selic (BCB-SGS), dividend yield (brapi).
- `apps/web` — Next.js 16 + TypeScript + Tailwind v4, dark-first (OKLCH), ⌘K command
  palette, gráficos SVG interativos.

## Rodar localmente

Pré-requisitos: Python 3.12+ e Node 20+.

```bash
# 1) API (porta 8000) — venv já em apps/api/.venv
ATLAS_DB=data_cache/atlas.db PYTHONPATH=apps/api \
  apps/api/.venv/Scripts/python.exe -m uvicorn atlas_api.api.main:app --port 8000

# 2) Web (porta 3000)
npm --prefix apps/web run dev      # abra http://localhost:3000
```

Testes: `PYTHONPATH=apps/api apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests -q`

## Dados (o `data_cache/atlas.db` é gitignored — regenere)

```bash
# carga histórica profunda (ex.: ~1 ano -> ativa IV Rank 52 semanas)
python -m atlas_api.cli backfill --sessions 252

# dias específicos (full chain)
python -m atlas_api.cli ingest --date 26062026

# job diário: ingere o último pregão disponível
python -m atlas_api.cli update
```

**Agendar o job diário (Windows):** `scripts/atlas-daily.cmd` roda o `update`.
Agende uma vez (~20:00, dias úteis):

```bat
schtasks /Create /TN "ATLAS daily" /TR "%CD%\scripts\atlas-daily.cmd" ^
  /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 20:00
```

## Cobertura

Opções **sobre ações** (americanas) e **sobre Ibovespa** (IBOV, europeias) que
negociaram no pregão. O COTAHIST traz apenas séries com negócio no dia. **Fora do
escopo atual:** futuros (WIN/WDO/DI1) — exigem uma fonte de dados B3 distinta do
COTAHIST.

## Documentação

`docs/` traz a pesquisa (00–07, incl. varredura AIForge), as lições/erros
(`LICOES-ERROS-E-ACERTOS.md`), specs, plano e arquitetura.
